"""Explicit, journalled authority overlay for a new disposable DJ2 replacement.

Only reviewed permission fields move forward. Player/team identities and all
unreviewed data must be stable; history supplies homes, claims and world progress.
"""

import copy
import gzip
import hashlib
import json
import os

from launcher.nbt import Tag, write_nbt
from omk import ftb_restore_authority as gate
from omk.backup_store import _json_write, _sync_directory
from omk.fs import regular

TEAM_FIELDS = (
    "Owner",
    "Players",
    "FreeToJoin",
    "FakePlayerStatus",
    "RequestingInvite",
    "Invited",
)
RULES = ("Explosions", "EditBlocks", "InteractWithBlocks", "AttackEntities", "UseItems")
PLAN = "ftb-authority-transfer-plan.json"
DONE = "ftb-authority-transferred.json"
STAGING = "ftb-authority-writing"


def sha(path):
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def _tag(root, key, kind):
    value = root.get(key)
    if not isinstance(value, Tag) or value.kind != kind:
        raise ValueError("Unreviewed FTB permission field type")
    return value.value


def _names(values, known):
    if any(not isinstance(v, str) or v.lower() not in known for v in values):
        raise ValueError("FTB permission references an unknown player")
    if len({v.lower() for v in values}) != len(values):
        raise ValueError("Ambiguous FTB permission references")


def _team(current, target, known, *, fake=False):
    owner = _tag(current, "Owner", 8)
    if not (fake and owner == "FakeForgePlayer"):
        _names([owner], known)
    players = _tag(current, "Players", 10)
    _names(players, known)
    if any(
        v.kind != 8 or v.value not in {"none", "enemy", "invited", "ally", "mod"}
        for v in players.values()
    ):
        raise ValueError("Unreviewed FTB team status")
    if _tag(current, "FreeToJoin", 1) not in (0, 1) or _tag(
        current, "FakePlayerStatus", 8
    ) not in {"none", "ally", "member"}:
        raise ValueError("Unreviewed FTB team permission")
    for key in ("RequestingInvite", "Invited"):
        if key in current:
            child, entries = _tag(current, key, 9)
            if child != 8 and (child != 0 or entries):
                raise ValueError("Unreviewed FTB invitation list")
            _names([entry.value for entry in entries], known)
    for key in TEAM_FIELDS:
        if key in current:
            target[key] = copy.deepcopy(current[key])
        else:
            target.pop(key, None)
    source_rules = _tag(_tag(current, "Data", 10), "ftbutilities", 10)
    target_rules = _tag(_tag(target, "Data", 10), "ftbutilities", 10)
    for key in RULES:
        kind = 1 if key == "Explosions" else 8
        value = _tag(source_rules, key, kind)
        if value not in ((0, 1) if kind == 1 else {"none", "ally", "member"}):
            raise ValueError("Unreviewed FTB interaction permission")
        target_rules[key] = copy.deepcopy(source_rules[key])


def merged_records(current, historical):
    # Validate both snapshots before constructing any candidate or writing files.
    gate.projection(current)
    gate.projection(historical)
    if set(current) != set(historical):
        raise ValueError("FTB player/team inventory changed; owner review required")
    result = copy.deepcopy(historical)
    names, uids = set(), set()
    for name, root in current.items():
        if name.startswith("players/"):
            if any(
                root.get(key) != historical[name].get(key) for key in ("Name", "UUID")
            ):
                raise ValueError("FTB player identity changed; owner review required")
            names.add(_tag(root, "Name", 8).lower())
            result[name]["TeamID"] = copy.deepcopy(root["TeamID"])
        elif name.startswith("teams/"):
            if any(
                root.get(key) != historical[name].get(key)
                for key in ("ID", "UID", "Type")
            ):
                raise ValueError("FTB team identity changed; owner review required")
            uid = _tag(root, "UID", 2)
            if uid in uids:
                raise ValueError("Ambiguous FTB team UID")
            uids.add(uid)
    for name, root in current.items():
        if name.startswith("teams/"):
            _team(root, result[name], names)
    _team(
        _tag(current["universe.dat"], "FakeTeam", 10),
        _tag(result["universe.dat"], "FakeTeam", 10),
        names,
        fake=True,
    )
    if not gate.compare(current, result)["compatible"]:
        raise ValueError(
            "Unreviewed FTB authority differences remain; owner review required"
        )
    return result


