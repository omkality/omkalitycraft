"""Owner admission barrier for one immutable source; no candidate promotion."""

import hashlib
import json
import re
import time
from datetime import UTC, datetime
from uuid import uuid4

from omk import (
    admin_backups as backups,
    admin_maintenance as maintenance,
    ingress_config as deployment,
)
from omk.admin import AdminError, _private_path, _read_json, _write_private
from omk.backup_store import _sync_directory
from omk.ingress_template import LABEL
from omk.profiles import PROJECT_ROOT
from omk.recovery_console import RecoveryConsole

TERMINAL = {"confirmed", "cancelled"}


def worker(config, value, action="status", *, source_required=False, operation=None):
    spec, target = value["spec"], value["target"]
    operation = operation or uuid4().hex
    args = [
        "run",
        "--rm",
        "--pull",
        "never",
        "-i",
        "--name",
        "omk-ingress-worker-" + operation,
        "--label",
        LABEL + "=" + spec["owner"],
        "--label",
        "omkality.ingress.helper=true",
        "--network",
        "none",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges:true",
        "--memory",
        "128m",
        "--cpus",
        "1",
        "--pids-limit",
        "32",
        "--log-driver",
        "none",
        "--volumes-from",
        value["proxy"]["id"] + ":ro",
        "--mount",
        f"type=volume,source={target['data_volume']},target=/server,readonly",
    ]
    for name in ("omk", "launcher"):
        args += [
            "--mount",
            f"type=bind,source={PROJECT_ROOT/name},target=/src/{name},readonly",
        ]
    request = {
        "schema": 1,
        "action": action,
        "config_sha256": value["config_sha256"],
        "backend": target["container"],
        "port": spec["backend_port"],
        "rcon_port": value["rcon_port"],
        "source_required": source_required,
    }
    raw = backups.docker(
        *args,
        "--workdir",
        "/src",
        "--env",
        "PYTHONDONTWRITEBYTECODE=1",
        backups.IMAGE,
        "python",
        "-m",
        "omk.ingress_worker",
        stdin=json.dumps(request),
        timeout=15,
        allowed_codes=(0, 1),
    )
    if len(raw.encode()) > 65536:
        raise AdminError("Ingress worker response exceeds bound")
    reply = json.loads(raw)
    result = reply.get("result", {})
    if (
        reply.get("ok") is not True
        or set(result)
        != {
            "closed",
            "sessions",
            "address",
            "backend_up",
            "config_sha256",
            "properties_sha256",
        }
        or type(result["closed"]) is not bool
        or type(result["backend_up"]) is not bool
        or type(result["sessions"]) is not int
        or not 0 <= result["sessions"] <= value["policy"]["max_connections"]
        or result["config_sha256"] != value["config_sha256"]
        or (
            source_required
            and not re.fullmatch(r"[a-f0-9]{64}", result.get("properties_sha256") or "")
        )
    ):
        raise AdminError(
            "Ingress proof refused; inspect private deployment and command acknowledgement"
        )
    return result


def capture(config, server, *, policy=None, closed=False):
    value = deployment.capture(config, server, policy)
    state = worker(config, value)
    if deployment.capture(config, server, value["policy"]) != value:
        raise AdminError("Ingress changed during inspection")
    if closed and not state["closed"]:
        raise AdminError("Close and confirm the ingress before maintenance")
    return value, state


def guard(config, server, expected, *, closed=False):
    if expected is None:
        if deployment.configured(config):
            raise AdminError(
                "Ingress configuration appeared during maintenance; plan again"
            )
        return
    value, _ = capture(config, server, policy=expected["policy"], closed=closed)
    if value != expected:
        raise AdminError("Maintenance ingress deployment identity changed")


def journal(config, operation):
    if not isinstance(operation, str) or not re.fullmatch(r"[a-f0-9]{32}", operation):
        raise AdminError("Invalid ingress operation")
    return _private_path(config.private, "ingress/" + operation + ".json")


def read(config, operation):
    r = _read_json(journal(config, operation), config.private)
    keys = {
        "schema",
        "operation",
        "server",
        "wanted",
        "deployment",
        "lifecycle",
        "readiness",
        "before",
        "stage",
        "created_at",
        "updated_at",
        "result",
    }
    if (
        type(r.get("schema")) is not int
        or r["schema"] != 1
        or r.get("operation") != operation
        or set(r) != keys
        or r["wanted"] not in {"open", "closed"}
        or r["stage"] not in TERMINAL | {"planned", "applying"}
        or r["server"] not in config.servers
    ):
        raise AdminError("Invalid ingress journal")
    return r


