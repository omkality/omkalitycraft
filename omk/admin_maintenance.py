"""Explicit owner maintenance of the same Docker container; never a scheduler."""

import contextlib
import json
import os
import re
import time
import tomllib
from datetime import UTC, datetime
from uuid import uuid4

from omk import admin_backups as backups
from omk.admin import AdminError, _private_path, _read_json, _write_private
from omk.diagnostics import regular
from omk.maintenance_console import stop as console_stop
from omk.profiles import PROJECT_ROOT
from omk.recovery_console import ConsoleError, RecoveryConsole

TERMINAL = {"complete", "cancelled"}
STAGES = TERMINAL | {"planned", "stop-requested", "stopped", "start-requested"}


def settings(environment=None):
    env = os.environ if environment is None else environment
    result = {}
    for key, default, minimum, maximum in (
        ("PLAN_TTL_SECONDS", 3600, 60, 86400),
        ("STOP_TIMEOUT_SECONDS", 120, 10, 600),
        ("START_TIMEOUT_SECONDS", 600, 10, 1800),
        ("READY_STABLE_SECONDS", 15, 5, 120),
        ("POLL_MILLISECONDS", 500, 100, 5000),
        ("JOURNAL_COUNT", 128, 8, 1000),
    ):
        raw = env.get("OMK_MAINTENANCE_" + key, str(default))
        if (
            not isinstance(raw, str)
            or not raw.isascii()
            or not raw.isdecimal()
            or len(raw) > 8
            or not minimum <= int(raw) <= maximum
        ):
            raise AdminError("Invalid OMK_MAINTENANCE_" + key)
        result[key.lower()] = int(raw)
    return result


def binding(config, server):
    path = config.private / "maintenance.toml"
    if not regular(path, config.private) or (
        os.name != "nt" and path.stat().st_mode & 0o077
    ):
        raise AdminError("Use a private mode-600 .omk-admin/maintenance.toml")
    with path.open("rb") as stream:
        raw = stream.read(65537)
    if len(raw) > 65536:
        raise AdminError("Maintenance configuration exceeds limit")
    doc = tomllib.loads(raw.decode())
    if (
        set(doc) != {"schema", "servers"}
        or type(doc["schema"]) is not int
        or doc["schema"] != 1
        or not isinstance(doc["servers"], dict)
        or not doc["servers"]
        or set(doc["servers"]) - set(config.servers)
    ):
        raise AdminError("Invalid maintenance allowlist")
    for entry in doc["servers"].values():
        if (
            not isinstance(entry, dict)
            or set(entry) != {"rcon_container_port"}
            or type(entry["rcon_container_port"]) is not int
            or not 1 <= entry["rcon_container_port"] <= 65535
        ):
            raise AdminError("Invalid maintenance RCON port")
    console = config.recovery_consoles.get(server)
    if server not in doc["servers"] or console is None:
        raise AdminError("Server requires an explicit maintenance binding and console")
    return {
        **doc["servers"][server],
        "host": console.host,
        "port": console.port,
        "adapter": console.adapter,
        "credential_file": console.credential_file,
    }


def credential(config, server):
    console = config.recovery_consoles[server]
    value = _read_json(
        _private_path(config.private, console.credential_file), config.private
    )
    if set(value) != {"password"}:
        raise AdminError("Invalid private maintenance console credential")
    return console, value["password"]


