"""Owner-only cold Docker backups. No stop/start/restore or public API endpoint."""

import contextlib
import json
import os
import re
import subprocess
import tomllib
from datetime import UTC, datetime
from uuid import uuid4

from omk.admin import AdminError, _private_path, _read_json, _write_private
from omk.cold_backup_worker import digest
from omk.diagnostics import regular
from omk.profiles import PROJECT_ROOT

IMAGE = "python:3.14.2-slim@sha256:1a3c6dbfd2173971abba880c3cc2ec4643690901f6ad6742d0827bae6cefc925"
RESOURCE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")
PINS = re.compile(r"[^\s,]+@sha256:[a-f0-9]{64}")


def settings(environment=None):
    env = os.environ if environment is None else environment
    result = {}
    for key, default, minimum, maximum in (
        ("MAX_BYTES", 48 * 1024**3, 1, 1024**4),
        ("STAGING_BYTES", 32 * 1024**3, 1, 1024**4),
        ("RESERVE_BYTES", 16 * 1024**3, 1, 1024**4),
        ("WORLD_MAX_BYTES", 16 * 1024**3, 1, 1024**4),
        ("MAX_COUNT", 12, 2, 128),
        ("JOURNAL_COUNT", 256, 8, 1000),
        ("TIMEOUT_SECONDS", 1800, 10, 7200),
        ("HELPER_MEMORY_MIB", 512, 128, 2048),
        ("HELPER_CPUS", 1, 1, 8),
        ("PLAN_TTL_SECONDS", 3600, 60, 86400),
    ):
        raw = env.get("OMK_BACKUP_" + key, str(default))
        if (
            not isinstance(raw, str)
            or not raw.isascii()
            or not raw.isdecimal()
            or len(raw) > 15
        ):
            raise AdminError("Invalid OMK_BACKUP_" + key)
        value = int(raw)
        if not minimum <= value <= maximum:
            raise AdminError("Invalid OMK_BACKUP_" + key)
        result[key.lower()] = value
    return result


def target_for(config, server):
    if server not in config.servers:
        raise AdminError("Server is not in the operator allowlist")
    path = config.private / "backups.toml"
    if not regular(path, config.private) or (
        os.name != "nt" and path.stat().st_mode & 0o077
    ):
        raise AdminError("Use a private mode-600 .omk-admin/backups.toml")
    with path.open("rb") as file:
        raw = file.read(65537)
    if len(raw) > 65536:
        raise AdminError("Backup configuration exceeds limit")
    doc = tomllib.loads(raw.decode())
    if set(doc) != {"schema", "servers"} or doc["schema"] != 1:
        raise AdminError("Invalid backup configuration schema")
    item = doc["servers"].get(server, {})
    keys = {
        "container",
        "data_volume",
        "store_volume",
        "label",
        "source_owner",
        "store_owner",
        "world",
        "image",
        "release",
    }
    if set(item) != keys or any(not isinstance(value, str) for value in item.values()):
        raise AdminError("Invalid backup target")
    if any(
        not RESOURCE.fullmatch(item[key])
        for key in (
            "container",
            "data_volume",
            "store_volume",
            "source_owner",
            "store_owner",
            "release",
        )
    ):
        raise AdminError("Invalid backup resource identifier")
    if (
        item["data_volume"] == item["store_volume"]
        or not re.fullmatch(r"omkality\.[a-z0-9_.-]{1,64}", item["label"])
        or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", item["world"])
        or not PINS.fullmatch(item["image"])
    ):
        raise AdminError("Invalid backup identity, image pin or world name")
    return dict(item)


def docker(*args, stdin=None, timeout=30):
    try:
        value = subprocess.run(
            ["docker", *args],
            input=stdin,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            encoding="utf-8",
            errors="replace",
        )
    except OSError, subprocess.SubprocessError:
        raise AdminError(
            "Docker operation unavailable or timed out; inspect backup journal"
        ) from None
    if value.returncode:
        raise AdminError("Docker operation failed; inspect backup journal")
    return value.stdout + value.stderr if args[0] == "logs" else value.stdout


def local_engine():
    context = os.environ.get("DOCKER_CONTEXT", "")
    endpoint = os.environ.get("DOCKER_HOST", "") if not context else ""
    if not endpoint:
        rows = json.loads(
            docker("context", "inspect", context)
            if context
            else docker("context", "inspect")
        )
        endpoint = rows[0]["Endpoints"]["docker"]["Host"]
    if (
        not endpoint.startswith(("unix://", "npipe://"))
        or docker("info", "--format", "{{.OSType}}").strip() != "linux"
    ):
        raise AdminError("Cold backups require a local Linux Docker engine")


def volume(target, store=False):
    key, owner = (
        ("store_volume", "store_owner") if store else ("data_volume", "source_owner")
    )
    rows = json.loads(docker("volume", "inspect", target[key]))
    if (
        len(rows) != 1
        or rows[0]["Name"] != target[key]
        or (rows[0].get("Labels") or {}).get(target["label"]) != target[owner]
    ):
        raise AdminError("Docker volume identity is not explicitly owned")
    return {
        key: target[key],
        "created": rows[0]["CreatedAt"],
        "owner": owner + ":" + target[owner],
    }


