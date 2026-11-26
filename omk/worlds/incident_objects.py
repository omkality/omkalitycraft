"""Sparse Anvil mutation for a selected DJ2 chest or dropped item."""

import hashlib
import math
import os
import struct
import zlib
from dataclasses import dataclass
from uuid import UUID

from omk.shared.nbt import Tag, read_nbt, write_nbt
from omk.worlds import forge112_regions as anvil
from omk.worlds.incident_players import (
    DATA_VERSION,
    NEID,
    _identity,
    _pin,
    coordinates,
    inventory_slot,
    require_stack,
)
from omk.worlds.reset.resource_reset_landing import SAFE_FLOORS

SECTOR = 4096
AIR = "minecraft:air"
CHESTS = {"minecraft:chest", "minecraft:trapped_chest"}


@dataclass(frozen=True)
class ChunkEdit:
    """Replace only the selected chunk allocation in a verified candidate copy."""

    offset: int
    data: bytes

    def record(self, path, size):
        digest = hashlib.sha256()
        with path.open("rb") as original:
            remaining = self.offset
            while remaining:
                part = original.read(min(remaining, 1024**2))
                if not part:
                    raise ValueError("Region changed before planning")
                digest.update(part)
                remaining -= len(part)
            original.seek(len(self.data), os.SEEK_CUR)
            digest.update(self.data)
            while part := original.read(1024**2):
                digest.update(part)
            if original.tell() != size:
                raise ValueError("Region changed before planning")
        return {"bytes": size, "sha256": digest.hexdigest()}

    def apply(self, path):
        with path.open("r+b") as target:
            target.seek(self.offset)
            target.write(self.data)
            target.flush()
            os.fsync(target.fileno())


def _open_region(world, dimension, cx, cz):
    terrain = world if dimension == 0 else world / f"DIM{dimension}"
    return (
        anvil.Region(terrain / "region" / f"r.{cx // 32}.{cz // 32}.mca", world),
        cx % 32 + cz % 32 * 32,
    )


def _block_lookup(world, dimension, chunk, registry):
    cache = {
        (anvil.value(chunk, "xPos", 3), anvil.value(chunk, "zPos", 3)): anvil.sections(
            chunk
        )
    }

    def lookup(x, y, z):
        key = x >> 4, z >> 4
        if key not in cache:
            region, index = _open_region(world, dimension, *key)
            cache[key] = anvil.sections(region.chunk(index))
        block = anvil.block_id(cache[key], x, y, z)
        return AIR if block is None else registry[block]

    return lookup


def _drop(chunk, selected):
    uid = UUID(selected["entity"])
    rows = anvil.compounds(chunk, "Entities")
    candidates = [i for i, row in enumerate(rows) if _identity(row) == uid]
    if len(candidates) != 1:
        raise ValueError(
            "Dropped entity UUID is missing or ambiguous in its saved chunk"
        )
    index = candidates[0]
    row = rows[index]
    if anvil.value(row, "id", 8) != "minecraft:item" or row.keys() & {
        "Passengers",
        "Riding",
        "RootVehicle",
    }:
        raise ValueError("Selected entity is not an independent dropped stack")
    x, _y, z = coordinates(row)
    if [math.floor(x) >> 4, math.floor(z) >> 4] != selected["chunk"]:
        raise ValueError("Dropped entity coordinates differ from its saved chunk")
    require_stack(anvil.value(row, "Item", 10), selected["id"])
    del chunk["Entities"].value[1][index]
    return row, {"entity_position": coordinates(row)}


def _position(row):
    return [anvil.value(row, axis, 3) for axis in "xyz"]


