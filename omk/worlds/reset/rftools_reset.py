"""Bindings reviewed for a stopped DJ2 copy using RFTools 7.73."""

import copy
from collections import Counter

from omk.shared.nbt import Tag
from omk.worlds.forge112_regions import block_id, compounds, sections, value

ARTIFACT = "rftools-1.12-7.73.jar"
SHA256 = "558c38d0f7852d17a03aef81e4bd6cc2f28e60db8a8749c710c9ee829f2de0a4"
ADAPTER = "rftools-7.73-dimension-transport-v1"
PROPERTIES = "rftools:properties"
PORTER = "rftools:charged_porter"
ADVANCED_PORTER = "rftools:advanced_charged_porter"
RECEIVER = "rftools:matter_receiver"
TRANSMITTER = "rftools:matter_transmitter"
SIMPLE_DIALER = "rftools:simple_dialer"
DIALER_SOURCE = ("transX", "transY", "transZ", "transDim")
TRANSMITTER_PROGRESS = (
    "tpTimer",
    "cooldownTimer",
    "totalTicks",
    "goodTicks",
    "badTicks",
    "status",
    "rfPerTick",
)
FAVORITES = tuple(f"target{i}" for i in range(8))
COORDINATES = ("dim", "x", "y", "z")


def destination_ids(data, dimension):
    """Resolve receiver IDs and reject a registry with ambiguous identities."""
    last_id = value(data, "lastId", 3)
    if last_id < 0:
        raise ValueError("Invalid RFTools destination counter")
    selected, known = set(), set()
    for row in compounds(data, "destinations"):
        target = value(row, "dim", 3)
        if "id" not in row:
            continue
        number = value(row, "id", 3)
        if not 0 <= number <= last_id or number in known:
            raise ValueError("Ambiguous RFTools destination IDs")
        known.add(number)
        if target == dimension:
            selected.add(number)
    return selected, known


def selected_positions(data, dimension, *, registry=False):
    """Return exact row indexes for the selected dimension in a native list."""
    positions, selected = set(), []
    for index, row in enumerate(compounds(data, "destinations")):
        position = tuple(value(row, name, 3) for name in COORDINATES)
        fields = set(COORDINATES)
        if registry:
            fields.add("name")
            value(row, "name", 8)
            if "id" in row:
                fields.add("id")
                value(row, "id", 3)
        if row.keys() != fields or position in positions:
            raise ValueError("Unreviewed or duplicate RFTools destination position")
        positions.add(position)
        if position[0] == dimension:
            selected.append(index)
    return selected


def remove_positions(data, selected):
    """Remove only the previously validated indexes from a destination list."""
    kind, rows = data["destinations"].value
    data["destinations"] = Tag(
        9, (kind, [row for index, row in enumerate(rows) if index not in selected])
    )


def _dialer_fields(data, dimension, receiver_ids):
    source = tuple(field for field in DIALER_SOURCE if field in data)
    if source and (
        source != DIALER_SOURCE or any(data[field].kind != 3 for field in source)
    ):
        return ()  # Leave partial or unreviewed links for the reference audit.
    if "receiver" in data:
        receiver = data["receiver"]
        if receiver.kind != 3:
            return ()
        if receiver.value in receiver_ids:
            # A receiver-less dialer with a source interrupts that transmitter.
            return ("receiver", *source)
    if source and data["transDim"].value == dimension:
        return source
    return ()


def _tile_fields(tile, dimension, receiver_ids):
    if tile.get("id") == Tag(8, SIMPLE_DIALER):
        return _dialer_fields(tile, dimension, receiver_ids)
    if (
        tile.get("id") == Tag(8, TRANSMITTER)
        and receiver_ids
        and "destId" in tile
        and value(tile, "destId", 3) in receiver_ids
        and not {"dim", "dest"} & tile.keys()
    ):
        return ("destId",)
    return ()


