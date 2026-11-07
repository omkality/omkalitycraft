"""Read-only DJ2 authority comparison before a disposable full-world return.

This adapter refuses differences; it never invents a merge of team ownership.
Claims and homes may return to history, authority must match the current source.
"""

import copy
import hashlib
import json
import re
import zipfile
import zlib
from pathlib import Path
from uuid import UUID

from launcher.nbt import MAX_BYTES, Tag, read_nbt
from omk.fs import regular
from omk.recovery_full_lab import _entries

PREFIX = "lab-world/data/ftb_lib/"
MAX_TOTAL = 32 * 1024**2
MAX_RECORDS = 1000
PINS = {
    "FTBLib-5.4.7.2.jar": "623fc574f0227fec6cc9e26c3879a605f9b4499c0078ff085291901a5495a6ac",
    "FTBUtilities-5.4.1.131.jar": "e458fe39aba9ba28122496e54f826e4f61df515ed1f8d0c70cc9e56f67a5404a",
}


def unpack(raw):
    if len(raw) > MAX_BYTES:
        raise ValueError("FTB record exceeds compressed limit")
    if raw.startswith(b"\x1f\x8b"):
        inflater = zlib.decompressobj(31)
        raw = inflater.decompress(raw, MAX_BYTES + 1)
        if len(raw) > MAX_BYTES or not inflater.eof or inflater.unused_data:
            raise ValueError("Invalid or oversized compressed FTB record")
    return raw


def nbt(raw):
    return read_nbt(unpack(raw))[1]


def authority_file(name):
    if name == "universe.dat":
        return True
    if re.fullmatch(r"(?:players|teams)/[A-Za-z0-9_-]{1,64}\.dat", name):
        return True
    if re.fullmatch(r"teams/claimedchunks/[A-Za-z0-9_-]{1,64}\.dat", name):
        return False
    raise ValueError("Unreviewed FTB storage entry")


def read_zip(
    path, *, world_name="lab-world", path_policy="portable", max_expanded_bytes=None
):
    result, total = {}, 0
    with zipfile.ZipFile(path) as archive:
        entries, _ = _entries(
            archive,
            world_name=world_name,
            path_policy=path_policy,
            max_expanded_bytes=max_expanded_bytes,
        )
        prefix = world_name + "/data/ftb_lib/"
        for info in entries:
            if not info.filename.startswith(prefix):
                continue
            name = info.filename.removeprefix(prefix)
            if not authority_file(name):
                continue
            if info.file_size > MAX_BYTES or len(result) >= MAX_RECORDS:
                raise ValueError("FTB authority snapshot exceeds limit")
            raw = unpack(archive.read(info))
            total += len(raw)
            if total > MAX_TOTAL:
                raise ValueError("FTB authority snapshot exceeds limit")
            result[name] = read_nbt(raw)[1]
    return result


def read_staged(server, *, world_name="lab-world"):
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", world_name):
        raise ValueError("Invalid FTB world root")
    base = server / world_name / "data/ftb_lib"
    result, total = {}, 0
    if base.resolve() != base.absolute() or not base.is_dir():
        raise ValueError("Missing or linked staged FTB directory")
    for path in base.rglob("*"):
        if path.is_symlink() or path.resolve() != path.absolute():
            raise ValueError("Linked staged FTB entry")
        if path.is_dir():
            if path.relative_to(base).as_posix() not in {
                "players",
                "teams",
                "teams/claimedchunks",
            }:
                raise ValueError("Unreviewed FTB storage directory")
            continue
        if not regular(path, base):
            raise ValueError("Nonregular staged FTB entry")
        if not authority_file(path.relative_to(base).as_posix()):
            continue
        if path.stat().st_size > MAX_BYTES or len(result) >= MAX_RECORDS:
            raise ValueError("FTB authority snapshot exceeds limit")
        raw = unpack(path.read_bytes())
        total += len(raw)
        if total > MAX_TOTAL:
            raise ValueError("FTB authority snapshot exceeds limit")
        result[path.relative_to(base).as_posix()] = read_nbt(raw)[1]
    return result


def _text(root, key):
    tag = root.get(key)
    if not isinstance(tag, Tag) or tag.kind != 8:
        raise ValueError("Invalid FTB identity field")
    return tag.value


