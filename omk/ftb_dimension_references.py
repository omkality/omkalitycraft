"""FTB 5.4 storage adapter: clear one dimension's references in copied records.

Any signed-int dimension is supported, including Overworld and dynamic worlds.
This is not wipe authorization: the caller owns allowlisting, backup and stop.
GTNH/other storage versions require their own verified adapters.
"""

import copy

from launcher.nbt import Tag


def _tag(root, key, kind):
    value = root.get(key)
    if not isinstance(value, Tag) or value.kind != kind:
        raise ValueError("Unreviewed FTB dimension-reference field")
    return value.value


def _dimension(tag):
    if not isinstance(tag, Tag) or tag.kind != 11 or len(tag.value) not in (0, 3, 4):
        raise ValueError("Unreviewed FTB dimension position")
    return None if not tag.value else (tag.value[3] if len(tag.value) == 4 else 0)


def _utilities(data, dimension):
    homes = _tag(data, "Homes", 10)
    for key in list(homes):
        if _dimension(homes[key]) == dimension:
            del homes[key]
    if "LastDeath" in data and _dimension(data["LastDeath"]) == dimension:
        data["LastDeath"] = Tag(11, [])
    if "teleportTracker" in data:
        tracker = _tag(data, "teleportTracker", 10)
        for key, value in list(tracker.items()):
            if value.kind != 10:
                raise ValueError("Unreviewed teleport tracker entry")
            if _tag(value.value, "dimension", 3) == dimension:
                del tracker[key]


def ftb_record(root, dimension, *, universe=False, claims=False):
    if type(dimension) is not int or not -(2**31) <= dimension < 2**31:
        raise ValueError("Invalid FTB dimension ID")
    if universe and claims:
        raise ValueError("Ambiguous FTB reference record kind")
    result = copy.deepcopy(root)
    if claims:
        _tag(result, "ClaimedChunks", 10).pop(str(dimension), None)
        return result
    actor = _tag(result, "FakePlayer", 10) if universe else result
    _utilities(_tag(_tag(actor, "Data", 10), "ftbutilities", 10), dimension)
    if universe:
        data = _tag(_tag(result, "Data", 10), "ftbutilities", 10)
        warps = _tag(data, "Warps", 10)
        for key in list(warps):
            if _dimension(warps[key]) == dimension:
                del warps[key]
    return result
