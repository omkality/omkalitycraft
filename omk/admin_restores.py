"""Closed owner plan/apply/verify for a separate Linux restore volume.

An explicit stopped source and recent verified backup are prerequisites. No
automatic lifecycle, volume creation/adoption, promotion or deletion is provided.
"""

import json
import re
from datetime import UTC, datetime
from uuid import uuid4

from omk import (
    admin_backups as backups,
    owner_volumes,
)
from omk.admin import AdminError, _read_json, _write_private
from omk.backup_store import _sync_directory
from omk.profiles import PROJECT_ROOT


def target_for(config, server, source):
    return owner_volumes.target_for(config, server, source, "restores.toml")


def destination(target):
    return owner_volumes.destination(target)


def worker(record, action):
    source, target, settings = record["source"], record["target"], record["settings"]
    request = {
        "action": action,
        "operation": record["operation"],
        "world": source["world"],
        "snapshot": record["snapshot"],
        "world_max_bytes": settings["world_max_bytes"],
        "policy": {
            k: settings[k]
            for k in ("max_bytes", "max_count", "staging_bytes", "reserve_bytes")
        },
    }
    if "expected" in record:
        request["expected"] = record["expected"]
    args = [
        "run",
        "--rm",
        "--pull",
        "never",
        "-i",
        "--name",
        "omk-restore-worker-" + uuid4().hex,
        "--label",
        "omkality.restore.operation=" + record["operation"],
        "--network",
        "none",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges:true",
        "--memory",
        str(settings["helper_memory_mib"]) + "m",
        "--cpus",
        str(settings["helper_cpus"]),
        "--pids-limit",
        "32",
        "--mount",
        f"type=volume,source={source['store_volume']},target=/backup,readonly",
        "--mount",
        f"type=volume,source={source['data_volume']},target=/current,readonly",
        "--mount",
        f"type=volume,source={target['data_volume']},target=/restore"
        + ("" if action == "apply" else ",readonly"),
        "--mount",
        f"type=bind,source={PROJECT_ROOT/'omk'},target=/src/omk,readonly",
    ]
    for filename in ("__init__.py", "nbt.py"):
        args += [
            "--mount",
            f"type=bind,source={PROJECT_ROOT/'launcher'/filename},target=/src/launcher/{filename},readonly",
        ]
    text = backups.docker(
        *args,
        "--workdir",
        "/src",
        "--env",
        "PYTHONDONTWRITEBYTECODE=1",
        backups.IMAGE,
        "python",
        "-m",
        "omk.owner_restore_worker",
        stdin=json.dumps(request),
        timeout=settings["timeout_seconds"],
        allowed_codes=(0, 1),
    )
    if len(text.encode()) > 65536:
        raise AdminError("Restore worker response exceeds limit")
    result = json.loads(text)
    if result.get("ok") is not True or not isinstance(result.get("result"), dict):
        kind = result.get("error_type", "InvalidResponse")
        if not isinstance(kind, str) or not re.fullmatch(r"[A-Za-z]{1,64}", kind):
            kind = "InvalidResponse"
        raise AdminError(
            "Restore worker refused the operation ("
            + kind
            + "); inspect journal and retained target"
        )
    return result["result"]


def journal(config, operation):
    if not re.fullmatch(r"[a-f0-9]{32}", operation):
        raise AdminError("Invalid restore operation identifier")
    return config.private / "restores" / (operation + ".json")


def save(config, record, stage):
    record.update(stage=stage, updated_at=datetime.now(UTC).isoformat())
    if len(json.dumps(record).encode()) > 65536:
        raise AdminError("Restore journal exceeds limit")
    _write_private(journal(config, record["operation"]), config.private, record)
    _sync_directory(config.private / "restores")


def read_record(config, operation):
    value = _read_json(journal(config, operation), config.private)
    allowed = {
        "schema",
        "operation",
        "server",
        "source",
        "target",
        "settings",
        "snapshot",
        "created_at",
        "operator_root",
        "checkpoint",
        "destination",
        "expected",
        "stage",
        "updated_at",
        "result",
        "failure_type",
        "failure_reason",
    }
    if (
        value.get("schema") != 1
        or value.get("operation") != operation
        or set(value) - allowed
    ):
        raise AdminError("Invalid restore journal schema or identity")
    return value