def snapshot(target, endpoint):
    """Metadata whitelist. Inspect never exposes Env, Args, properties or tokens."""
    rows = json.loads(
        backups.docker("inspect", "--type", "container", target["container"])
    )
    if len(rows) != 1:
        raise AdminError("Ambiguous maintenance container")
    data = rows[0]
    state, host = data["State"], data["HostConfig"]
    mount = [m for m in data["Mounts"] if m["Destination"] == "/srv"]
    expected_port = [{"HostIp": "127.0.0.1", "HostPort": str(endpoint["port"])}]
    port = str(endpoint["rcon_container_port"]) + "/tcp"
    if (
        (data["Config"].get("Labels") or {}).get(target["label"])
        != target["source_owner"]
        or data["Config"]["Image"] != target["image"]
        or host.get("RestartPolicy", {}).get("Name") not in {"no", ""}
        or host.get("NetworkMode") == "host"
        or host.get("PortBindings", {}).get(port) != expected_port
        or len(mount) != 1
        or mount[0].get("Name") != target["data_volume"]
        or mount[0]["Type"] != "volume"
        or any(m["Destination"].startswith("/srv/") for m in data["Mounts"])
        or state.get("OOMKilled") is not False
        or state.get("Paused") is not False
        or state.get("Restarting") is not False
        or state.get("Status") not in {"running", "exited"}
        or state.get("Running") != (state.get("Status") == "running")
        or (not state["Running"] and state.get("ExitCode") != 0)
    ):
        raise AdminError(
            "Maintenance requires the owned pinned container, exact loopback RCON binding and safe lifecycle"
        )
    active = backups.docker(
        "ps", "-q", "--no-trunc", "--filter", "volume=" + target["data_volume"]
    ).split()
    if set(active) != ({data["Id"]} if state["Running"] else set()):
        raise AdminError("Source volume has an unexpected active writer or helper")
    if (
        state["Running"]
        and data.get("NetworkSettings", {}).get("Ports", {}).get(port) != expected_port
    ):
        raise AdminError("Active RCON binding differs from the configured container")
    # Reuse cold-backup logging admission before accepting a running source.
    logs = host.get("LogConfig", {})
    opts = logs.get("Config", {})
    maximum = re.fullmatch(r"([0-9]{1,5})([km])", opts.get("max-size", ""))
    count = opts.get("max-file", "")
    if (
        logs.get("Type") != "local"
        or maximum is None
        or not count.isdecimal()
        or not 1 <= int(count) <= 4
        or int(maximum[1]) * {"k": 1024, "m": 1024**2}[maximum[2]] > 16 * 1024**2
    ):
        raise AdminError("Maintenance requires bounded Docker local logs")
    return {
        "container": data["Id"],
        "image": data["Image"],
        "created": data["Created"],
        "started": state["StartedAt"],
        "restart_count": data["RestartCount"],
        "source": backups.volume(target),
        "store": backups.volume(target, True),
        "running": state["Running"],
    }


def worker(record, action, backup=None):
    target, policy = record["target"], backups.settings()
    request = {
        "action": action,
        "rcon_container_port": record["binding"]["rcon_container_port"],
    }
    if backup is not None:
        policy = backup["settings"]
        request = {**backups.request_for(backup, action), "snapshot": backup["result"]}
    backups.volume(target)
    backups.volume(target, True)
    args = [
        "run",
        "--rm",
        "--pull",
        "never",
        "-i",
        "--name",
        "omk-maintenance-worker-" + uuid4().hex,
        "--label",
        "omkality.maintenance.operation=" + record["operation"],
        "--network",
        "none",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges:true",
        "--memory",
        str(policy["helper_memory_mib"]) + "m",
        "--cpus",
        str(policy["helper_cpus"]),
        "--pids-limit",
        "32",
        "--mount",
        f"type=volume,source={target['data_volume']},target=/server,readonly",
        "--mount",
        f"type=bind,source={PROJECT_ROOT/'omk'},target=/src/omk,readonly",
        "--workdir",
        "/src",
        "--env",
        "PYTHONDONTWRITEBYTECODE=1",
    ]
    if action == "proof":
        args += [
            "--mount",
            f"type=volume,source={target['store_volume']},target=/backup,readonly",
        ]
    raw = backups.docker(
        *args,
        backups.IMAGE,
        "python",
        "-m",
        "omk.maintenance_worker",
        stdin=json.dumps(request),
        timeout=policy["timeout_seconds"],
        allowed_codes=(0, 1),
    )
    if len(raw) > 65536:
        raise AdminError("Maintenance worker response exceeded limit")
    value = json.loads(raw)
    if value.get("ok") is not True:
        raise AdminError(
            "Maintenance worker refused changed runtime, backup or source; inspect the private journal"
        )
    return {k: v for k, v in value.items() if k != "ok"}


def journal(config, operation):
    if not re.fullmatch(r"[a-f0-9]{32}", operation):
        raise AdminError("Invalid maintenance operation identifier")
    return config.private / "maintenance" / (operation + ".json")


