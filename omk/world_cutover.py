"""Owner cold installation into the same source container, with retained worlds."""

import json
import re
from datetime import UTC, datetime
from uuid import uuid4

from omk import (
    admin_backups as backups,
    admin_maintenance as maintenance,
    admin_reset_staging as staging,
    cutover_lease,
    ingress,
)
from omk.admin import AdminError, _private_path, _read_json, _write_private
from omk.backup_store import _sync_directory
from omk.cold_backup_worker import digest
from omk.profiles import PROJECT_ROOT

TERMINAL = {"cancelled", "reverted", "committed"}
STAGES = TERMINAL | {
    "planned",
    "applying",
    "installed",
    "reverting",
    "commit-requested",
    "cancelling",
}
LABEL = "omkality.world.cutover"


def path(config, operation):
    if not isinstance(operation, str) or not re.fullmatch(r"[a-f0-9]{32}", operation):
        raise AdminError("Invalid world cutover identifier")
    return _private_path(config.private, "world-cutovers/" + operation + ".json")


def read(config, operation):
    r = _read_json(path(config, operation), config.private)
    if (
        set(r)
        != {
            "schema",
            "operation",
            "server",
            "resource_operation",
            "resource_sha256",
            "window_sha256",
            "expected",
            "created_at",
            "updated_at",
            "stage",
            "result",
            "write_lease",
        }
        or type(r.get("schema")) is not int
        or r["schema"] != 1
        or r.get("operation") != operation
        or r["stage"] not in STAGES
        or r["server"] not in config.servers
        or not re.fullmatch(r"[a-f0-9]{32}", r["resource_operation"])
        or (
            r["write_lease"] is not None
            and not re.fullmatch(r"[a-f0-9]{32}", r["write_lease"])
        )
    ):
        raise AdminError("Invalid world cutover journal")
    return r


def records(config):
    folder = _private_path(config.private, "world-cutovers")
    if not folder.exists():
        return []
    paths = list(folder.iterdir())
    if len(paths) > 1000:
        raise AdminError("World cutover journal exceeds bound")
    return [read(config, p.stem) for p in paths]


def require_clear(config, server):
    if any(
        r["server"] == server and r["stage"] not in TERMINAL for r in records(config)
    ):
        raise AdminError(
            "World cutover is pending; reconcile it before another owner operation"
        )


def save(config, r, stage, *, arm=False):
    r.update(stage=stage, updated_at=datetime.now(UTC).isoformat())
    if not arm:
        r["write_lease"] = None
    elif stage not in {"applying", "reverting"} or r["write_lease"] is None:
        raise AdminError("Only a fresh durable world write attempt may be armed")
    if len(json.dumps(r).encode()) > 65536:
        raise AdminError("World cutover journal exceeds size bound")
    # Revoke the preceding attempt before changing intent. Only arm a fresh
    # request after its durable journal exists. A delayed Docker run can never
    # resume with an old nonce after cancellation or another attempt.
    cutover_lease.publish(config, r["operation"], stage, None)
    _write_private(path(config, r["operation"]), config.private, r)
    _sync_directory(path(config, r["operation"]).parent)
    if r["write_lease"] is not None:
        cutover_lease.publish(config, r["operation"], stage, r["write_lease"])


def resource_identity(p):
    return digest(
        {
            k: v
            for k, v in p.items()
            if k not in {"stage", "updated_at", "installation_operation"}
        }
    )


def window_identity(window):
    return digest(
        {
            k: window[k]
            for k in (
                "operation",
                "server",
                "target",
                "binding",
                "initial",
                "runtime",
                "checkpoint",
                "operator_root",
                "ingress",
            )
        }
    )


def consumed(config, resource):
    operation = resource.get("installation_operation")
    if not operation:
        return False
    r = read(config, operation)
    return (
        resource["stage"] == "installed"
        and r["stage"] == "committed"
        and r["resource_operation"] == resource["operation"]
        and resource_identity(resource) == r["resource_sha256"]
    )


def runtime_request(p):
    return {
        "schema": 1,
        "action": "runtime-verify",
        "operation": p["operation"],
        "world": p["source"]["world"],
        "dimension": p["dimension"],
        "position": "auto",
        "snapshot": p["snapshot"],
        "world_max_bytes": p["settings"]["world_max_bytes"],
        "preflight_options": p["preflight_options"],
        "policy": {
            k: p["settings"][k]
            for k in ("max_bytes", "max_count", "staging_bytes", "reserve_bytes")
        },
        "expected": p["expected"],
        "runtime_expected": p["runtime_expected"],
    }