def _air(section, offset, number):
    for field, index, shift, mask, bits in (
        ("Blocks", offset, 0, 255, number & 255),
        ("Data", offset // 2, 4 * (offset % 2), 15, 0),
        ("Add", offset // 2, 4 * (offset % 2), 15, (number >> 8) & 15),
        ("Add2", offset // 2, 4 * (offset % 2), 15, (number >> 12) & 15),
    ):
        if field not in section:
            if bits:
                section[field] = Tag(7, bytes(2048))
            else:
                continue
        raw = bytearray(section[field].value)
        raw[index] = (raw[index] & ~(mask << shift)) | (bits << shift)
        section[field] = Tag(7, bytes(raw))


def _chest(world, chunk, selected, registry):
    x, y, z = selected["position"]
    dimension = selected["dimension"]
    blocks = _block_lookup(world, dimension, chunk, registry)
    if blocks(x, y, z) != "minecraft:chest":
        raise ValueError("Selected position is not a vanilla chest block")
    neighbors = [
        blocks(x + dx, y, z + dz) for dx, dz in ((-1, 0), (1, 0), (0, -1), (0, 1))
    ]
    if CHESTS.intersection(neighbors):
        raise ValueError("Double or adjacent chests need a separate review")
    tiles = anvil.compounds(chunk, "TileEntities")
    matches = [
        i for i, tile in enumerate(tiles) if _position(tile) == selected["position"]
    ]
    if len(matches) != 1:
        raise ValueError("Chest TileEntity position is missing or ambiguous")
    tile = tiles[matches[0]]
    if anvil.value(tile, "id", 8) != "minecraft:chest" or "LootTable" in tile:
        raise ValueError("Chest has an unreviewed serializer or pending loot")
    if any(
        not 0 <= anvil.value(item, "Slot", 1) < 27
        for item in anvil.compounds(tile, "Items")
    ):
        raise ValueError("Chest has slots outside its reviewed inventory")
    sections = anvil.sections(chunk)
    section = sections[y >> 4]
    index = (y & 15) * 256 + (z & 15) * 16 + (x & 15)
    state = {
        "name": "minecraft:chest",
        "numeric_id": anvil.block_id(sections, x, y, z),
        "metadata": (section["Data"].value[index // 2] >> (4 * (index % 2))) & 15,
    }
    if selected["kind"] == "chest":
        evidence = inventory_slot(tile, "Items", selected)
    else:
        if (
            set(neighbors) != {AIR}
            or y in (0, 255)
            or blocks(x, y + 1, z) != AIR
            or blocks(x, y - 1, z) not in SAFE_FLOORS
            or (
                "TileTicks" in chunk
                and any(
                    _position(tick) == selected["position"]
                    for tick in anvil.compounds(chunk, "TileTicks")
                )
            )
        ):
            raise ValueError(
                "Whole chest removal requires an isolated block without scheduled ticks"
            )
        air = next(number for number, name in registry.items() if name == AIR)
        _air(section, index, air)
        del chunk["TileEntities"].value[1][matches[0]]
        evidence = tile
    return evidence, {"block_state": state}


def edit(server, world, selected, level, runtime):
    _pin(runtime, NEID)
    if selected["kind"] == "dropped":
        cx, cz = selected["chunk"]
    else:
        x, _y, z = selected["position"]
        cx, cz = x >> 4, z >> 4
    region, index = _open_region(world, selected["dimension"], cx, cz)
    label, root, original = region.record(index)
    if (
        anvil.value(root, "DataVersion", 3) != DATA_VERSION
        or write_nbt(label, root) != original
    ):
        raise ValueError("Unreviewed or non-round-trippable Anvil chunk")
    chunk = anvil.value(root, "Level", 10)
    if selected["kind"] == "dropped":
        evidence, context = _drop(chunk, selected)
    else:
        evidence, context = _chest(world, chunk, selected, anvil.block_registry(level))

    raw = write_nbt(label, root)
    if read_nbt(raw) != (label, root):
        raise ValueError("Edited chunk failed typed readback")
    encoded = zlib.compress(raw)
    payload = struct.pack(">IB", len(encoded) + 1, 2) + encoded
    offset, count = region.locations[index]
    if len(payload) > count * SECTOR:
        raise ValueError("Edited chunk exceeds its original Anvil allocation")
    name = region.path.relative_to(server).as_posix()
    patch = ChunkEdit(offset * SECTOR, payload.ljust(count * SECTOR, b"\0"))
    return name, patch, evidence, context