def save(config, record, stage):
    record.update(stage=stage, updated_at=datetime.now(UTC).isoformat())
    _write_private(journal(config, record["operation"]), config.private, record)
    if os.name != "nt":
        fd = os.open(config.private / "maintenance", os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def read_record(config, operation):
    record = _read_json(journal(config, operation), config.private)
    keys = {
        "schema",
        "operation",
        "server",
        "target",
        "binding",
        "settings",
        "operator_root",
        "created_at",
        "updated_at",
        "stage",
        "initial",
        "runtime",
        "checkpoint",
        "backup_operation",
        "proof",
        "start_requested_at",
        "resumed",
    }
    if (
        type(record.get("schema")) is not int
        or record.get("schema") != 1
        or record.get("operation") != operation
        or set(record) - keys
        or record.get("stage") not in STAGES
    ):
        raise AdminError("Invalid maintenance journal")
    return record


def status(record):
    return {
        "ok": True,
        "operation": record["operation"],
        "server": record["server"],
        "stage": record["stage"],
        "backup_operation": record.get("backup_operation"),
        "container": {
            "name": record["target"]["container"],
            "id": record["initial"]["container"],
        },
        "data_volume": record["target"]["data_volume"],
        "store_volume": record["target"]["store_volume"],
        "runtime_sha256": record["runtime"]["runtime_sha256"],
        "same_container_only": True,
        "ready_for_players": False,
    }


def current(config, record):
    backups.local_engine()
    server = record["server"]
    if (
        backups.target_for(config, server) != record["target"]
        or binding(config, server) != record["binding"]
        or str(config.servers[server]) != record["operator_root"]
    ):
        raise AdminError("Maintenance configuration changed after planning")
    value = snapshot(record["target"], record["binding"])
    for key in ("container", "image", "created", "restart_count", "source", "store"):
        if value[key] != record["initial"][key]:
            raise AdminError("Maintenance container or volume identity changed")
    return value


def plan(config, server, environment=None):
    with backups.locked(config):
        policy = settings(environment)
        target, endpoint = backups.target_for(config, server), binding(config, server)
        backups.local_engine()
        folder = config.private / "maintenance"
        folder.mkdir(mode=0o700, exist_ok=True)
        paths = list(folder.iterdir())
        if len(paths) >= policy["journal_count"]:
            raise AdminError(
                "Maintenance journal limit reached; archive terminal journals"
            )
        for path in paths:
            other = read_record(config, path.stem)
            if other["server"] == server and other["stage"] not in TERMINAL:
                raise AdminError(
                    "Reconcile or cancel the existing maintenance window first"
                )
        record = {
            "schema": 1,
            "operation": uuid4().hex,
            "server": server,
            "target": target,
            "binding": endpoint,
            "settings": policy,
            "operator_root": str(config.servers[server]),
            "created_at": datetime.now(UTC).isoformat(),
        }
        record["initial"] = snapshot(target, endpoint)
        if not record["initial"]["running"]:
            raise AdminError("New maintenance windows require the running source")
        console, password = credential(config, server)
        RecoveryConsole(console, password).ready()
        record["runtime"] = worker(record, "runtime")
        if current(config, record) != record["initial"]:
            raise AdminError("Source changed during maintenance planning")
        save(config, record, "planned")
        return status(record)


def wait_stopped(config, record):
    deadline = time.monotonic() + record["settings"]["stop_timeout_seconds"]
    while True:
        value = current(config, record)
        if value["started"] != record["initial"]["started"]:
            raise AdminError("Source restarted during maintenance stop")
        if not value["running"]:
            point = backups.checkpoint(record["target"])
            if worker(record, "runtime") != record["runtime"]:
                raise AdminError("Runtime changed during maintenance stop")
            if backups.checkpoint(record["target"]) != point:
                raise AdminError("Source changed while accepting the clean stop")
            record["checkpoint"] = point
            save(config, record, "stopped")
            return status(record)
        if time.monotonic() >= deadline:
            raise AdminError(
                "Stop is unconfirmed; inspect status and reconcile; no force kill was sent"
            )
        time.sleep(record["settings"]["poll_milliseconds"] / 1000)


def wait_started(config, record):
    deadline = time.monotonic() + record["settings"]["start_timeout_seconds"]
    boot = None
    healthy_since = None
    console, password = credential(config, record["server"])
    while True:
        value = current(config, record)
        if not value["running"] or value["started"] == record["initial"]["started"]:
            raise AdminError("Start is unconfirmed; reconcile without repeating start")
        started = datetime.fromisoformat(value["started"].replace("Z", "+00:00"))
        # Host and Docker VM clocks can differ even on a local engine. Both
        # lifecycle timestamps must come from that same engine; the controller's
        # start_requested_at is an audit field, not a cross-clock admission gate.
        finished = datetime.fromisoformat(
            record["checkpoint"]["finished"].replace("Z", "+00:00")
        )
        if started <= finished:
            raise AdminError("Container boot does not follow the recorded clean stop")
        if boot is not None and value != boot:
            raise AdminError("Source lifecycle changed during start readiness")
        boot = value
        logs = backups.docker(
            "logs", "--since", value["started"], "--tail", "4000", value["container"]
        )
        if len(logs.encode()) > 8 * 1024**2 or any(
            s in logs
            for s in (
                "Encountered an unexpected exception",
                "This crash report has been saved to:",
            )
        ):
            raise AdminError("New server boot has fatal or oversized logs")
        try:
            if re.search(r"Done \([^\r\n]{1,64}\)!", logs):
                RecoveryConsole(console, password).ready()
                if current(config, record) != boot:
                    raise AdminError("Source changed after readiness")
                now = time.monotonic()
                if healthy_since is None:
                    healthy_since = now
                if now - healthy_since >= record["settings"]["ready_stable_seconds"]:
                    record["resumed"] = boot
                    save(config, record, "complete")
                    return status(record)
            else:
                healthy_since = None
        except ConsoleError, OSError, UnicodeError:
            healthy_since = None
        if time.monotonic() >= deadline:
            raise AdminError(
                "Readiness timed out; inspect and reconcile the same start intent"
            )
        time.sleep(record["settings"]["poll_milliseconds"] / 1000)


def execute(config, operation, action, *, backup_operation=None, environment=None):
    with backups.locked(config):
        record = read_record(config, operation)
        if action == "status":
            return status(record)
        value = current(config, record)
        if action == "cancel":
            if record["stage"] not in {"planned", "stopped"} or (
                value != record["initial"]
                if record["stage"] == "planned"
                else backups.checkpoint(record["target"]) != record["checkpoint"]
            ):
                raise AdminError("Cannot cancel an uncertain or changed lifecycle")
            save(config, record, "cancelled")
            return status(record)
        if action == "reconcile":
            if record["stage"] == "stop-requested":
                return wait_stopped(config, record)
            if record["stage"] == "start-requested":
                return wait_started(config, record)
            raise AdminError("No maintenance intent needs reconciliation")
        if action == "stop":
            return request_stop(config, record, value, environment)
        if action == "start":
            return request_start(config, record, backup_operation)
        raise AdminError("Unsupported maintenance action")


def request_stop(config, record, value, environment):
    age = (
        datetime.now(UTC) - datetime.fromisoformat(record["created_at"])
    ).total_seconds()
    if (
        record["stage"] != "planned"
        or value != record["initial"]
        or record["settings"] != settings(environment)
        or not 0 <= age <= record["settings"]["plan_ttl_seconds"]
        or worker(record, "runtime") != record["runtime"]
    ):
        raise AdminError("Maintenance plan is stale, changed or already attempted")
    console, password = credential(config, record["server"])
    RecoveryConsole(console, password).ready()
    if current(config, record) != record["initial"]:
        raise AdminError("Source changed before stop intent")
    save(config, record, "stop-requested")
    # Only the verified Docker clean checkpoint can confirm stop.
    with contextlib.suppress(ConsoleError, OSError, UnicodeError):
        console_stop(console, password)
    return wait_stopped(config, record)


def request_start(config, record, backup_operation):
    if record["stage"] != "stopped":
        raise AdminError("Unsupported maintenance stage or action")
    if backups.checkpoint(record["target"]) != record["checkpoint"]:
        raise AdminError("Stopped source changed after maintenance")
    backup = backups.read_record(config, backup_operation or "")
    if (
        backup["stage"] != "complete"
        or backup["server"] != record["server"]
        or backup["target"] != record["target"]
        or backup["operator_root"] != record["operator_root"]
        or backup["checkpoint"] != record["checkpoint"]
        or backup["source"]["runtime_sha256"] != record["runtime"]["runtime_sha256"]
    ):
        raise AdminError(
            "Start requires a completed backup of this exact stopped source"
        )
    proof = worker(record, "proof", backup)
    if backups.checkpoint(record["target"]) != record["checkpoint"]:
        raise AdminError("Source changed while verifying the start backup")
    record.update(
        backup_operation=backup_operation,
        proof=proof,
        start_requested_at=datetime.now(UTC).isoformat(),
    )
    save(config, record, "start-requested")
    # Use the frozen immutable ID, never docker compose up or a mutable name.
    backups.docker("start", record["initial"]["container"])
    return wait_started(config, record)


def add_maintenance_parser(actions):
    parser = actions.add_parser(
        "maintenance", help="Owner graceful stop and verified same-container restart"
    )
    sub = parser.add_subparsers(dest="maintenance_action", required=True)
    sub.add_parser("plan").add_argument("--server", required=True)
    for action in ("stop", "status", "start", "reconcile", "cancel"):
        command = sub.add_parser(action)
        command.add_argument("--operation", required=True)
        if action == "start":
            command.add_argument("--backup-operation", required=True)


def run_maintenance(config, args):
    if args.maintenance_action == "plan":
        return plan(config, args.server)
    return execute(
        config,
        args.operation,
        args.maintenance_action,
        backup_operation=getattr(args, "backup_operation", None),
    )
