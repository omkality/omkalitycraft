"""Single-player rescue and exact object selection on saved DJ2 data."""

import gzip
import math
import re
from uuid import UUID

from omk.backups import ftb_restore_authority as ftb
from omk.shared.java_properties import parse_properties
from omk.shared.nbt import Tag, read_nbt, write_nbt
from omk.worlds import forge112_regions as anvil
from omk.worlds.reset.resource_reset_inventory import _read
from omk.worlds.reset.resource_reset_landing import (
    NoReviewedLanding,
    select_landing,
)

DATA_VERSION = anvil.DATA_VERSION
NEID = (
    "NotEnoughIDs-1.5.4.4.jar",
    "f042f90c5623a1f2bbcc1d0bd93cfca40109b9c0659399e1f48aa8ce37b75622",
)
JED = (
    "justenoughdimensions-1.12.2-1.6.0-dev.20211009.214847.jar",
    "6840d8ad69059f90c4288c317bf88284a4ccd716d06cc0aa0d37d20b2693dd8f",
)
KINDS = {
    "inventory": {"player", "slot"},
    "chest": {"dimension", "position", "slot"},
    "dropped": {"dimension", "chunk", "entity"},
    "chest-block": {"dimension", "position"},
}
MASK_64 = (1 << 64) - 1


