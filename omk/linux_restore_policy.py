"""Current DJ2 access/FTB policy on a historical, stopped Linux replacement.

Only a fresh initialized target; source and backup are mounted read-only. No
Drasl state, credentials, lifecycle, overwrites of an existing service, or retry.
"""

import copy
import hashlib
import json
import os
import re
import shutil
import sys
from pathlib import Path

from omk import (
    ftb_restore_authority as ftb,
    ftb_restore_reconcile as reconcile,
    linux_world_restore as raw,
)
from omk.backup_store import _directory, _json_write, _sync_directory
from omk.cold_backup_worker import runtime_digest
from omk.fs import regular
from omk.stopped_world_backup import inventory

PLAN, DONE = raw.POLICY_MARKERS
STAGING = ".omk-current-policy-writing"
LISTS = ("ops.json", "banned-players.json", "banned-ips.json", "whitelist.json")
RANKS = "local/ftbutilities/ranks.txt"
MAX_FILE = 1024**2


def digest(data):
    return hashlib.sha256(data).hexdigest()


def _read(root, name, *, limit=MAX_FILE):
    path = root / name
    if not regular(path, root) or path.stat().st_size > limit:
        raise ValueError("Missing, linked or oversized current policy file")
    return path.read_bytes()


def _flag(data):
    try:
        text = data.decode("utf-8")
        values = re.findall(r"^white-list=(true|false)\r?$", text, re.M)
        if len(values) != 1 or b"\0" in data:
            raise ValueError("Invalid whitelist flag")
        return values[0]
    except UnicodeError:
        raise ValueError("Invalid current whitelist data") from None


def _current(root, world):
    data = {name: _read(root, name) for name in (*LISTS, RANKS)}
    try:
        for name in LISTS:
            rows = json.loads(data[name])
            if (
                not isinstance(rows, list)
                or len(rows) > 10000
                or any(not isinstance(row, dict) for row in rows)
            ):
                raise ValueError("Invalid current access list")
        if not data[RANKS].decode("utf-8").strip() or b"\0" in data[RANKS]:
            raise ValueError("Invalid current rank definitions")
    except ValueError, UnicodeError, RecursionError:
        raise ValueError("Invalid current access/rank data") from None
    props = _read(root, "server.properties")
    flag = _flag(props)
    records = ftb.read_staged(root, world_name=world)
    summary = {
        "files": {name: digest(value) for name, value in data.items()},
        "properties_sha256": digest(props),
        "whitelist": flag,
        "ftb_sha256": digest(
            json.dumps(ftb._canonical(records), sort_keys=True).encode()
        ),
        "runtime_sha256": runtime_digest(root),
    }
    return data, records, summary


def _expected(request, storage, target, current):
    identity = raw._request(request, target)
    _directory(current)
    if current.samefile(target) or raw._read(target / raw.OWNER) != identity:
        raise ValueError("Current policy source aliases target or ownership differs")
    ftb.check_runtime(current)
    ftb.check_runtime(target)
    archive, manifest = raw._selected(request, storage)
    # The raw receipt binds the historical source even after intentional changes.
    base = raw._read(target / raw.PLAN)
    if raw._read(target / raw.DONE) != base or base != {
        **identity,
        "snapshot": request["snapshot"],
        "sha256": manifest["sha256"],
        "files": len(manifest["files"]),
        "inventory_sha256": digest(
            json.dumps(manifest["files"], sort_keys=True).encode()
        ),
    }:
        raise ValueError("Historical world stage receipt differs from source")
    data, current_ftb, summary = _current(current, request["world"])
    historical = ftb.read_zip(
        archive, world_name=request["world"], path_policy="linux-server"
    )
    merged = reconcile.merged_records(current_ftb, historical)
    payload = dict(data)
    props = _read(target, "server.properties").decode("utf-8")
    if "\0" in props:
        raise ValueError("Invalid target properties")
    props = re.sub(r"^white-list=.*(?:\n|$)", "", props, flags=re.M)
    payload["server.properties"] = (
        props.rstrip() + "\nwhite-list=" + summary["whitelist"] + "\n"
    ).encode()
    expected_world = copy.deepcopy(manifest["files"])
    for name, record in merged.items():
        if record != historical[name]:
            relative = request["world"] + "/data/ftb_lib/" + name
            payload[relative] = reconcile._encoded(record)
            expected_world[relative] = {
                "bytes": len(payload[relative]),
                "sha256": digest(payload[relative]),
            }
    binding = {
        **identity,
        "adapter": "dj2-current-policy-v1",
        "snapshot_sha256": manifest["sha256"],
        "raw_receipt_sha256": digest((target / raw.DONE).read_bytes()),
        "current": summary,
        "after": {name: digest(value) for name, value in payload.items()},
        "world_inventory_sha256": digest(
            json.dumps(expected_world, sort_keys=True).encode()
        ),
    }
    return payload, expected_world, binding