def records(config):
    folder = _private_path(config.private, "ingress")
    if not folder.exists():
        return []
    paths = list(folder.iterdir())
    if len(paths) > 1000:
        raise AdminError("Ingress journal exceeds bound")
    return [read(config, p.stem) for p in paths]


def save(config, r, stage):
    r.update(stage=stage, updated_at=datetime.now(UTC).isoformat())
    if len(json.dumps(r).encode()) > 65536:
        raise AdminError("Ingress journal exceeds size bound")
    _write_private(journal(config, r["operation"]), config.private, r)
    _sync_directory(journal(config, r["operation"]).parent)


def status(r):
    return {
        "ok": True,
        "operation": r["operation"],
        "server": r["server"],
        "stage": r["stage"],
        "wanted": r["wanted"],
        "loopback_only": True,
        "ready_for_players": False,
        "promoted": False,
    }


def operations_clear(config, server, operation=None):
    from omk.world_cutover import consumed, require_clear  # noqa: PLC0415

    require_clear(config, server)
    for r in records(config):
        if (
            r["server"] == server
            and r["stage"] not in TERMINAL
            and r["operation"] != operation
        ):
            raise AdminError("Resolve pending ingress operations before opening")
    for folder, reader, terminal in (
        ("maintenance", maintenance.read_record, maintenance.TERMINAL),
    ):
        path = config.private / folder
        if path.exists():
            for p in path.iterdir():
                r = reader(config, p.stem)
                if r["server"] == server and r["stage"] not in terminal:
                    raise AdminError("Maintenance is pending; ingress must stay closed")
    from omk import (  # noqa: PLC0415
        admin_reset_staging as reset,
        candidate_slots,
    )

    path = config.private / "resource-resets"
    if path.exists():
        for p in path.iterdir():
            r = reset.read_record(config, p.stem)
            if (
                r["server"] == server
                and r["stage"] != "abandoned"
                and not consumed(config, r)
            ):
                raise AdminError(
                    "Resource candidate is pending; ingress must stay closed"
                )
    if any(
        r["server"] == server and r["stage"] != "released"
        for r in candidate_slots.records(config)
    ):
        raise AdminError("Candidate slot is pending; ingress must stay closed")


def source_ready(config, server, value):
    binding = maintenance.binding(config, server)
    source = maintenance.snapshot(value["target"], binding)
    if not source["running"] or source["container"] != value["proxy"]["source_id"]:
        raise AdminError("Ingress opening requires the same running source")
    logs = backups.docker(
        "logs", "--since", source["started"], "--tail", "4000", source["container"]
    )
    if (
        len(logs.encode()) > 8 * 1024**2
        or not re.search(r"Done \([^\r\n]{1,64}\)!", logs)
        or any(
            s in logs
            for s in (
                "Encountered an unexpected exception",
                "This crash report has been saved to:",
            )
        )
    ):
        raise AdminError("Source boot lacks clean readiness")
    console, password = maintenance.credential(config, server)
    RecoveryConsole(console, password).ready()
    if maintenance.snapshot(value["target"], binding) != source:
        raise AdminError("Source changed during readiness")
    return source


def backend_address(value):
    data = json.loads(
        backups.docker("inspect", "--type", "container", value["proxy"]["source_id"])
    )[0]
    return data["NetworkSettings"]["Networks"][value["spec"]["network"]]["IPAddress"]


def plan(config, server, wanted, environment=None, *, _operation=None):
    with backups.locked(config):
        operation = backups.planned_id(config, "ingress", _operation)
        if wanted not in {"open", "closed"}:
            raise AdminError("Invalid ingress target state")
        policy = maintenance.settings(environment)
        if len(records(config)) >= policy["journal_count"]:
            raise AdminError("Archive terminal ingress history before planning")
        if wanted == "open":
            operations_clear(config, server)
        value, before = capture(config, server)
        readiness = source_ready(config, server, value) if wanted == "open" else None
        if wanted == "open":
            before = worker(config, value, source_required=True)
            if before["address"] != backend_address(value):
                raise AdminError("Wait for ingress DNS to resolve the current source")
        r = {
            "schema": 1,
            "operation": operation,
            "server": server,
            "wanted": wanted,
            "deployment": value,
            "lifecycle": policy,
            "readiness": readiness,
            "before": before,
            "stage": "planned",
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": "",
            "result": None,
        }
        save(config, r, "planned")
        return status(r)


