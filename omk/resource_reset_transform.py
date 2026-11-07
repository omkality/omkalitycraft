"""Reviewed data edits for a fresh resource-reset candidate, never a live world.

Unknown mod data is retained. This does not approve portals or a landing site.
The caller must bind the complete inventory and require a current verified backup.
"""

import copy
import gzip
import hashlib
import re

from launcher.nbt import Tag, read_nbt, write_nbt
from omk import resource_reset_inventory as audit
from omk.ftb_dimension_references import ftb_record


def landing(value):
    if (
        not isinstance(value, list)
        or len(value) != 3
        or any(type(v) is not int for v in value)
        or any(abs(value[i]) > 29999000 for i in (0, 2))
        or not 1 <= value[1] <= 253
    ):
        raise ValueError("Invalid candidate overworld landing coordinates")
    return [value[0] + 0.5, float(value[1]), value[2] + 0.5]


def player(root, dimension, position):
    """Return a copy; inventory, XP, capabilities and unknown tags stay intact."""
    result = copy.deepcopy(root)
    if audit._tag(result, "Dimension", 3) == dimension:
        if "RootVehicle" in result or "Riding" in result:
            raise ValueError("Mounted resource player requires a vehicle adapter")
        # Position/motion are deliberately reset together, including old NBT copies.
        result.update(
            Dimension=Tag(3, 0),
            Pos=Tag(9, (6, [Tag(6, v) for v in position])),
            Motion=Tag(9, (6, [Tag(6, 0.0) for _ in range(3)])),
            FallDistance=Tag(5, 0.0),
            OnGround=Tag(1, 1),
            PortalCooldown=Tag(3, 300),
        )
    if "HasSpawnDimensionSet" in result and audit._tag(
        result, "HasSpawnDimensionSet", 1
    ) not in (0, 1):
        raise ValueError("Unreviewed selected respawn dimension flag")
    if (
        "SpawnDimension" in result
        and audit._tag(result, "SpawnDimension", 3) == dimension
    ):
        result.pop("SpawnDimension")
        result["HasSpawnDimensionSet"] = Tag(1, 0)
        # SpawnX/Y/Z/Forced belong to the Overworld bed; Forge keeps other
        # dimensions' bed positions in Spawns, not in these vanilla fields.
    if "Spawns" in result:
        audit._list(result, "Spawns", 10)
        child, rows = result["Spawns"].value
        result["Spawns"] = Tag(
            9, (child, [v for v in rows if audit._tag(v.value, "Dim", 3) != dimension])
        )
    return result


def jed_record(root, dimension):
    result = copy.deepcopy(root)
    if "PlayerData" in result and "PlayerDimensions" in result:
        raise ValueError("Mixed JED tracker generations require review")
    key = "PlayerData" if "PlayerData" in result else "PlayerDimensions"
    seen = set()
    for row in audit._list(result, key, 10):
        identity = (audit._tag(row, "UUIDM", 4), audit._tag(row, "UUIDL", 4))
        if identity in seen:
            raise ValueError("Duplicate JED player identity")
        seen.add(identity)
        if audit._tag(row, "Dimension", 3) == dimension:
            row["Dimension"] = Tag(3, 0)
    return result


def _kind(name, world):
    player_prefix = world + "/playerdata/"
    ftb_prefix = world + "/data/ftb_lib/"
    if name.startswith(player_prefix) and re.fullmatch(
        r"[a-f0-9-]{36}\.(dat|dat_old)", name.removeprefix(player_prefix)
    ):
        return "player"
    if name.startswith(ftb_prefix + "players/"):
        return "ftb"
    if name == ftb_prefix + "universe.dat":
        return "universe"
    if name.startswith(ftb_prefix + "teams/claimedchunks/"):
        return "claims"
    if name == world + "/data/justenoughdimensions/data_tracker.dat":
        return "jed"
    return None


def changes(server, world, dimension, position, files):
    """Sparse bytes only; even unchanged NBT compression is preserved verbatim."""
    position = landing(position)
    payloads = {}
    total = 0
    for name in files:
        kind = _kind(name, world)
        if kind is None:
            continue
        raw = audit._read(server / name, server / world)
        label, root = read_nbt(audit.ftb.unpack(raw))
        if kind == "player":
            result = player(root, dimension, position)
        elif kind == "jed":
            result = jed_record(root, dimension)
        else:
            result = ftb_record(
                root, dimension, universe=kind == "universe", claims=kind == "claims"
            )
        if result != root:
            data = gzip.compress(write_nbt(label, result), compresslevel=1, mtime=0)
            total += len(data)
            if total > audit.ftb.MAX_TOTAL:
                raise ValueError("Resource reset edits exceed reviewed memory budget")
            if read_nbt(audit.ftb.unpack(data)) != (label, result):
                raise ValueError("Resource reset NBT edit failed readback")
            payloads[name] = data
    return payloads


def result_inventory(files, payloads, world, dimension):
    prefix = world + f"/DIM{dimension}/"
    marker = world + "/omk-resource-world.properties"
    result = {
        name: copy.deepcopy(row)
        for name, row in files.items()
        if not name.startswith(prefix) and name != marker
    }
    for name, data in payloads.items():
        if name not in result:
            raise ValueError("Resource reset edit is outside retained source")
        result[name] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    return result