def _write_record(path, value):
    if len(json.dumps(value).encode()) > 65536:
        raise ValueError("Current policy record exceeds limit")
    _json_write(path, value)
    path.chmod(0o600)
    _sync_directory(path.parent)


def _target_hash(root, name):
    path = root / name
    if not path.exists() and not path.is_symlink():
        return None
    return digest(_read(root, name, limit=ftb.MAX_BYTES))


def stage(request, storage, target, current):
    if any(
        (target / key).exists() or (target / key).is_symlink()
        for key in (PLAN, DONE, STAGING)
    ):
        raise ValueError(
            "Current policy already attempted; never repeat partial changes"
        )
    raw.execute({**request, "action": "verify"}, storage, target)
    payload, world, binding = _expected(request, storage, target, current)
    before = {name: _target_hash(target, name) for name in payload}
    if (
        shutil.disk_usage(target).free
        < sum(map(len, payload.values())) + 65536 + request["policy"]["reserve_bytes"]
    ):
        raise OSError("Current policy free-space reserve would be violated")
    _write_record(target / PLAN, {"binding": binding, "before": before})
    staging = target / STAGING
    staging.mkdir(mode=0o700)
    for name, data in payload.items():
        path = staging / name
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with path.open("xb") as output:
            path.chmod(0o600)
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        if digest(path.read_bytes()) != binding["after"][name]:
            raise ValueError("Current policy staging readback failed")
    for name in payload:
        if _target_hash(target, name) != before[name]:
            raise ValueError("Target changed during current policy staging")
        destination = target / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        os.replace(staging / name, destination)
        _sync_directory(destination.parent)
    _verify_data(request, target, payload, world)
    if _expected(request, storage, target, current)[2] != binding:
        raise ValueError("Current policy source changed during staging")
    receipt = {"plan_sha256": digest((target / PLAN).read_bytes()), "binding": binding}
    _write_record(target / DONE, receipt)
    return {
        "policy_staged": True,
        "files": len(payload),
        "world_inventory_sha256": binding["world_inventory_sha256"],
    }


def _verify_data(request, target, payload, expected_world):
    for name, data in payload.items():
        if _read(target, name, limit=ftb.MAX_BYTES) != data:
            raise ValueError("Current policy file differs from expected source")
    actual = inventory(
        target / request["world"],
        world_name=request["world"],
        max_expanded_bytes=request["world_max_bytes"],
        path_policy="linux-server",
    )
    if actual != expected_world:
        raise ValueError("World differs from historical progress plus current policy")


def verify(request, storage, target, current):
    payload, world, binding = _expected(request, storage, target, current)
    plan, done = raw._read(target / PLAN), raw._read(target / DONE)
    if (
        set(plan) != {"binding", "before"}
        or plan["binding"] != binding
        or set(plan["before"]) != set(payload)
        or done
        != {"plan_sha256": digest((target / PLAN).read_bytes()), "binding": binding}
    ):
        raise ValueError("Current policy has no complete bound receipt")
    _verify_data(request, target, payload, world)
    return {
        "policy_verified": True,
        "files": len(payload),
        "world_inventory_sha256": binding["world_inventory_sha256"],
    }


def execute(
    request,
    storage=Path("/backup/store"),
    target=Path("/restore"),
    current=Path("/current"),
):
    if request["action"] == "stage-policy":
        return stage(request, storage, target, current)
    if request["action"] == "verify-policy":
        return verify(request, storage, target, current)
    raise ValueError("Unknown current policy operation")


if __name__ == "__main__":
    try:
        data = sys.stdin.buffer.read(65537)
        if len(data) > 65536:
            raise ValueError("Current policy request exceeds limit")
        print(json.dumps({"ok": True, **execute(json.loads(data))}))
    except Exception as error:
        print(json.dumps({"ok": False, "error_type": type(error).__name__}))
        raise SystemExit(1) from None
