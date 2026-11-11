"""Read-only owner accounting; no retention, scheduler or world mutation."""

import json
import os
from uuid import uuid4

from omk import (
    admin_backups as backups,
    owner_volumes,
)
from omk.admin import AdminError
from omk.profiles import PROJECT_ROOT


def limits(environment=None):
    env = os.environ if environment is None else environment
    result = {}
    for key, default, maximum in (
        ("MAX_ENTRIES", 200000, 1000000),
        ("MAX_DEPTH", 64, 128),
    ):
        value = env.get("OMK_STORAGE_" + key, str(default))
        if (
            not isinstance(value, str)
            or not value.isascii()
            or not value.isdecimal()
            or len(value) > 9
        ):
            raise AdminError("Invalid OMK_STORAGE_" + key)
        number = int(value)
        if not 1 <= number <= maximum:
            raise AdminError("Invalid OMK_STORAGE_" + key)
        result[key.lower()] = number
    return result


def targets(config, server):
    source = backups.target_for(config, server)
    values = [
        ("source", source["data_volume"], backups.volume(source)),
        ("store", source["store_volume"], backups.volume(source, store=True)),
    ]
    for filename, role in (
        ("resource-resets.toml", "reset"),
        ("restores.toml", "restore"),
    ):
        path = config.private / filename
        if path.exists() or path.is_symlink():
            entries = owner_volumes.document(config, filename)
            if server in entries:
                target = owner_volumes.target_for(config, server, source, filename)
                # Count the explicitly owned volume even when a reviewed candidate
                # container exists. Read-only observation does not require unused=True.
                rows = json.loads(
                    backups.docker("volume", "inspect", target["data_volume"])
                )
                if (
                    len(rows) != 1
                    or rows[0]["Name"] != target["data_volume"]
                    or (rows[0].get("Labels") or {}).get(target["label"])
                    != target["owner"]
                ):
                    raise AdminError(
                        "Storage target is missing or no longer explicitly owned"
                    )
                values.append(
                    (
                        role,
                        target["data_volume"],
                        {
                            "created": rows[0]["CreatedAt"],
                            "owner": target["owner"],
                        },
                    )
                )
    if len({value[1] for value in values}) != len(values):
        raise AdminError("Storage resources alias")
    return source, values


def inspect(config, server, environment=None):
    with backups.locked(config):
        backups.local_engine()
        source, values = targets(config, server)
        policy = backups.settings(environment)
        request = {
            "schema": 1,
            "roles": [v[0] for v in values],
            "world": source["world"],
            "limits": limits(environment),
        }
        args = [
            "run",
            "--rm",
            "--pull",
            "never",
            "-i",
            "--name",
            "omk-storage-" + uuid4().hex,
            "--label",
            "omkality.storage.inspection=true",
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
            "--log-driver",
            "none",
        ]
        for role, name, _identity in values:
            args += [
                "--mount",
                f"type=volume,source={name},target=/storage/{role},readonly,volume-nocopy",
            ]
        args += [
            "--mount",
            f"type=bind,source={PROJECT_ROOT/'omk'},target=/src/omk,readonly",
            "--workdir",
            "/src",
            "--env",
            "PYTHONDONTWRITEBYTECODE=1",
            backups.IMAGE,
            "python",
            "-m",
            "omk.storage_inventory",
        ]
        raw = backups.docker(
            *args,
            stdin=json.dumps(request),
            timeout=policy["timeout_seconds"],
            allowed_codes=(0, 1),
        )
        if len(raw.encode()) > 32768:
            raise AdminError("Storage report exceeds bound")
        response = json.loads(raw)
        if response.get("ok") is not True or not isinstance(
            response.get("result"), dict
        ):
            raise AdminError(
                "Storage inspection refused or changed; retry in a quiet window"
            )
        if targets(config, server) != (source, values):
            raise AdminError(
                "Storage identity or configuration changed during inspection"
            )
        result = response["result"]
        if result.get("schema") != 1 or result.get("read_only") is not True:
            raise AdminError("Invalid storage inventory response")
        result.update(
            ok=True, server=server, configured_reserve_bytes=policy["reserve_bytes"]
        )
        for filesystem in result["filesystems"]:
            filesystem["below_reserve"] = (
                filesystem["available_bytes"] < policy["reserve_bytes"]
            )
        return result


def add_parser(actions):
    sub = actions.add_parser(
        "storage", help="Owner read-only volume space accounting"
    ).add_subparsers(dest="storage_action", required=True)
    sub.add_parser("inspect").add_argument("--server", required=True)


def run(config, args):
    return inspect(config, args.server)
