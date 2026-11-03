"""Read-only Forge saved-registry comparison, never a world converter."""

import gzip
import hashlib
import io
import zlib
from pathlib import Path

from launcher.nbt import MAX_BYTES, read_nbt
from omk.backup_archive import regular_file

CRITICAL = frozenset(
    {"minecraft:blocks", "minecraft:items", "minecraft:entities", "minecraft:biomes"}
)
MAX_DETAILS = 100


def add_upgrade_commands(sub):
    upgrade = sub.add_parser("upgrade", help="Read-only modpack upgrade checks")
    audit = upgrade.add_subparsers(dest="action", required=True).add_parser(
        "registry-audit", help="Compare stopped copies of Forge level.dat"
    )
    for name in ("source", "target"):
        audit.add_argument("--" + name, type=Path, required=True)


def _ordinary_path(path):
    # Checking only the leaf would permit a parent symlink/junction into live data.
    path = path.absolute()
    for entry in (path, *path.parents):
        if entry.is_symlink() or entry.is_junction():
            raise ValueError("Linked registry input")
    return path


def _field(compound, key, kind):
    tag = compound.get(key)
    if tag is None or tag.kind != kind:
        raise ValueError("Invalid Forge registry structure")
    return tag.value


def _name(value):
    # Legacy names include Galacticraft's "outer space" biomes and multi-colon
    # registry groups. Preserve exact names instead of applying modern ID rules.
    if (
        not isinstance(value, str)
        or not 3 <= len(value) <= 256
        or ":" not in value
        or value.startswith(":")
        or value.endswith(":")
        or any(ord(c) < 32 or ord(c) == 127 for c in value)
    ):
        raise ValueError("Invalid saved registry name")
    return value


def read_registries(path):
    """Read bounded gzip NBT from an operator-supplied stopped level.dat copy."""
    path = _ordinary_path(Path(path))
    if not 0 < regular_file(path) <= MAX_BYTES:
        raise ValueError("Oversized registry input")
    with path.open("rb") as file:
        raw = file.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("Oversized registry input")
    with gzip.GzipFile(fileobj=io.BytesIO(raw)) as file:
        nbt = file.read(MAX_BYTES + 1)
    _, root = read_nbt(nbt)
    saved = _field(_field(root, "FML", 10), "Registries", 10)
    if not saved.keys() >= CRITICAL or len(saved) > 128:
        raise ValueError("Incomplete or oversized Forge registry set")
    registries = {}
    for name, registry in saved.items():
        _name(name)
        if registry.kind != 10:
            raise ValueError("Invalid Forge registry")
        child, entries = _field(registry.value, "ids", 9)
        if child not in {0, 10} or (child == 0 and entries) or len(entries) > 32768:
            raise ValueError("Invalid Forge registry entries")
        names, numbers = {}, set()
        for entry in entries:
            key = _name(_field(entry.value, "K", 8))
            number = _field(entry.value, "V", 3)
            if not 0 <= number <= 2147483647 or key in names or number in numbers:
                raise ValueError("Ambiguous saved registry mapping")
            names[key] = number
            numbers.add(number)
        registries[name] = names
    return {"sha256": hashlib.sha256(raw).hexdigest(), "registries": registries}


def _details(names):
    values = sorted(names)
    return {
        "count": len(values),
        "names": values[:MAX_DETAILS],
        "truncated": len(values) > MAX_DETAILS,
    }


def compare_registries(source, target):
    before, after = source["registries"], target["registries"]
    groups = {}
    for name in sorted(before.keys() | after.keys()):
        old, new = before.get(name, {}), after.get(name, {})
        shared = old.keys() & new.keys()
        groups[name] = {
            "source_present": name in before,
            "target_present": name in after,
            "source_count": len(old),
            "target_count": len(new),
            "removed": _details(old.keys() - new.keys()),
            "added": _details(new.keys() - old.keys()),
            "numeric_id_changes": sum(old[key] != new[key] for key in shared),
        }
    review = bool(before.keys() - after.keys()) or any(
        group["removed"]["count"] for group in groups.values()
    )
    return {
        "ok": not review,
        "read_only": True,
        "upgrade_accepted": False,
        "requires_registry_review": review,
        "coverage": "Saved registry names/IDs only; not aliases, datafixers or world contents",
        "sha256": {"source": source["sha256"], "target": target["sha256"]},
        "detail_limit_per_change": MAX_DETAILS,
        "registries": groups,
    }


def audit_registry_files(args):
    try:
        return compare_registries(
            read_registries(args.source), read_registries(args.target)
        )
    except OSError, ValueError, EOFError, UnicodeError, TypeError, zlib.error:
        return {
            "ok": False,
            "read_only": True,
            "upgrade_accepted": False,
            "error": "Unreadable or invalid Forge registry input",
        }
