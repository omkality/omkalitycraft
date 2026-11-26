"""Conservative saved-world landing geometry; no generation, edits or start approval."""

import math
import re
from pathlib import Path

from omk.backups.ftb_restore_authority import nbt
from omk.worlds import forge112_regions as anvil
from omk.worlds.reset.resource_reset_inventory import _read

SAFE_FLOORS = frozenset(
    {
        "minecraft:stone",
        "minecraft:grass",
        "minecraft:dirt",
        "minecraft:cobblestone",
        "minecraft:bedrock",
        "minecraft:planks",
        "minecraft:sandstone",
        "minecraft:brick_block",
        "minecraft:stonebrick",
        "minecraft:iron_block",
        "minecraft:gold_block",
        "minecraft:diamond_block",
        "minecraft:emerald_block",
        "minecraft:quartz_block",
        "minecraft:obsidian",
        "minecraft:end_stone",
    }
)


class NoReviewedLanding(ValueError):
    """Valid save, but no conservative candidate inside the bounded search."""


def _protected_spawn_chunks(world):
    team = nbt(_read(world / "data/ftb_lib/teams/omk_spawn.dat", world))
    if anvil.value(team, "Type", 8) != "server":
        raise ValueError("Landing protection is not a server team")
    claims = anvil.value(
        nbt(_read(world / "data/ftb_lib/teams/claimedchunks/omk_spawn.dat", world)),
        "ClaimedChunks",
        10,
    )
    return {
        (anvil.value(row, "x", 3), anvil.value(row, "z", 3))
        for row in anvil.compounds(claims, "0")
    }


def world_path(server, world_name):
    if not isinstance(world_name, str) or not re.fullmatch(
        r"[A-Za-z0-9_-]{1,64}", world_name
    ):
        raise ValueError("Invalid preflight world name")
    world = server / world_name
    if not world.is_dir() or world.is_symlink() or world.is_junction():
        raise ValueError("Missing or linked preflight world")
    if world.resolve() != server.resolve() / world_name:
        raise ValueError("Aliased preflight world")
    return world


