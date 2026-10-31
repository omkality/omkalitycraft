"""Read the one bounded fixture chunk from a stopped lab ZIP; never edit a world."""

import struct
import zipfile
import zlib

from launcher.nbt import MAX_BYTES, read_nbt


def chunk_level(snapshot, chunk_x, chunk_z):
    """Bounded overworld chunk reader for lab preflight; no archive extraction."""
    with zipfile.ZipFile(snapshot) as archive:
        name = f"lab-world/region/r.{chunk_x // 32}.{chunk_z // 32}.mca"
        if sum(info.filename == name for info in archive.infolist()) != 1:
            raise ValueError("Missing or duplicate fixture region")
        info = archive.getinfo(name)
        if info.file_size > 128 * 1024**2:
            raise ValueError("Fixture region exceeds lab limit")
        with archive.open(info) as region:
            region.seek(4 * (chunk_x % 32 + (chunk_z % 32) * 32))
            location = region.read(4)
            if len(location) != 4:
                raise ValueError("Missing fixture chunk header")
            sector = int.from_bytes(location[:3], "big")
            sectors = location[3]
            if sector < 2 or not sectors or (sector + sectors) * 4096 > info.file_size:
                raise ValueError("Invalid fixture chunk location")
            region.seek(sector * 4096)
            header = region.read(5)
            if len(header) != 5:
                raise ValueError("Truncated fixture chunk header")
            size, compression = struct.unpack(">IB", header)
            if compression != 2 or not 1 < size <= sectors * 4096 - 4:
                raise ValueError("Unsupported fixture chunk encoding")
            compressed = region.read(size - 1)
            if len(compressed) != size - 1:
                raise ValueError("Truncated fixture chunk")
    inflater = zlib.decompressobj()
    raw = inflater.decompress(compressed, MAX_BYTES + 1)
    if len(raw) > MAX_BYTES or not inflater.eof or inflater.unused_data:
        raise ValueError("Invalid or oversized fixture NBT")
    _, root = read_nbt(raw)
    return root["Level"].value


def fixture_tiles(snapshot):
    tiles = chunk_level(snapshot, 8, 8)["TileEntities"].value[1]
    return {
        (
            tile.value["x"].value,
            tile.value["y"].value,
            tile.value["z"].value,
        ): tile.value
        for tile in tiles
    }


def verify_snapshot_tiles(snapshots, expect):
    before = fixture_tiles(snapshots / "before-grief.zip")
    damaged = fixture_tiles(snapshots / "before-restore.zip")
    restored = fixture_tiles(snapshots / "after-restore.zip")
    for name, point in [
        ("vanilla_chest", (130, 241, 130)),
        ("iron_chest", (132, 241, 130)),
        ("thermal_furnace", (134, 241, 130)),
    ]:
        expect(point in before and point in restored, name + "_saved_tile_exists")
        expect(
            before[point] == restored[point],
            name + "_complete_saved_nbt_matches_snapshot",
        )
    neighbor = (136, 241, 130)
    expect(neighbor in damaged and neighbor in restored, "neighbor_saved_tile_exists")
    expect(
        damaged[neighbor] == restored[neighbor], "neighbor_complete_saved_nbt_unchanged"
    )