def worker(config, r, p, action):
    writable = action in {"apply", "recover", "revert"}
    args = [
        "run",
        "--rm",
        "--pull",
        "never",
        "-i",
        "--name",
        "omk-world-cutover-" + r["operation"],
        "--label",
        LABEL + "=" + r["operation"],
        "--network",
        "none",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges:true",
        "--memory",
        str(p["settings"]["helper_memory_mib"]) + "m",
        "--cpus",
        str(p["settings"]["helper_cpus"]),
        "--pids-limit",
        "32",
        "--log-driver",
        "none",
    ]
    for name, destination, ro in [
        (p["source"]["data_volume"], "server", not writable),
        (p["source"]["store_volume"], "backup", True),
        (p["target"]["data_volume"], "target", True),
    ]:
        args += [
            "--mount",
            f"type=volume,source={name},target=/{destination}"
            + (",readonly" if ro else ""),
        ]
    for name in ("omk", "launcher", "profiles"):
        args += [
            "--mount",
            f"type=bind,source={PROJECT_ROOT/name},target=/src/{name},readonly",
        ]
    control = cutover_lease.directory(config, r["operation"])
    if action == "plan":
        cutover_lease.publish(config, r["operation"], "planned", None)
    args += ["--mount", f"type=bind,source={control},target=/control,readonly"]
    raw = backups.docker(
        *args,
        "--workdir",
        "/src",
        "--env",
        "PYTHONDONTWRITEBYTECODE=1",
        backups.IMAGE,
        "python",
        "-m",
        "omk.world_cutover_worker",
        stdin=json.dumps(
            {
                "schema": 1,
                "action": action,
                "operation": r["operation"],
                "runtime": runtime_request(p),
                "expected": r.get("expected"),
                "write_lease": r["write_lease"],
            }
        ),
        timeout=p["settings"]["timeout_seconds"],
        allowed_codes=(0, 1),
    )
    if len(raw.encode()) > 65536:
        raise AdminError("World cutover proof exceeds bound")
    response = json.loads(raw)
    if response.get("ok") is not True or not isinstance(response.get("result"), dict):
        raise AdminError(
            "World cutover proof refused; inspect private generations and journal"
        )
    return response["result"]


def status(r):
    return {
        "ok": True,
        "operation": r["operation"],
        "server": r["server"],
        "stage": r["stage"],
        "resource_operation": r["resource_operation"],
        "filesystem_phase": (r["result"] or {}).get("phase"),
        "same_container_only": True,
        "ready_for_players": False,
    }


def drained(config, server, window):
    if window.get("ingress") is None:
        raise AdminError("World installation requires configured and closed ingress")
    value, state = ingress.capture(
        config, server, policy=window["ingress"]["policy"], closed=True
    )
    if value != window["ingress"] or state["sessions"] != 0:
        raise AdminError(
            "World installation requires the same closed ingress with zero TCP sessions"
        )


def current(config, r, *, running=False):
    p = staging.read_record(config, r["resource_operation"])
    window = maintenance.read_record(config, p["maintenance_operation"])
    if (
        resource_identity(p) != r["resource_sha256"]
        or window_identity(window) != r["window_sha256"]
        or p["stage"] not in {"runtime-ready", "installed"}
        or (
            p["stage"] == "installed"
            and p.get("installation_operation") != r["operation"]
        )
        or window["stage"] != ("complete" if running else "stopped")
        or backups.target_for(config, r["server"]) != p["source"]
        or str(config.servers[r["server"]]) != p["operator_root"]
    ):
        raise AdminError("World installation bindings or maintenance window changed")
    observed = maintenance.current(config, window)
    if running:
        if observed != window["resumed"] or not observed["running"]:
            raise AdminError(
                "World installation requires its exact accepted source boot"
            )
    elif backups.checkpoint(p["source"]) != p["checkpoint"]:
        raise AdminError(
            "Source boot changed; a started world cannot be reverted by this operation"
        )
    references = backups.docker(
        "ps", "-aq", "--no-trunc", "--filter", "volume=" + p["source"]["data_volume"]
    ).split()
    if set(references) != {window["initial"]["container"]}:
        raise AdminError(
            "Source volume has a foreign container or pending cutover helper"
        )
    from omk import candidate_slots, owner_volumes  # noqa: PLC0415

    candidate_slots.require_clear(config, p["operation"])
    if owner_volumes.destination(p["target"], unused=True) != p["destination"]:
        raise AdminError("World candidate identity changed")
    backup = staging.backup_for(config, p)
    if digest(backup) != p["backup_sha256"]:
        raise AdminError("World installation backup journal changed")
    drained(config, r["server"], window)
    return p, window


def plan(config, resource_operation):
    from omk.candidate_slots import require_clear as slots_clear  # noqa: PLC0415

    with backups.locked(config):
        p = staging.read_record(config, resource_operation)
        require_clear(config, p["server"])
        if (
            p["stage"] != "runtime-ready"
            or len(records(config)) >= maintenance.settings()["journal_count"]
        ):
            raise AdminError(
                "World installation requires a sealed candidate and room in the journal"
            )
        staging.stable(config, p)
        slots_clear(config, resource_operation)
        window = maintenance.read_record(config, p["maintenance_operation"])
        drained(config, p["server"], window)
        source = json.loads(
            backups.docker(
                "inspect", "--type", "container", window["initial"]["container"]
            )
        )[0]
        if source["Config"].get("User") not in {"", "0", "root", "0:0"}:
            raise AdminError(
                "This world exchange adapter requires the reviewed root-owned source runtime"
            )
        r = {
            "schema": 1,
            "operation": uuid4().hex,
            "server": p["server"],
            "resource_operation": p["operation"],
            "resource_sha256": resource_identity(p),
            "window_sha256": window_identity(window),
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": "",
            "stage": "planned",
            "result": None,
            "write_lease": None,
        }
        r["expected"] = worker(config, r, p, "plan")
        current(config, r)
        save(config, r, "planned")
        return status(r)