def checkpoint(target):
    # Only metadata whitelist below enters the journal; never Config.Env/Args.
    rows = json.loads(docker("inspect", "--type", "container", target["container"]))
    if len(rows) != 1:
        raise AdminError("Ambiguous source container")
    data = rows[0]
    state, host = data["State"], data["HostConfig"]
    if (
        (data["Config"].get("Labels") or {}).get(target["label"])
        != target["source_owner"]
        or data["Config"]["Image"] != target["image"]
        or state.get("Status") != "exited"
        or state.get("Running") is not False
        or state.get("OOMKilled") is not False
        or state.get("ExitCode") != 0
        or host.get("RestartPolicy", {}).get("Name") not in {"no", ""}
    ):
        raise AdminError(
            "Cold backup requires the owned pinned container, clean exit and disabled automatic restart"
        )
    mounts = [m for m in data["Mounts"] if m["Destination"] == "/srv"]
    if (
        len(mounts) != 1
        or mounts[0].get("Name") != target["data_volume"]
        or mounts[0]["Type"] != "volume"
        or any(m["Destination"].startswith("/srv/") for m in data["Mounts"])
    ):
        raise AdminError("Unexpected source data mounts")
    active = docker("ps", "-q", "--filter", "volume=" + target["data_volume"])
    if active.strip():
        raise AdminError("Source volume is mounted by a running container")
    source = volume(target)
    store = volume(target, True)
    log_config = host.get("LogConfig", {})
    options = log_config.get("Config", {})
    maximum = re.fullmatch(r"([0-9]{1,5})([km])", options.get("max-size", ""))
    count = options.get("max-file", "")
    if (
        log_config.get("Type") != "local"
        or maximum is None
        or not count.isdecimal()
        or not 1 <= int(count) <= 4
        or int(maximum[1]) * {"k": 1024, "m": 1024**2}[maximum[2]] > 16 * 1024**2
    ):
        raise AdminError("Source requires bounded Docker local logs before backup")
    logs = docker("logs", "--tail", "4000", target["container"])
    if (
        not logs
        or len(logs.encode()) > 8 * 1024**2
        or "Stopping server" not in logs
        or any(
            marker in logs
            for marker in (
                "Encountered an unexpected exception",
                "This crash report has been saved to:",
            )
        )
    ):
        raise AdminError("Source stop log is missing, oversized or fatal")
    return {
        "container": data["Id"],
        "image": data["Image"],
        "created": data["Created"],
        "started": state["StartedAt"],
        "finished": state["FinishedAt"],
        "restart_count": data["RestartCount"],
        "source": source,
        "store": store,
        "stop_log_sha256": digest(logs),
    }


def worker(target, request):
    volume(target, True)
    args = [
        "run",
        "--rm",
        "--pull",
        "never",
        "-i",
        "--name",
        "omk-cold-worker-" + uuid4().hex,
        "--label",
        "omkality.backup.operation=" + request["operation"],
        "--network",
        "none",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges:true",
        "--memory",
        str(request["settings"]["helper_memory_mib"]) + "m",
        "--cpus",
        str(request["settings"]["helper_cpus"]),
        "--pids-limit",
        "32",
        "--mount",
        f"type=volume,source={target['store_volume']},target=/backup",
        "--mount",
        f"type=bind,source={PROJECT_ROOT/'omk'},target=/src/omk,readonly",
        "--workdir",
        "/src",
        "--env",
        "PYTHONDONTWRITEBYTECODE=1",
    ]
    if request["action"] in {"plan", "prepare"}:
        volume(target)
        args += [
            "--mount",
            f"type=volume,source={target['data_volume']},target=/server,readonly",
        ]
    raw = docker(
        *args,
        IMAGE,
        "python",
        "-m",
        "omk.cold_backup_worker",
        stdin=json.dumps(request),
        timeout=request["settings"]["timeout_seconds"],
    )
    if len(raw) > 65536:
        raise AdminError("Backup worker response exceeded limit")
    result = json.loads(raw)
    if result.get("ok") is not True:
        raise AdminError(
            "Backup worker refused the operation; previous verified copies remain available"
        )
    return {key: value for key, value in result.items() if key != "ok"}


