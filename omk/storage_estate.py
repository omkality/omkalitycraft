"""Owner project census of all configured game volumes and explicit shared state."""

import json
import os
import re
import tomllib
from uuid import uuid4

from omk import (
    admin_backups as backups,
    admin_storage,
    owner_volumes,
)
from omk.admin import AdminError
from omk.estate_budget import assess, declared_limits
from omk.fs import regular
from omk.profiles import PROJECT_ROOT
from omk.storage_policy import storage_plan

SHARED = {"auth", "content", "reports", "exports"}


def shared(config):
    path = config.private / "storage.toml"
    if not regular(path, config.private) or (
        os.name != "nt" and path.stat().st_mode & 0o077
    ):
        raise AdminError("Use explicit private mode-600 .omk-admin/storage.toml")
    with path.open("rb") as stream:
        raw = stream.read(16385)
    if len(raw) > 16384:
        raise AdminError("Project storage configuration exceeds bound")
    doc = tomllib.loads(raw.decode())
    if (
        set(doc) != {"schema", "volumes"}
        or type(doc["schema"]) is not int
        or doc["schema"] != 1
        or not isinstance(doc["volumes"], dict)
        or not 1 <= len(doc["volumes"]) <= 4
        or "auth" not in doc["volumes"]
        or set(doc["volumes"]) - SHARED
    ):
        raise AdminError(
            "Project storage requires explicitly owned auth and known shared roles"
        )
    for entry in doc["volumes"].values():
        if (
            not isinstance(entry, dict)
            or set(entry) != {"volume", "label", "owner"}
            or any(not isinstance(v, str) for v in entry.values())
            or not backups.RESOURCE.fullmatch(entry["volume"])
            or not backups.RESOURCE.fullmatch(entry["owner"])
            or not re.fullmatch(
                r"(?:omkality\.[a-z0-9_.-]{1,64}|com\.docker\.compose\.project)",
                entry["label"],
            )
        ):
            raise AdminError("Invalid explicit shared storage identity")
    return doc["volumes"]


def resources(config):
    configured = owner_volumes.document(config, "backups.toml")
    result = []
    for index, server in enumerate(sorted(configured)):
        source, values = admin_storage.targets(config, server)
        for role, name, identity in values:
            result.append(
                {
                    "id": f"server-{index}-{role}",
                    "role": role,
                    "server": server,
                    "world": source["world"],
                    "volume": name,
                    "identity": identity,
                }
            )
    for role, entry in sorted(shared(config).items()):
        rows = json.loads(backups.docker("volume", "inspect", entry["volume"]))
        if (
            len(rows) != 1
            or rows[0]["Name"] != entry["volume"]
            or (rows[0].get("Labels") or {}).get(entry["label"]) != entry["owner"]
        ):
            raise AdminError("Explicit shared storage is missing or no longer owned")
        result.append(
            {
                "id": "shared-" + role,
                "role": role,
                "server": None,
                "world": "world",
                "volume": entry["volume"],
                "identity": {"created": rows[0]["CreatedAt"], **entry},
            }
        )
    if not 3 <= len(result) <= 64 or len({e["volume"] for e in result}) != len(result):
        raise AdminError("Project volumes alias or exceed the census bound")
    return result


def worker(values, limits, policy):
    args = [
        "run",
        "--rm",
        "--pull",
        "never",
        "-i",
        "--name",
        "omk-project-storage-" + uuid4().hex,
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
    for entry in values:
        args += [
            "--mount",
            f"type=volume,source={entry['volume']},target=/storage/{entry['id']},readonly,volume-nocopy",
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
        "omk.estate_inventory",
    ]
    request = {
        "schema": 1,
        "resources": [{k: e[k] for k in ["id", "role", "world"]} for e in values],
        "limits": limits,
    }
    raw = backups.docker(
        *args,
        stdin=json.dumps(request),
        timeout=policy["timeout_seconds"],
        allowed_codes=(0, 1),
    )
    if len(raw.encode()) > 65536:
        raise AdminError("Project storage report exceeds bound")
    reply = json.loads(raw)
    if reply.get("ok") is not True or not isinstance(reply.get("result"), dict):
        raise AdminError(
            "Project storage changed or cannot be read; retry in a quiet window"
        )
    value = reply["result"]
    expected = {e["id"]: e["role"] for e in values}
    if (
        value.get("schema") != 1
        or value.get("read_only") is not True
        or len(value.get("resources", [])) != len(expected)
        or {e["id"]: e["role"] for e in value["resources"]} != expected
    ):
        raise AdminError("Project storage report differs from the requested census")
    return value


def inspect(config, environment=None):
    plan = storage_plan(environment)
    if not plan["ok"]:
        raise AdminError(plan["error"])
    with backups.locked(config):
        backups.local_engine()
        before = resources(config)
        policy = backups.settings(environment)
        report = worker(before, admin_storage.limits(environment), policy)
        if resources(config) != before:
            raise AdminError("Project storage configuration or volume identity changed")
        report["budget"] = assess(report, plan)
        servers = {e["server"] for e in before if e["server"] is not None}
        report["budget"]["declared_operation_limits"] = declared_limits(
            plan, policy, len(servers)
        )
        shared_roles = {e["role"] for e in before if e["server"] is None}
        report.update(
            ok=True,
            scope="configured-project-volumes",
            configured_servers=sorted(servers),
            unconfigured_servers=sorted(set(config.servers) - servers),
            shared_roles=sorted(shared_roles),
            missing_shared_roles=sorted(SHARED - shared_roles),
        )
        mapping = {e["id"]: e["server"] for e in before}
        for item in report["resources"]:
            item["server"] = mapping[item["id"]]
        return report