def _stable(config, record):
    source = backups.target_for(config, record["server"])
    target = target_for(config, record["server"], source)
    if (
        source != record["source"]
        or target != record["target"]
        or str(config.servers[record["server"]]) != record["operator_root"]
        or backups.checkpoint(source) != record["checkpoint"]
        or destination(target) != record["destination"]
    ):
        raise AdminError(
            "Restore configuration, source lifecycle or destination changed"
        )


def plan(config, server, snapshot, environment=None):
    if not isinstance(snapshot, str) or not re.fullmatch(
        r"snapshot-[a-f0-9]{32}", snapshot
    ):
        raise AdminError("Invalid selected restore snapshot")
    with backups.locked(config):
        source = backups.target_for(config, server)
        target = target_for(config, server, source)
        backups.local_engine()
        settings = backups.settings(environment)
        folder = config.private / "restores"
        folder.mkdir(exist_ok=True, mode=0o700)
        rows = list(folder.iterdir())
        if len(rows) >= settings["journal_count"]:
            raise AdminError(
                "Restore journal limit reached; archive reviewed completed records"
            )
        if any(
            _read_json(path, config.private).get("stage") not in {"planned", "staged"}
            for path in rows
        ):
            raise AdminError(
                "Inspect the previous incomplete restore before planning another"
            )
        record = {
            "schema": 1,
            "operation": uuid4().hex,
            "server": server,
            "source": source,
            "target": target,
            "settings": settings,
            "snapshot": snapshot,
            "created_at": datetime.now(UTC).isoformat(),
            "operator_root": str(config.servers[server]),
            "checkpoint": backups.checkpoint(source),
            "destination": destination(target),
        }
        record["expected"] = worker(record, "plan")
        _stable(config, record)
        save(config, record, "planned")
        return {"ok": True, **record}


def run(config, operation, *, verify=False, environment=None):
    with backups.locked(config):
        record = read_record(config, operation)
        backups.local_engine()
        _stable(config, record)
        if verify:
            if record["stage"] not in {"applying", "incomplete", "staged"}:
                raise AdminError("No attempted restore to verify")
        else:
            age = (
                datetime.now(UTC) - datetime.fromisoformat(record["created_at"])
            ).total_seconds()
            if (
                record["stage"] != "planned"
                or record["settings"] != backups.settings(environment)
                or not (0 <= age <= record["settings"]["plan_ttl_seconds"])
            ):
                raise AdminError("Restore plan is stale, changed or already attempted")
            save(config, record, "applying")
        try:
            result = worker(record, "verify" if verify else "apply")
            _stable(config, record)
        except Exception as error:
            record["failure_type"] = type(error).__name__
            if isinstance(error, AdminError):
                record["failure_reason"] = str(error)
            save(config, record, "incomplete")
            raise AdminError(
                "Restore incomplete; retain target, inspect status and verify; never repeat apply"
            ) from None
        record["result"] = result
        save(config, record, "staged")
        return {"ok": True, "operation": operation, "stage": "staged", **result}


def add_restore_parser(actions):
    parser = actions.add_parser(
        "restores", help="Owner Linux restore staging; no lifecycle or promotion"
    )
    sub = parser.add_subparsers(dest="restore_action", required=True)
    planning = sub.add_parser("plan")
    planning.add_argument("--server", required=True)
    planning.add_argument("--snapshot", required=True)
    for action in ("apply", "verify", "status"):
        sub.add_parser(action).add_argument("--operation", required=True)


def run_restores(config, args):
    if args.restore_action == "plan":
        return plan(config, args.server, args.snapshot)
    if args.restore_action == "status":
        return {"ok": True, **read_record(config, args.operation)}
    return run(config, args.operation, verify=args.restore_action == "verify")