def for_window(config, operation):
    found = [
        r
        for r in records(config)
        if r["stage"] not in TERMINAL
        and staging.read_record(config, r["resource_operation"])[
            "maintenance_operation"
        ]
        == operation
    ]
    if len(found) > 1:
        raise AdminError("Ambiguous world cutover for maintenance")
    return found[0] if found else None


def start_proof(config, window, backup):
    r = for_window(config, window["operation"])
    if r is None:
        return None
    if r["stage"] != "installed":
        raise AdminError(
            "World installation is not confirmed; verify or recover it before start"
        )
    p, _ = current(config, r)
    if backup["operation"] != p["backup_operation"]:
        raise AdminError("World installation requires its frozen backup")
    result = worker(config, r, p, "verify")
    if result["phase"] != "installed" or result["identity_sha256"] != digest(
        r["expected"]
    ):
        raise AdminError("Installed generation is incomplete or changed")
    current(config, r)
    return {
        "source": backup["source"],
        "snapshot": backup["result"],
        "cutover_operation": r["operation"],
        "installation_sha256": digest(r["expected"]),
    }


def commit(config, r):
    p, window = current(config, r, running=True)
    if window.get("proof", {}).get("cutover_operation") != r["operation"] or window[
        "proof"
    ].get("installation_sha256") != digest(r["expected"]):
        raise AdminError("Source boot has no verified installation proof")
    save(config, r, "commit-requested")
    p["installation_operation"] = r["operation"]
    staging.save(config, p, "installed")
    save(config, r, "committed")
    return status(r)


def attempted(r, p, action):
    if action == "apply":
        age = (
            datetime.now(UTC) - datetime.fromisoformat(r["created_at"])
        ).total_seconds()
        if r["stage"] != "planned" or not 0 <= age <= p["settings"]["plan_ttl_seconds"]:
            raise AdminError("World installation plan expired or was already attempted")
        return "applying"
    allowed = {
        "recover": {"applying", "cancelling"},
        "revert": {"installed", "reverting"},
        "verify": {"applying", "installed", "reverting", "cancelling"},
    }
    if action not in allowed or r["stage"] not in allowed[action]:
        raise AdminError("Unsupported world cutover transition")
    return (
        "reverting"
        if action == "revert"
        else ("applying" if action == "recover" else r["stage"])
    )


def execute(config, operation, action):
    with backups.locked(config):
        r = read(config, operation)
        if action == "status":
            return status(r)
        if action == "commit":
            if r["stage"] not in {"installed", "commit-requested"}:
                raise AdminError("No accepted source start to commit")
            return commit(config, r)
        p, _window = current(config, r)
        if action == "cancel":
            if r["stage"] not in {"planned", "applying", "cancelling"}:
                raise AdminError("Installed world requires an explicit revert")
            save(config, r, "cancelling")
            result = worker(config, r, p, "cancel")
            if result.get("phase") != "cancelled" or result.get(
                "identity_sha256"
            ) != digest(r["expected"]):
                raise AdminError(
                    "Original generation or revoked write fence is unconfirmed"
                )
            current(config, r)
            r["result"] = result
            save(config, r, "cancelled")
            return status(r)
        next_stage = attempted(r, p, action)
        if action != "verify":
            r["write_lease"] = uuid4().hex
            save(config, r, next_stage, arm=True)
        result = worker(config, r, p, action)
        current(config, r)
        if result.get("identity_sha256") != digest(r["expected"]):
            raise AdminError("World exchange result differs from intent")
        r["result"] = result
        phase = result["phase"]
        terminal = "reverted" if r["stage"] == "reverting" else "installed"
        if phase == terminal:
            save(config, r, terminal)
        else:
            save(config, r, r["stage"])
        return status(r)


def add_parser(actions):
    sub = actions.add_parser(
        "world-cutovers", help="Owner cold same-container world installation"
    ).add_subparsers(dest="cutover_action", required=True)
    sub.add_parser("plan").add_argument("--resource-operation", required=True)
    for action in (
        "apply",
        "verify",
        "recover",
        "revert",
        "cancel",
        "commit",
        "status",
    ):
        sub.add_parser(action).add_argument("--operation", required=True)


def run(config, args):
    if args.cutover_action == "plan":
        return plan(config, args.resource_operation)
    return execute(config, args.operation, args.cutover_action)
