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
SHULKERS = {
    f"minecraft:{color}_shulker_box"
    for color in (
        "white",
        "orange",
        "magenta",
        "light_blue",
        "yellow",
        "lime",
        "pink",
        "gray",
        "silver",
        "cyan",
        "purple",
        "blue",
        "brown",
        "green",
        "red",
        "black",
    )
}
CRATES = {
    "actuallyadditions:block_giant_chest": ("actuallyadditions:giantchest", 117),
    "actuallyadditions:block_giant_chest_medium": (
        "actuallyadditions:giantchestmedium",
        234,
    ),
    "actuallyadditions:block_giant_chest_large": (
        "actuallyadditions:giantchestlarge",
        351,
    ),
}
TILE_STORAGE = {
    "minecraft:chest": ({"minecraft:chest", "minecraft:trapped_chest"}, range(27)),
    "minecraft:shulker_box": (SHULKERS, range(27)),
    "minecraft:ironchest.iron": ({"ironchest:iron_chest"}, range(54)),
    **{tile: ({block}, capacity) for block, (tile, capacity) in CRATES.items()},
}
ITEM_LIMITS = {
    PORTER: 1,
    ADVANCED_PORTER: 1,
    RECEIVER: 64,
    TRANSMITTER: 64,
    SIMPLE_DIALER: 64,
}


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


def _transmitter_fields(data, dimension, receiver_ids):
    if {"dim", "dest"} & data.keys():
        position = data.get("dest")
        if (
            "destId" not in data
            and isinstance(position, Tag)
            and position.kind == 11
            and len(position.value) == 3
            and 0 <= position.value[1] < 256
            and data.get("dim") == Tag(3, dimension)
        ):
            return ("dest", "dim")
        return ()
    if receiver_ids and "destId" in data and value(data, "destId", 3) in receiver_ids:
        return ("destId",)
    return ()


def _tile_fields(tile, dimension, receiver_ids):
    if tile.get("id") == Tag(8, SIMPLE_DIALER):
        return _dialer_fields(tile, dimension, receiver_ids)
    if tile.get("id") == Tag(8, TRANSMITTER):
        return _transmitter_fields(tile, dimension, receiver_ids)
    return ()


def _edit_tile(tile, dimension, receiver_ids):
    fields = _tile_fields(tile, dimension, receiver_ids)
    if fields:
        updated = {key: tag for key, tag in tile.items() if key not in fields}
        if tile["id"] == Tag(8, TRANSMITTER):
            if "tpPlayer" in updated:
                value(updated, "tpPlayer", 8)
                del updated["tpPlayer"]
            for field in TRANSMITTER_PROGRESS:
                if field in updated:
                    value(updated, field, 3)
                    updated[field] = Tag(3, 0)
        return updated, [f"/{field}" for field in fields]
    identifier = tile.get("id")
    if (
        identifier is None
        or identifier.kind != 8
        or identifier.value not in TILE_STORAGE
    ):
        return tile, []
    _blocks, slots = TILE_STORAGE[identifier.value]
    if "Items" not in tile or "LootTable" in tile:
        return tile, []
    updated = copy.deepcopy(tile)
    return updated, _inventory(updated, "Items", slots, dimension, receiver_ids)


def tile_updates(chunk, dimension, receiver_ids, registry):
    """Return changed installed blocks and the exact reference paths they resolve."""
    tiles = compounds(chunk, "TileEntities")
    selected = {}
    for index, tile in enumerate(tiles):
        edited, removed = _edit_tile(tile, dimension, receiver_ids)
        if removed:
            selected[index] = (edited, removed)
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
    for index, edit in selected.items():
        tile = tiles[index]
        x, y, z = (value(tile, key, 3) for key in coordinates)
        block = value(tile, "id", 8)
        expected = TILE_STORAGE[block][0] if block in TILE_STORAGE else {block}
        if (
            positions[x, y, z] != 1
            or (x >> 4, z >> 4) != (cx, cz)
            or not 0 <= y <= 255
            or registry.get(block_id(section_map, x, y, z)) not in expected
        ):
            continue
        edits[index] = edit
    return edits


def _item_fields(data, item, dimension, receiver_ids):
    if item == SIMPLE_DIALER:
        return _dialer_fields(data, dimension, receiver_ids)
    if item == TRANSMITTER:
        return _transmitter_fields(data, dimension, receiver_ids)
    if item == RECEIVER:
        keys = ("destinationId",)
    elif item == ADVANCED_PORTER:
        keys = ("target", *FAVORITES)
    else:
        keys = ("target",)
    return tuple(
        key for key in keys if key in data and value(data, key, 3) in receiver_ids
    )


def _check_count(stack, limit):
    count = stack.get("Count")
    if (
        not isinstance(count, Tag)
        or count.kind not in {1, 3}
        or not 1 <= count.value <= limit
        or value(stack, "Damage", 2) != 0
    ):
        raise ValueError("Unreviewed RFTools inventory item layout")


def _stack_links(stack, dimension, receiver_ids):
    identifier = stack.get("id")
    if identifier is None or identifier.kind != 8 or "tag" not in stack:
        return []
    name = identifier.value
    if name in ITEM_LIMITS:
        data = value(stack, "tag", 10)
        targets = _item_fields(data, name, dimension, receiver_ids)
        if targets:
            _check_count(stack, ITEM_LIMITS[name])
            if "target" in targets and "tpTimer" in data:
                value(data, "tpTimer", 3)
                del data["tpTimer"]
            for key in targets:
                del data[key]
        return [f"/tag/{key}" for key in targets]
    if name not in SHULKERS and name not in CRATES:
        return []
    data = value(stack, "tag", 10)
    if name in SHULKERS:
        if "BlockEntityTag" not in data:
            return []
        container = value(data, "BlockEntityTag", 10)
        slots, prefix, limit = range(27), "/tag/BlockEntityTag", 1
    else:
        container = data
        slots, prefix, limit = CRATES[name][1], "/tag", 64
    if "LootTable" in container:
        return []
    removed = _inventory(container, "Items", slots, dimension, receiver_ids)
    if removed:
        _check_count(stack, limit)
    return [prefix + path for path in removed]


def _inventory(root, inventory, slots, dimension, receiver_ids):
    removed = []
    if inventory not in root:
        return removed
    stacks = compounds(root, inventory)
    if isinstance(slots, int):
        # Placed crates include empty slots. Dropped crates omit the consumed keeper.
        if len(stacks) > slots or any("Slot" in stack for stack in stacks):
            return removed
    else:
        occupied = set()
        for stack in stacks:
            slot = value(stack, "Slot", 1)
            if slot not in slots or slot in occupied:
                raise ValueError("Unreviewed or duplicate RFTools inventory slot")
            occupied.add(slot)
    for index, stack in enumerate(stacks):
        removed.extend(
            f"/{inventory}/{index}{path}"
            for path in _stack_links(stack, dimension, receiver_ids)
        )
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