def select_landing(  # noqa: PLR0915 - one bounded saved-world geometry audit
    server: Path,
    world_name: str,
    *,
    radius=16,
    vertical=8,
    max_chunks=32,
    resource_landing=False,
    center=None,
    excluded=None,
):
    if any(type(v) is not int for v in (radius, vertical, max_chunks)) or not (
        0 <= radius <= 32 and 0 <= vertical <= 32 and 1 <= max_chunks <= 256
    ):
        raise ValueError("Invalid landing search budget")
    world = world_path(server, world_name)
    root = nbt(_read(world / "level.dat", world))
    data = anvil.value(root, "Data", 10)
    terrain = world
    if resource_landing:
        terrain = world / "DIM-18000"
        saved_resource = nbt(_read(terrain / "jed_level.dat", world))
        data = anvil.value(saved_resource, "Data", 10)
    spawn = [anvil.value(data, "Spawn" + axis, 3) for axis in "XYZ"]
    origin = spawn if center is None else center
    if not all(abs(origin[i]) <= 29999000 for i in (0, 2)) or not 1 <= origin[1] <= 253:
        raise ValueError("Invalid saved spawn")
    border = [
        anvil.value(data, key, 6)
        for key in ("BorderCenterX", "BorderCenterZ", "BorderSize")
    ]
    if not all(math.isfinite(v) for v in border) or not 1 <= border[2] <= 60000000:
        raise ValueError("Unsupported saved world border")
    if "BorderSizeLerpTime" in data and anvil.value(data, "BorderSizeLerpTime", 4) != 0:
        raise ValueError("Moving border requires native review")
    ids = anvil.block_registry(root)
    claimed = not resource_landing and center is None
    points = _protected_spawn_chunks(world) if claimed else None
    kind = "forge112-saved-vanilla-floor-air"
    if resource_landing:
        kind = "forge112-resource-floor-air"
    elif claimed:
        kind += "-server-claim"
    cache, missing = {}, set()

    def saved(cx, cz):
        key = cx, cz
        if key not in cache and key not in missing:
            if len(cache) + len(missing) >= max_chunks:
                raise ValueError("Landing chunk budget exceeded")
            path = terrain / "region" / f"r.{cx // 32}.{cz // 32}.mca"
            if not path.exists():
                missing.add(key)
                return None
            region = anvil.Region(path, world)
            index = cx % 32 + 32 * (cz % 32)
            if index not in region.locations:
                missing.add(key)
                return None
            chunk = region.chunk(index)
            if any(
                anvil.value(chunk, flag, 1) != 1
                for flag in ("TerrainPopulated", "LightPopulated")
            ):
                missing.add(key)
                return None
            cache[key] = chunk, anvil.sections(chunk)
        return cache.get(key)

    def block(x, y, z):
        result = saved(x >> 4, z >> 4)
        if result is None:
            return None
        number = anvil.block_id(result[1], x, y, z)
        if number is None:
            return "minecraft:air"
        if number not in ids:
            raise ValueError("Block ID missing from FML registry")
        return ids[number]

    def safe(x, y, z):  # noqa: PLR0912 - reject each independent safety condition
        if not 2 <= y <= 251 or (excluded is not None and excluded(x >> 4, z >> 4)):
            return False
        for cx in range((x - 3) >> 4, ((x + 3) >> 4) + 1):
            for cz in range((z - 3) >> 4, ((z + 3) >> 4) + 1):
                nearby = saved(cx, cz)
                if nearby is None:
                    return False
                chunk = nearby[0]
                for tile in anvil.compounds(chunk, "TileEntities"):
                    if (
                        abs(anvil.value(tile, "x", 3) - x) <= 2
                        and abs(anvil.value(tile, "z", 3) - z) <= 2
                        and abs(anvil.value(tile, "y", 3) - y) <= 3
                    ):
                        return False
                for entity in anvil.compounds(chunk, "Entities"):
                    child, pos = anvil.value(entity, "Pos", 9)
                    if (
                        child != 6
                        or len(pos) != 3
                        or not all(math.isfinite(v.value) for v in pos)
                    ):
                        raise ValueError("Unsupported nearby entity position")
                    if (
                        abs(pos[0].value - x - 0.5) <= 3
                        and abs(pos[2].value - z - 0.5) <= 3
                        and abs(pos[1].value - y) <= 3
                    ):
                        return False
        for dx in range(-1, 2):
            for dz in range(-1, 2):
                xx, zz = x + dx, z + dz
                if (points is not None and (xx >> 4, zz >> 4) not in points) or not (
                    abs(xx + 0.5 - border[0]) < border[2] / 2 - 1
                    and abs(zz + 0.5 - border[1]) < border[2] / 2 - 1
                ):
                    return False
                if block(xx, y - 1, zz) not in SAFE_FLOORS:
                    return False
                if any(
                    block(xx, yy, zz) != "minecraft:air" for yy in (y, y + 1, y + 2)
                ):
                    return False
        return True

    candidates = [(origin[0], origin[2])]
    for distance in range(1, radius + 1):
        candidates.extend(
            (origin[0] + dx, origin[2] + dz)
            for dz in range(-distance, distance + 1)
            for dx in range(-distance, distance + 1)
            if max(abs(dx), abs(dz)) == distance
        )
    heights = [origin[1]] + [
        origin[1] + delta * sign for delta in range(1, vertical + 1) for sign in (1, -1)
    ]
    for x, z in candidates:
        for y in heights:
            if safe(x, y, z):
                return {
                    "schema": 1,
                    "kind": kind,
                    "position": [x, y, z],
                    "saved_spawn": spawn,
                    "chunks_read": len(cache),
                    "radius": radius,
                    "vertical": vertical,
                    "max_chunks": max_chunks,
                    "world_changes": False,
                    "generation": False,
                    "native_revalidation_required": True,
                }
    if center is None:
        raise NoReviewedLanding("No reviewed landing near protected saved spawn")
    raise NoReviewedLanding("No reviewed saved landing in the requested area")