@contextlib.contextmanager
def locked(config):
    path = config.private / "backups.lock"
    try:
        with path.open("xb") as file:
            file.write(b"0")
        path.chmod(0o600)
    except FileExistsError:
        pass
    if not regular(path, config.private):
        raise AdminError("Invalid backup lock")
    with path.open("r+b") as file:
        if os.name == "nt":
            import msvcrt  # noqa: PLC0415

            msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl  # noqa: PLC0415

            fcntl.flock(file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            if os.name == "nt":
                file.seek(0)
                msvcrt.locking(file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(file.fileno(), fcntl.LOCK_UN)


def journal(config, operation):
    if not re.fullmatch(r"[a-f0-9]{32}", operation):
        raise AdminError("Invalid backup operation identifier")
    return config.private / "backups" / (operation + ".json")


def save(config, record, stage):
    record.update(stage=stage, updated_at=datetime.now(UTC).isoformat())
    if len(json.dumps(record).encode()) > 65536:
        raise AdminError("Backup journal exceeded limit")
    _write_private(journal(config, record["operation"]), config.private, record)
    if os.name != "nt":
        fd = os.open(config.private / "backups", os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def request_for(record, action):
    value = dict(record)
    value["action"] = action
    value["policy"] = {
        key: record["settings"][key]
        for key in ("max_bytes", "max_count", "staging_bytes", "reserve_bytes")
    }
    value["world_max_bytes"] = record["settings"]["world_max_bytes"]
    value["world"] = record["target"]["world"]
    return value


def plan(config, server, environment=None):
    with locked(config):
        policy = settings(environment)
        target = target_for(config, server)
        local_engine()
        folder = config.private / "backups"
        folder.mkdir(exist_ok=True, mode=0o700)
        rows = list(folder.iterdir())
        if len(rows) >= policy["journal_count"]:
            raise AdminError(
                "Backup journal limit reached; archive completed journals before planning"
            )
        for path in rows:
            value = _read_json(
                _private_path(config.private, str(path.relative_to(config.private))),
                config.private,
            )
            if value.get("stage") not in {"planned", "complete"}:
                raise AdminError(
                    "Finish or inspect the previous incomplete backup before planning"
                )
        record = {
            "schema": 1,
            "operation": uuid4().hex,
            "server": server,
            "target": target,
            "settings": policy,
            "created_at": datetime.now(UTC).isoformat(),
            "operator_root": str(config.servers[server]),
        }
        record["checkpoint"] = checkpoint(target)
        record.update(worker(target, request_for(record, "plan")))
        if checkpoint(target) != record["checkpoint"]:
            raise AdminError("Source lifecycle changed during backup planning")
        save(config, record, "planned")
        return {"ok": True, **record}


def run(config, operation, *, finish=False, environment=None):
    with locked(config):
        record = _read_json(journal(config, operation), config.private)
        if record.get("schema") != 1 or record.get("operation") != operation:
            raise AdminError("Invalid backup journal")
        target = target_for(config, record["server"])
        local_engine()
        if volume(target, True) != record["checkpoint"]["store"]:
            raise AdminError("Backup store volume was replaced after planning")
        if (
            target != record["target"]
            or str(config.servers[record["server"]]) != record["operator_root"]
        ):
            raise AdminError("Backup target changed after plan")
        if finish:
            if (
                record["stage"]
                not in {"publishing", "published", "acknowledging", "incomplete"}
                or "prepared" not in record
            ):
                raise AdminError(
                    "No prepared publication to reconcile; inspect retained staging"
                )
            record["result"] = worker(target, request_for(record, "recover"))
        else:
            age = (
                datetime.now(UTC) - datetime.fromisoformat(record["created_at"])
            ).total_seconds()
            if (
                record["stage"] != "planned"
                or record["settings"] != settings(environment)
                or not 0 <= age <= record["settings"]["plan_ttl_seconds"]
                or checkpoint(target) != record["checkpoint"]
            ):
                raise AdminError("Backup plan is stale, changed or already attempted")
            save(config, record, "preparing")
            try:
                record["prepared"] = worker(target, request_for(record, "prepare"))
                if checkpoint(target) != record["checkpoint"]:
                    raise AdminError(
                        "Source restarted during backup; staged copy will not be published"
                    )
                save(config, record, "publishing")
                record["result"] = worker(target, request_for(record, "publish"))
            except Exception as error:
                record["failure_type"] = type(error).__name__
                save(config, record, "incomplete")
                raise AdminError(
                    "Backup incomplete; inspect journal and retained staging; never repeat run blindly"
                ) from None
        save(config, record, "published")
        save(config, record, "acknowledging")
        worker(target, request_for(record, "acknowledge"))
        save(config, record, "complete")
        return {
            "ok": True,
            "operation": operation,
            "stage": "complete",
            "snapshot": record["result"],
        }


def add_backup_parser(actions):
    parser = actions.add_parser(
        "backups", help="Owner cold Docker backups; explicit stopped server only"
    )
    sub = parser.add_subparsers(dest="backup_action", required=True)
    for action in ("plan", "list"):
        sub.add_parser(action).add_argument("--server", required=True)
    for action in ("run", "status", "finish"):
        sub.add_parser(action).add_argument("--operation", required=True)


def run_backups(config, args):
    if args.backup_action == "plan":
        return plan(config, args.server)
    if args.backup_action in {"run", "finish"}:
        return run(config, args.operation, finish=args.backup_action == "finish")
    if args.backup_action == "status":
        return {
            "ok": True,
            **_read_json(journal(config, args.operation), config.private),
        }
    target = target_for(config, args.server)
    local_engine()
    record = {"operation": uuid4().hex, "target": target, "settings": settings()}
    return {"ok": True, **worker(target, request_for(record, "list"))}