def _number(value, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError("Incident coordinate, dimension or slot is out of range")
    return value


def _uid(value):
    if not isinstance(value, str) or len(value) != 36 or str(UUID(value)) != value:
        raise ValueError("Use the canonical server UUID")
    return value


def _vector(value, bounds):
    if not isinstance(value, list) or len(value) != len(bounds):
        raise ValueError("Invalid incident position or chunk coordinates")
    for component, (minimum, maximum) in zip(value, bounds, strict=True):
        _number(component, minimum, maximum)


HORIZONTAL = (-29999000, 29999000)
DIMENSION = (-(2**31), 2**31 - 1)
BLOCK = (HORIZONTAL, (0, 255), HORIZONTAL)


def validate(spec):
    if not isinstance(spec, dict) or not spec or spec.keys() - {"rescue", "quarantine"}:
        raise ValueError("Specify a rescue, quarantine or both")
    if "rescue" in spec:
        rescue = spec["rescue"]
        if (
            not isinstance(rescue, dict)
            or not {"player", "danger"} <= rescue.keys()
            or rescue.keys() - {"player", "danger", "landing", "radius_chunks"}
        ):
            raise ValueError("Invalid player rescue selection")
        _uid(rescue["player"])
        _vector(rescue["danger"], (DIMENSION, HORIZONTAL, HORIZONTAL))
        _number(rescue.get("radius_chunks", 0), 0, 32)
        if "landing" in rescue:
            _vector(rescue["landing"], (HORIZONTAL, (2, 251), HORIZONTAL))
    if "quarantine" in spec:
        _quarantine_selection(spec["quarantine"])


def _quarantine_selection(selected):
    kind = selected.get("kind") if isinstance(selected, dict) else None
    if (
        not isinstance(kind, str)
        or kind not in KINDS
        or selected.keys() != KINDS[kind] | {"kind", "id"}
        or not isinstance(selected["id"], str)
        or not re.fullmatch(r"[a-z0-9_.-]{1,64}:[a-z0-9_./-]{1,128}", selected["id"])
    ):
        raise ValueError("Invalid exact quarantine selection")
    if kind == "inventory":
        _uid(selected["player"])
        slot = _number(selected["slot"], 0, 255)
        if slot not in {*range(36), 100, 101, 102, 103, 150}:
            raise ValueError("Use a vanilla inventory, armor or offhand slot")
        return
    _number(selected["dimension"], *DIMENSION)
    if kind == "dropped":
        _uid(selected["entity"])
        _vector(selected["chunk"], ((-1874938, 1874937),) * 2)
    else:
        _vector(selected["position"], BLOCK)
        if kind == "chest":
            _number(selected["slot"], 0, 26)
        elif selected["id"] != "minecraft:chest":
            raise ValueError("Only the vanilla single chest block is reviewed")


def document(path, parent):
    raw = ftb.unpack(_read(path, parent))
    record = read_nbt(raw)
    if write_nbt(*record) != raw:
        raise ValueError("Original NBT cannot be round-tripped losslessly")
    return record


def compressed(name, root):
    raw = write_nbt(name, root)
    if read_nbt(raw) != (name, root):
        raise ValueError("Edited NBT failed typed readback")
    return gzip.compress(raw, compresslevel=1, mtime=0)


def _pin(files, pin):
    name, digest = pin
    if files.get(f"mods/{name}") != digest:
        raise ValueError("Saved data requires a reviewed DJ2 mod runtime")


def _identity(root, most="UUIDMost", least="UUIDLeast"):
    high, low = anvil.value(root, most, 4), anvil.value(root, least, 4)
    return UUID(int=((high & MASK_64) << 64) | (low & MASK_64))


def coordinates(root):
    kind, rows = anvil.value(root, "Pos", 9)
    if kind != 6 or len(rows) != 3 or not all(math.isfinite(t.value) for t in rows):
        raise ValueError("Unreviewed saved position")
    return [t.value for t in rows]


def inventory_slot(actor, field, selected):
    rows = anvil.compounds(actor, field)
    slots = [anvil.value(row, "Slot", 1) & 255 for row in rows]
    if len(set(slots)) != len(slots) or selected["slot"] not in slots:
        raise ValueError("Inventory slot is missing or ambiguous")
    index = slots.index(selected["slot"])
    stack = rows[index]
    require_stack(stack, selected["id"])
    del actor[field].value[1][index]
    return stack


def require_stack(stack, expected):
    # DJ2 also writes Count as TAG_Int. Retain the exact stored type.
    count = stack.get("Count")
    if (
        anvil.value(stack, "id", 8) != expected
        or count is None
        or count.kind not in {1, 3}
        or count.value < 1
    ):
        raise ValueError("Selected stack ID or count does not match")
    anvil.value(stack, "Damage", 2)


def _move(root, landing):
    if (
        {"RootVehicle", "Riding", "Passengers"} & root.keys()
        or not math.isfinite(health := anvil.value(root, "Health", 5))
        or health <= 0
        or ("DeathTime" in root and anvil.value(root, "DeathTime", 2) != 0)
    ):
        raise ValueError("Dead or mounted player needs manual recovery")
    root.update(
        Dimension=Tag(3, 0),
        Pos=Tag(9, (6, [Tag(6, p) for p in landing])),
        Motion=Tag(9, (6, [Tag(6, 0.0) for _ in range(3)])),
        FallDistance=Tag(5, 0.0),
        OnGround=Tag(1, 1),
        PortalCooldown=Tag(3, 300),
    )


def view_distance(server, world):
    _lines, properties = parse_properties(_read(server / "server.properties", server))
    distance = properties.get("view-distance", "10")
    if properties.get("level-name") != world.name or not re.fullmatch(
        r"[0-9]{1,2}", distance
    ):
        raise ValueError("Cannot establish the saved world and view distance")
    return _number(int(distance), 3, 32)


def _landing(server, world, rescue, view):
    hazard, x, z = rescue["danger"]
    distance = view + rescue.get("radius_chunks", 0) + 2

    def excluded(cx, cz):
        return hazard == 0 and max(abs(cx - (x >> 4)), abs(cz - (z >> 4))) <= distance

    point = rescue.get("landing")
    try:
        proof = select_landing(
            server,
            world.name,
            center=point,
            excluded=excluded,
            **({"radius": 0, "vertical": 0} if point is not None else {}),
        )
    except NoReviewedLanding:
        raise ValueError(
            "Select another saved landing outside the danger area"
        ) from None
    x, y, z = proof["position"]
    return [x + 0.5, float(y), z + 0.5]


def _ftb_history(server, world, player):
    ftb.check_runtime(server)
    records = ftb.read_staged(server, world_name=world.name)
    ftb.projection(records)
    for filename, root in records.items():
        if not filename.startswith("players/") or UUID(
            anvil.value(root, "UUID", 8)
        ) != UUID(player):
            continue
        utilities = anvil.value(anvil.value(root, "Data", 10), "ftbutilities", 10)
        if "teleportTracker" in utilities:
            anvil.value(utilities, "teleportTracker", 10)
            path = world / "data/ftb_lib" / filename
            name, original = document(path, world)
            saved = anvil.value(anvil.value(original, "Data", 10), "ftbutilities", 10)
            saved.pop("teleportTracker")
            return {path.relative_to(server).as_posix(): compressed(name, original)}
    return {}


def _jed_dimension(server, world, player, dimension, runtime):
    path = world / "data/justenoughdimensions/data_tracker.dat"
    if dimension == 0 or not (path.exists() or path.is_symlink()):
        return {}
    _pin(runtime, JED)
    name, root = document(path, world)
    keys = root.keys() & {"PlayerData", "PlayerDimensions"}
    if len(keys) != 1:
        raise ValueError("Unreviewed JED tracker format")
    rows = anvil.compounds(root, next(iter(keys)))
    selected = [row for row in rows if _identity(row, "UUIDM", "UUIDL") == UUID(player)]
    if not selected:
        return {}
    if len(selected) != 1 or anvil.value(selected[0], "Dimension", 3) != dimension:
        raise ValueError("The selected player has conflicting saved dimensions")
    selected[0]["Dimension"] = Tag(3, 0)
    return {path.relative_to(server).as_posix(): compressed(name, root)}


def _player_file(path, world, player):
    name, root = document(path, world)
    if (
        _identity(root) != UUID(player)
        or anvil.value(root, "DataVersion", 3) != DATA_VERSION
    ):
        raise ValueError("Player save identity or data version differs")
    return name, root


def player_edits(server, world, spec, runtime, view):
    """Only the chosen UUID, its back history and its JED row can change."""
    rescue = spec.get("rescue")
    quarantine = spec.get("quarantine", {})
    slot = quarantine if quarantine.get("kind") == "inventory" else None
    moves, evidence, edits = None, None, {}
    actors = {request["player"] for request in (rescue, slot) if request is not None}
    for player in sorted(actors):
        path = world / "playerdata" / f"{player}.dat"
        name, root = _player_file(path, world, player)
        if slot is not None and slot["player"] == player:
            evidence = inventory_slot(root, "Inventory", slot)
        if rescue is not None and rescue["player"] == player:
            dimension = anvil.value(root, "Dimension", 3)
            previous = coordinates(root)
            if dimension != rescue["danger"][0]:
                raise ValueError(
                    "Danger dimension differs from the player's saved dimension"
                )
            landing = _landing(server, world, rescue, view)
            _move(root, landing)
            edits.update(_jed_dimension(server, world, player, dimension, runtime))
            edits.update(_ftb_history(server, world, player))
            previous_path = path.with_suffix(".dat_old")
            if previous_path.exists() or previous_path.is_symlink():
                old_name, old = _player_file(previous_path, world, player)
                _move(old, landing)
                edits[previous_path.relative_to(server).as_posix()] = compressed(
                    old_name, old
                )
            moves = {
                "player": player,
                "from_dimension": dimension,
                "from": previous,
                "to_dimension": 0,
                "to": landing,
                "view_distance": view,
            }
        edits[path.relative_to(server).as_posix()] = compressed(name, root)
    return edits, moves, evidence