def current(config, r, *, allow_new_boot=False):
    value = deployment.capture(config, r["server"], r["deployment"]["policy"])
    expected = json.loads(json.dumps(r["deployment"]))
    if allow_new_boot:
        expected["proxy"]["started"] = value["proxy"]["started"]
    if value != expected:
        raise AdminError("Ingress deployment changed after planning")
    return value


def confirm(config, r):
    deadline = time.monotonic() + r["deployment"]["policy"]["timeout_seconds"]
    while True:
        value = current(config, r)
        opening = r["wanted"] == "open"
        if opening:
            operations_clear(config, r["server"], r["operation"])
            if source_ready(config, r["server"], value) != r["readiness"]:
                raise AdminError("Source boot changed after ingress plan")
        result = worker(config, value, source_required=opening)
        if result["closed"] == (not opening) and (
            not opening
            or (
                result["backend_up"]
                and result["address"] == backend_address(value)
                and result["properties_sha256"] == r["before"]["properties_sha256"]
            )
        ):
            if current(config, r) != value:
                raise AdminError("Ingress changed after confirmation")
            r["result"] = result
            save(config, r, "confirmed")
            return status(r)
        if time.monotonic() >= deadline:
            raise AdminError(
                "Ingress state unconfirmed; verify without repeating the command"
            )
        time.sleep(r["lifecycle"]["poll_milliseconds"] / 1000)


def execute(config, operation, action):
    with backups.locked(config):
        r = read(config, operation)
        if action == "status":
            return status(r)
        if action == "cancel":
            value = current(config, r, allow_new_boot=True)
            if r["stage"] in TERMINAL or not worker(config, value)["closed"]:
                raise AdminError("Cancellation requires verified closed ingress")
            save(config, r, "cancelled")
            return status(r)
        if action == "verify":
            if r["stage"] not in {"applying", "confirmed"}:
                raise AdminError("Ingress has no attempted command to verify")
            return confirm(config, r)
        if action != "apply" or r["stage"] != "planned":
            raise AdminError("Ingress command was already attempted or is unsupported")
        age = (
            datetime.now(UTC) - datetime.fromisoformat(r["created_at"])
        ).total_seconds()
        if not 0 <= age <= r["lifecycle"]["plan_ttl_seconds"]:
            raise AdminError("Ingress plan expired")
        value = current(config, r)
        opening = r["wanted"] == "open"
        if opening:
            operations_clear(config, r["server"], r["operation"])
            if source_ready(config, r["server"], value) != r["readiness"]:
                raise AdminError("Source changed before opening")
        before = worker(config, value, source_required=opening)
        if (
            before["closed"] != r["before"]["closed"]
            or before["properties_sha256"] != r["before"]["properties_sha256"]
        ):
            raise AdminError("Ingress state or source properties changed before intent")
        save(config, r, "applying")
        worker(
            config,
            value,
            r["wanted"] if opening else "close",
            source_required=opening,
            operation=r["operation"],
        )
        return confirm(config, r)


def abandon_close_plan(config, operation):
    """Internal cancellation before any close intent; never sends a proxy write."""
    with backups.locked(config):
        r = read(config, operation)
        if r["stage"] != "planned" or r["wanted"] != "closed":
            raise AdminError("Only an unattempted close plan can be abandoned")
        value = current(config, r)
        state = worker(config, value)
        if state["config_sha256"] != r["before"]["config_sha256"]:
            raise AdminError("Ingress config changed before cancellation")
        save(config, r, "cancelled")
        return status(r)


def add_parser(actions):
    sub = actions.add_parser(
        "ingress", help="Owner loopback admission barrier; no promotion"
    ).add_subparsers(dest="ingress_action", required=True)
    for name in ("prepare", "inspect"):
        sub.add_parser(name).add_argument("--server", required=True)
    p = sub.add_parser("plan")
    p.add_argument("--server", required=True)
    p.add_argument("--state", choices=["open", "closed"], required=True)
    for name in ("apply", "verify", "status", "cancel"):
        sub.add_parser(name).add_argument("--operation", required=True)


def run(config, args):
    if args.ingress_action == "prepare":
        with backups.locked(config):
            return deployment.preparation(config, args.server)
    if args.ingress_action == "inspect":
        value, state = capture(config, args.server)
        return {
            "ok": True,
            "server": args.server,
            "closed": state["closed"],
            "sessions": state["sessions"],
            "loopback_only": True,
            "ready_for_players": False,
            "deployment_sha256": hashlib.sha256(
                json.dumps(value, sort_keys=True).encode()
            ).hexdigest(),
        }
    if args.ingress_action == "plan":
        return plan(config, args.server, args.state)
    return execute(config, args.operation, args.ingress_action)
