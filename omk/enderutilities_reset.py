"""Pinned target unbinding in saved player Inventory/EnderItems, never live data.

Only loose tier-0 crystals and the Items modules of Ender Porters are reviewed.
Other storage/tier/serializer paths remain findings in the general preflight.
"""

import copy
import math

from launcher.nbt import Tag

ARTIFACT = "enderutilities-1.12.2-0.7.15.jar"
SHA256 = "c0a604aac57853f76f16e21958b02f4d6adbc543c20dda67eb1088ca91ba618c"
ADAPTER = "enderutilities-0.7.15-player-location-target-v2"
CRYSTAL = "enderutilities:linkcrystal"
PORTER = "enderutilities:enderporter"
TARGET_FIELDS = {
    "posX": 3,
    "posY": 3,
    "posZ": 3,
    "Dim": 3,
    "BlockFace": 1,
    "dPosX": 6,
    "dPosY": 6,
    "dPosZ": 6,
    "DimName": 8,
    "BlockName": 8,
    "BlockMeta": 1,
    "ItemMeta": 2,
    "Yaw": 5,
    "Pitch": 5,
}
REQUIRED = {"posX", "posY", "posZ", "Dim", "BlockFace"}


def _field(root, key, kinds):
    value = root.get(key)
    if not isinstance(value, Tag) or value.kind not in kinds:
        raise ValueError("Unsupported Ender Utilities saved field: " + key)
    return value.value


def _rows(tag, maximum):
    if not isinstance(tag, Tag) or tag.kind != 9:
        raise ValueError("Unsupported Ender Utilities item list")
    kind, rows = tag.value
    if len(rows) > maximum or kind not in ({10} if rows else {0, 10}):
        raise ValueError("Unsupported Ender Utilities item-list layout")
    if any(not isinstance(row, Tag) or row.kind != 10 for row in rows):
        raise ValueError("Unsupported Ender Utilities item-list element")
    return [row.value for row in rows]


def _target(stack, dimension, path, removed):
    if _field(stack, "id", {8}) != CRYSTAL:
        return
    damage = _field(stack, "Damage", {2})
    if damage != 0:
        return  # Block/portal tiers require separate native acceptance.
    if _field(stack, "Count", {1, 3}) <= 0:
        raise ValueError("Invalid saved location-crystal count")
    if "tag" not in stack:
        return
    data = _field(stack, "tag", {10})
    if "Target" not in data:
        return
    target = _field(data, "Target", {10})
    if _field(target, "Dim", {3}) != dimension:
        return
    if not set(target) >= REQUIRED or set(target) - set(TARGET_FIELDS):
        raise ValueError("Unreviewed location-crystal Target schema")
    for key, tag in target.items():
        value = _field(target, key, {TARGET_FIELDS[key]})
        if tag.kind in {5, 6} and not math.isfinite(value):
            raise ValueError("Nonfinite location-crystal coordinate")
    if not 0 <= target["BlockFace"].value <= 5 or ("Yaw" in target) != (
        "Pitch" in target
    ):
        raise ValueError("Unreviewed location-crystal orientation")
    del data["Target"]  # Native removeTargetTagFromItem keeps all other NBT.
    removed.append(path + "/tag/Target/Dim")


def _inventory(root, key, slots, dimension, removed):
    if key not in root:
        return
    rows = _rows(root[key], len(slots))
    occupied = set()
    for index, stack in enumerate(rows):
        slot = _field(stack, "Slot", {1})
        if slot not in slots or slot in occupied:
            raise ValueError("Unreviewed or duplicate player inventory slot")
        occupied.add(slot)
        name = _field(stack, "id", {8})
        path = f"/{key}/{index}"
        if name == CRYSTAL:
            _target(stack, dimension, path, removed)
        elif name == PORTER and _field(stack, "Damage", {2}) in {0, 1}:
            if _field(stack, "Count", {1, 3}) != 1:
                raise ValueError("Unreviewed Ender Porter stack count")
            if "tag" not in stack:
                continue
            data = _field(stack, "tag", {10})
            if "Items" not in data:
                continue
            modules, used = _rows(data["Items"], 10), set()
            for module_index, module in enumerate(modules):
                number = _field(module, "Slot", {1})
                if not 0 <= number < 10 or number in used:
                    raise ValueError("Unreviewed or duplicate module slot")
                used.add(number)
                _target(module, dimension, f"{path}/tag/Items/{module_index}", removed)


def unbind_player_targets(root, dimension):
    """Return an independent tree and exact removable finding paths; source is intact."""
    if type(dimension) is not int or not -(2**31) <= dimension < 2**31:
        raise ValueError("Invalid target dimension")
    if not isinstance(root, dict):
        raise ValueError("Invalid saved player root")
    result, removed = copy.deepcopy(root), []
    _inventory(
        result, "Inventory", {*range(36), *range(100, 104), -106}, dimension, removed
    )
    _inventory(result, "EnderItems", set(range(27)), dimension, removed)
    return result, removed
