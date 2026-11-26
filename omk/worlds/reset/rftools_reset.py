"""Bindings reviewed for a stopped DJ2 copy using RFTools 7.73."""

import copy

from omk.shared.nbt import Tag
from omk.worlds.forge112_regions import compounds, value

ARTIFACT = "rftools-1.12-7.73.jar"
SHA256 = "558c38d0f7852d17a03aef81e4bd6cc2f28e60db8a8749c710c9ee829f2de0a4"
ADAPTER = "rftools-7.73-dimension-transport-v1"
PROPERTIES = "rftools:properties"
PORTER = "rftools:charged_porter"
ADVANCED_PORTER = "rftools:advanced_charged_porter"
RECEIVER = "rftools:matter_receiver"
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


def _inventory(root, inventory, slots, receiver_ids, removed):
    if inventory not in root:
        return
    stacks = compounds(root, inventory)
    occupied = set()
    for index, stack in enumerate(stacks):
        slot = value(stack, "Slot", 1)
        if slot not in slots or slot in occupied:
            raise ValueError("Unreviewed or duplicate RFTools player item slot")
        occupied.add(slot)
        name = stack.get("id")
        if name not in (Tag(8, PORTER), Tag(8, ADVANCED_PORTER), Tag(8, RECEIVER)) or (
            "tag" not in stack
        ):
            continue
        data = value(stack, "tag", 10)
        if name.value == RECEIVER:
            keys = ("destinationId",)
        elif name.value == ADVANCED_PORTER:
            keys = ("target", *FAVORITES)
        else:
            keys = ("target",)
        targets = [
            key for key in keys if key in data and value(data, key, 3) in receiver_ids
        ]
        if not targets:
            continue
        count = stack.get("Count")
        if (
            not isinstance(count, Tag)
            or count.kind not in {1, 3}
            or not 1 <= count.value <= (64 if name.value == RECEIVER else 1)
            or value(stack, "Damage", 2) != 0
        ):
            raise ValueError("Unreviewed RFTools player item layout")
        if "target" in targets and "tpTimer" in data:
            value(data, "tpTimer", 3)
            del data["tpTimer"]
        for key in targets:
            del data[key]
            removed.append(f"/{inventory}/{index}/tag/{key}")


def unbind_player_targets(root, dimension, receiver_ids):
    """Return edited player NBT and the exact findings the edit resolves."""
    result, removed = copy.deepcopy(root), []
    _inventory(
        result, "Inventory", {*range(36), *range(100, 104), -106}, receiver_ids, removed
    )
    _inventory(result, "EnderItems", set(range(27)), receiver_ids, removed)
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