def tile_updates(chunk, dimension, receiver_ids, registry):
    """Retire obsolete links only in verified installed RFTools blocks."""
    tiles = compounds(chunk, "TileEntities")
    selected = {
        index: fields
        for index, tile in enumerate(tiles)
        if (fields := _tile_fields(tile, dimension, receiver_ids))
    }
    if not selected:
        return {}
    coordinates = ("x", "y", "z")
    positions = Counter(
        tuple(value(tile, key, 3) for key in coordinates)
        for tile in tiles
        if all(key in tile and tile[key].kind == 3 for key in coordinates)
    )
    section_map = sections(chunk)
    cx, cz = (value(chunk, key, 3) for key in ("xPos", "zPos"))
    edits = {}
    for index, fields in selected.items():
        tile = tiles[index]
        x, y, z = (value(tile, key, 3) for key in coordinates)
        block = value(tile, "id", 8)
        if (
            positions[x, y, z] != 1
            or (x >> 4, z >> 4) != (cx, cz)
            or not 0 <= y <= 255
            or registry.get(block_id(section_map, x, y, z)) != block
        ):
            continue
        updated = {key: tag for key, tag in tile.items() if key not in fields}
        if block == TRANSMITTER:
            if "tpPlayer" in updated:
                value(updated, "tpPlayer", 8)
                del updated["tpPlayer"]
            for field in TRANSMITTER_PROGRESS:
                if field in updated:
                    value(updated, field, 3)
                    updated[field] = Tag(3, 0)
        edits[index] = updated
    return edits


def _item_fields(data, item, dimension, receiver_ids):
    if item == SIMPLE_DIALER:
        return _dialer_fields(data, dimension, receiver_ids)
    if item == RECEIVER:
        keys = ("destinationId",)
    elif item == ADVANCED_PORTER:
        keys = ("target", *FAVORITES)
    else:
        keys = ("target",)
    return tuple(
        key for key in keys if key in data and value(data, key, 3) in receiver_ids
    )


def _inventory(root, inventory, slots, dimension, receiver_ids):
    removed = []
    if inventory not in root:
        return removed
    stacks = compounds(root, inventory)
    occupied = set()
    for index, stack in enumerate(stacks):
        slot = value(stack, "Slot", 1)
        if slot not in slots or slot in occupied:
            raise ValueError("Unreviewed or duplicate RFTools player item slot")
        occupied.add(slot)
        name = stack.get("id")
        if (
            name
            not in (
                Tag(8, PORTER),
                Tag(8, ADVANCED_PORTER),
                Tag(8, RECEIVER),
                Tag(8, SIMPLE_DIALER),
            )
            or "tag" not in stack
        ):
            continue
        data = value(stack, "tag", 10)
        targets = _item_fields(data, name.value, dimension, receiver_ids)
        if not targets:
            continue
        max_count = 64 if name.value in {RECEIVER, SIMPLE_DIALER} else 1
        count = stack.get("Count")
        if (
            not isinstance(count, Tag)
            or count.kind not in {1, 3}
            or not 1 <= count.value <= max_count
            or value(stack, "Damage", 2) != 0
        ):
            raise ValueError("Unreviewed RFTools player item layout")
        if "target" in targets and "tpTimer" in data:
            value(data, "tpTimer", 3)
            del data["tpTimer"]
        for key in targets:
            del data[key]
            removed.append(f"/{inventory}/{index}/tag/{key}")
    return removed


def unbind_player_targets(root, dimension, receiver_ids):
    """Return edited player NBT and the exact findings the edit resolves."""
    result = copy.deepcopy(root)
    removed = _inventory(
        result,
        "Inventory",
        {*range(36), *range(100, 104), -106},
        dimension,
        receiver_ids,
    )
    removed.extend(
        _inventory(result, "EnderItems", set(range(27)), dimension, receiver_ids)
    )
    if "ForgeCaps" in result:
        caps = value(result, "ForgeCaps", 10)
        if PROPERTIES in caps:
            data = value(caps, PROPERTIES, 10)
            if "destinations" in data:
                selected = selected_positions(data, dimension)
                if selected:
                    remove_positions(data, set(selected))
                    removed.extend(
                        f"/ForgeCaps/{PROPERTIES}/destinations/{index}/dim"
                        for index in selected
                    )
    return result, removed