def _player(root):
    # Only these reviewed progress/display fields may change during a rollback.
    root.pop("LastTimeSeen", None)
    root.pop("HideTeamNotification", None)
    data = root.get("Data")
    if not isinstance(data, Tag) or data.kind != 10:
        raise ValueError("Invalid FTB player data")
    utilities = data.value.get("ftbutilities")
    if not isinstance(utilities, Tag) or utilities.kind != 10:
        raise ValueError("Invalid FTBUtilities player data")
    for key in ("Homes", "teleportTracker", "LastDeath"):
        utilities.value.pop(key, None)


def _canonical(value):
    if isinstance(value, Tag):
        return [value.kind, _canonical(value.value)]
    if isinstance(value, dict):
        return {k: _canonical(v) for k, v in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_canonical(v) for v in value]
    if isinstance(value, bytes):
        return value.hex()
    return value


def projection(records):
    records = copy.deepcopy(records)
    if "universe.dat" not in records:
        raise ValueError("Missing FTB universe")
    universe = records["universe.dat"]
    UUID(_text(universe, "UUID"))
    fake = universe.get("FakePlayer")
    if not isinstance(fake, Tag) or fake.kind != 10:
        raise ValueError("Missing FTB fake player")
    _player(fake.value)
    if universe.get("FakeTeam", Tag(0, None)).kind != 10:
        raise ValueError("Missing FTB fake team")
    identities = set()
    teams = {Path(n).stem for n in records if n.startswith("teams/")}
    for name, root in records.items():
        if name.startswith("players/"):
            uid = UUID(_text(root, "UUID")).hex
            if (
                uid in identities
                or _text(root, "Name").lower() != Path(name).stem.lower()
            ):
                raise ValueError("Ambiguous FTB player identity")
            identities.add(uid)
            if _text(root, "TeamID") not in teams | {""}:
                raise ValueError("FTB player references a missing team")
            _player(root)
        elif name.startswith("teams/"):
            if _text(root, "ID") != Path(name).stem:
                raise ValueError("Ambiguous FTB team identity")
            team_type = _text(root, "Type")
            # FTBLib omits Owner when its server team has no player owner.
            # Preserve that absence in the canonical snapshot; never invent one.
            if "Owner" in root or team_type != "server":
                _text(root, "Owner")
            _text(root, "FakePlayerStatus")
            if root.get("Players", Tag(0, None)).kind != 10:
                raise ValueError("Invalid FTB team status map")
    return _canonical(records)


def compare(current, historical):
    a, b = projection(current), projection(historical)

    def digest(value):
        return hashlib.sha256(
            json.dumps(value, sort_keys=True, allow_nan=False).encode()
        ).hexdigest()

    changes = sorted(name for name in a.keys() | b.keys() if a.get(name) != b.get(name))
    return {
        "schema": 1,
        "adapter": "dj2-ftb-5.4",
        "compatible": not changes,
        "current_sha256": digest(a),
        "historical_sha256": digest(b),
        "changed_records": changes,
        "current_records": len(a),
        "historical_records": len(b),
        "automatic_merge": False,
    }


def check_runtime(server):
    for name, expected in PINS.items():
        path = server / "mods" / name
        if not regular(path, server) or path.stat().st_size > 16 * 1024**2:
            raise ValueError("Unreviewed FTB runtime")
        with path.open("rb") as file:
            if hashlib.file_digest(file, "sha256").hexdigest() != expected:
                raise ValueError("Unreviewed FTB runtime")


def stage_gate(current_zip, destination, *, lab):
    if (
        lab.is_symlink()
        or not lab.name.startswith("recovery-lab-")
        or destination != lab / "recovery-lab-return/server"
        or current_zip != lab / "backups/before-full-return.zip"
        or not (lab / "full-return-staged.json").is_file()
    ):
        raise ValueError("Expected stopped disposable full return")
    check_runtime(destination)
    result = compare(read_zip(current_zip), read_staged(destination))
    with (lab / "ftb-authority-comparison.json").open("x", encoding="utf-8") as file:
        json.dump(result, file, indent=2)
    if not result["compatible"]:
        raise ValueError(
            "Current FTB authority differs from historical world; replacement start blocked"
        )
    return result


def verify_gate(current_zip, destination, *, lab):
    """Re-read actual staged data; a marker alone must never authorize start."""
    path = lab / "ftb-authority-comparison.json"
    if not regular(path, lab) or path.stat().st_size > 65536:
        raise ValueError("Missing FTB authority comparison")
    expected = json.loads(path.read_text(encoding="utf-8"))
    check_runtime(destination)
    actual = compare(read_zip(current_zip), read_staged(destination))
    if not actual["compatible"] or actual != expected:
        raise ValueError(
            "FTB authority changed after comparison; replacement start blocked"
        )
