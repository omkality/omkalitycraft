"""Owner-only inspection of stopped resource references; no reset implementation."""

import json
import re
from uuid import uuid4

from omk import admin_backups as backups
from omk.admin import AdminError
from omk.cold_backup_worker import digest
from omk.profiles import PROJECT_ROOT
from omk.resource_reset_inventory import validate_dimension


def _cleanup_failed_worker(name, operation):
    ids = backups.docker(
        "ps",
        "-aq",
        "--filter",
        "name=^/" + name + "$",
        "--filter",
        "label=omkality.resource.inspection=" + operation,
        "--no-trunc",
    ).split()
    if not ids:
        return
    if len(ids) != 1 or not re.fullmatch(r"[a-f0-9]{64}", ids[0]):
        raise AdminError("Ambiguous interrupted resource inspection helper")
    rows = json.loads(backups.docker("inspect", "--type", "container", ids[0]))
    if (
        len(rows) != 1
        or rows[0].get("Name") != "/" + name
        or (rows[0].get("Config", {}).get("Labels") or {}).get(
            "omkality.resource.inspection"
        )
        != operation
    ):
        raise AdminError("Interrupted inspection helper identity changed")
    backups.docker("rm", "--force", ids[0])


def worker(target, dimension, settings):
    operation = uuid4().hex
    name = "omk-resource-inspect-" + operation
    args = [
        "run",
        "--rm",
        "--pull",
        "never",
        "-i",
        "--name",
        name,
        "--label",
        "omkality.resource.inspection=" + operation,
        "--network",
        "none",
        "--read-only",
        "--log-driver",
        "none",
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
        f"type=volume,source={target['data_volume']},target=/server,readonly",
        "--workdir",
        "/src",
        "--env",
        "PYTHONDONTWRITEBYTECODE=1",
    ]
    for module in ("omk", "launcher", "profiles"):
        args += [
            "--mount",
            f"type=bind,source={PROJECT_ROOT/module},target=/src/{module},readonly",
        ]
    request = {
        "schema": 1,
        "action": "inspect",
        "world": target["world"],
        "dimension": dimension,
        "world_max_bytes": settings["world_max_bytes"],
    }
    try:
        raw = backups.docker(
            *args,
            backups.IMAGE,
            "python",
            "-m",
            "omk.resource_reset_worker",
            stdin=json.dumps(request),
            timeout=settings["timeout_seconds"],
            allowed_codes=(0, 1),
        )
    except BaseException:
        _cleanup_failed_worker(name, operation)
        raise
    if len(raw.encode()) > 65536:
        raise AdminError("Resource inspection response exceeded limit")
    result = json.loads(raw)
    if not isinstance(result, dict):
        raise AdminError("Invalid resource inspection worker response")
    if result.get("ok") is not True:
        kind = result.get("error_type", "InvalidResponse")
        if not isinstance(kind, str) or not re.fullmatch(r"[A-Za-z]{1,64}", kind):
            kind = "InvalidResponse"
        raise AdminError(
            "Resource inspection refused ("
            + kind
            + "); check runtime, ownership and data format"
        )
    value = result.get("result")
    if not isinstance(value, dict) or any(
        value.get(k) is not False
        for k in ("world_changes", "reset_plan", "can_apply", "backup_verified")
    ):
        raise AdminError("Unexpected non-inspection worker result")
    if (
        value.get("schema") != 1
        or value.get("adapter") != "dj2-ftb5.4-jed1.6-inspection-v1"
        or value.get("world") != target["world"]
        or not isinstance(value.get("resource_identity"), dict)
        or value["resource_identity"].get("dimension") != str(dimension)
        or not isinstance(value.get("world_inventory_sha256"), str)
        or not re.fullmatch(r"[a-f0-9]{64}", value["world_inventory_sha256"])
    ):
        raise AdminError("Inspection worker returned a different source identity")
    return value


def inspect(config, server, dimension, environment=None):
    try:
        validate_dimension(dimension)
    except ValueError:
        raise AdminError(
            "Only an allowlisted resource dimension can be inspected"
        ) from None
    with backups.locked(config):
        target = backups.target_for(config, server)
        backups.local_engine()
        settings = backups.settings(environment)
        before = backups.checkpoint(target)
        result = worker(target, dimension, settings)
        if (
            backups.target_for(config, server) != target
            or backups.checkpoint(target) != before
        ):
            raise AdminError(
                "Source lifecycle or configuration changed during inspection"
            )
    return {"ok": True, "server": server, "checkpoint_sha256": digest(before), **result}


def add_resource_reset_parser(actions):
    parser = actions.add_parser(
        "resource-resets", help="Read-only resource reference inspection; no wipe"
    )
    sub = parser.add_subparsers(dest="resource_reset_action", required=True)
    command = sub.add_parser("inspect")
    command.add_argument("--server", required=True)
    command.add_argument("--dimension", type=int, required=True)


def run_resource_reset(config, args):
    return inspect(config, args.server, args.dimension)