def _paths(current_zip, destination, lab):
    if (
        not lab.name.startswith("recovery-lab-")
        or lab.resolve() != lab.absolute()
        or destination != lab / "recovery-lab-return/server"
        or destination.resolve() != destination.absolute()
        or current_zip != lab / "backups/before-full-return.zip"
        or not regular(current_zip, lab)
        or not regular(lab / "full-return-staged.json", lab)
        or not regular(lab / "current-ranks-staged.json", lab)
    ):
        raise ValueError(
            "Authority transfer requires an owned staged stopped replacement"
        )
    plan = _json(lab / "full-return-plan.json", lab)
    source = plan.get("source", "")
    if (
        not isinstance(source, str)
        or "/" in source
        or "\\" in source
        or not source.endswith(".zip")
    ):
        raise ValueError("Invalid historical backup identity")
    historical_zip = lab / "backups" / source
    if not regular(historical_zip, lab) or sha(historical_zip) != plan.get(
        "source_sha256"
    ):
        raise ValueError("Historical backup differs from full return plan")
    gate.check_runtime(destination)
    return historical_zip


def _json(path, lab):
    if not regular(path, lab) or path.stat().st_size > 65536:
        raise ValueError("Missing or oversized authority transfer record")
    return json.loads(path.read_bytes())


def _write_json(path, value):
    if len(json.dumps(value).encode()) > 65536:
        raise ValueError("Authority transfer record exceeds limit")
    _json_write(path, value)
    path.chmod(0o600)
    _sync_directory(path.parent)


def _encoded(root):
    return gzip.compress(write_nbt("", root), compresslevel=1, mtime=0)


def transfer(current_zip, destination, *, lab):
    historical_zip = _paths(current_zip, destination, lab)
    if any(
        (lab / name).exists() or (lab / name).is_symlink()
        for name in (PLAN, DONE, STAGING, "ftb-authority-comparison.json")
    ):
        raise ValueError(
            "Authority transfer already attempted; never repeat a partial transfer"
        )
    current = gate.read_zip(current_zip)
    historical = gate.read_zip(historical_zip)
    if gate.read_staged(destination) != historical:
        raise ValueError("Staged FTB data differ from the verified historical backup")
    merged = merged_records(current, historical)
    candidates = {
        name: _encoded(root)
        for name, root in merged.items()
        if root != historical[name]
    }
    files = {
        name: {
            "before": sha(destination / gate.PREFIX / name),
            "after": hashlib.sha256(data).hexdigest(),
        }
        for name, data in candidates.items()
    }
    plan = {
        "schema": 1,
        "current_zip_sha256": sha(current_zip),
        "historical_zip_sha256": sha(historical_zip),
        "files": files,
    }
    _write_json(
        lab / PLAN, plan
    )  # Exclusive creation also serializes competing writers.
    staging = lab / STAGING
    staging.mkdir(mode=0o700)
    for name, data in candidates.items():
        path = staging / name
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with path.open("xb") as out:
            path.chmod(0o600)
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
        if gate.nbt(path.read_bytes()) != merged[name]:
            raise ValueError("Encoded authority transfer failed readback")
    for name in candidates:
        path = destination / gate.PREFIX / name
        if sha(path) != files[name]["before"]:
            raise ValueError("Staged FTB data changed during transfer")
        os.replace(staging / name, path)
        _sync_directory(path.parent)
    if (
        gate.read_staged(destination) != merged
        or sha(current_zip) != plan["current_zip_sha256"]
        or sha(historical_zip) != plan["historical_zip_sha256"]
    ):
        raise ValueError("Authority transfer final verification failed")
    result = {
        "schema": 1,
        "plan_sha256": sha(lab / PLAN),
        "changed_records": sorted(candidates),
        "verified": True,
        "arbitrary_merge": False,
    }
    _write_json(lab / DONE, result)
    verify_transfer(current_zip, destination, lab=lab)
    return result


def verify_transfer(current_zip, destination, *, lab):
    historical_zip = _paths(current_zip, destination, lab)
    plan, done = _json(lab / PLAN, lab), _json(lab / DONE, lab)
    if (
        set(plan) != {"schema", "current_zip_sha256", "historical_zip_sha256", "files"}
        or plan["schema"] != 1
        or done
        != {
            "schema": 1,
            "plan_sha256": sha(lab / PLAN),
            "changed_records": sorted(plan["files"]),
            "verified": True,
            "arbitrary_merge": False,
        }
    ):
        raise ValueError("Authority transfer journal binding mismatch")
    if (
        sha(current_zip) != plan["current_zip_sha256"]
        or sha(historical_zip) != plan["historical_zip_sha256"]
    ):
        raise ValueError("Authority transfer backup changed after planning")
    merged = merged_records(gate.read_zip(current_zip), gate.read_zip(historical_zip))
    if gate.read_staged(destination) != merged:
        raise ValueError("Transferred FTB data changed before replacement start")
    for name, record in plan["files"].items():
        if (
            name not in merged
            or sha(destination / gate.PREFIX / name) != record["after"]
        ):
            raise ValueError("Transferred FTB file failed final readback")
