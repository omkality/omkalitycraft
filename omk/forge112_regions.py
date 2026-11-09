"""Bounded, read-only Anvil/NBT for the pinned Forge 1.12.2 + NEID save format."""

import re
import struct
import zlib
from pathlib import Path

from launcher.nbt import MAX_BYTES, Tag, read_nbt
from omk.ftb_restore_authority import regular


def value(root, key, kind):
    tag = root.get(key)
    if not isinstance(tag, Tag) or tag.kind != kind:
        raise ValueError("Unsupported saved-world field: " + key)
    return tag.value


def compounds(root, key):
    child, rows = value(root, key, 9)
    if child != 10 and not (child == 0 and not rows):
        raise ValueError("Expected compound list: " + key)
    return [r.value for r in rows]


class Region:
    def __init__(self, path: Path, world: Path):
        if not regular(path, world):
            raise ValueError("Linked or missing region")
        match = re.fullmatch(r"r\.(-?\d+)\.(-?\d+)\.mca", path.name)
        if not match:
            raise ValueError("Unsupported region filename")
        self.path = path
        self.x, self.z = map(int, match.groups())
        self.size = path.stat().st_size
        if not 8192 <= self.size <= 1024**3 or self.size % 4096:
            raise ValueError("Unsupported region size")
        with path.open("rb") as source:
            header = source.read(4096)
        self.locations = {}
        occupied = {0, 1}
        for index in range(1024):
            offset = int.from_bytes(header[index * 4 : index * 4 + 3], "big")
            count = header[index * 4 + 3]
            if offset == count == 0:
                continue
            sectors = set(range(offset, offset + count))
            if (
                offset < 2
                or not count
                or (offset + count) * 4096 > self.size
                or occupied & sectors
            ):
                raise ValueError("Invalid or overlapping region allocation")
            occupied.update(sectors)
            self.locations[index] = offset, count

    def chunk(self, index):
        if index not in self.locations:
            raise ValueError("Landing chunk is not saved")
        offset, count = self.locations[index]
        with self.path.open("rb") as source:
            source.seek(offset * 4096)
            header = source.read(5)
            if len(header) != 5:
                raise ValueError("Truncated chunk header")
            length, codec = struct.unpack(">IB", header)
            if codec != 2 or not 1 < length <= count * 4096 - 4:
                raise ValueError("Unsupported chunk compression")
            compressed = source.read(length - 1)
        if len(compressed) != length - 1:
            raise ValueError("Truncated compressed chunk")
        inflater = zlib.decompressobj()
        raw = inflater.decompress(compressed, MAX_BYTES + 1)
        if len(raw) > MAX_BYTES or not inflater.eof or inflater.unused_data:
            raise ValueError("Invalid or oversized chunk NBT")
        level = value(read_nbt(raw)[1], "Level", 10)
        expected = self.x * 32 + index % 32, self.z * 32 + index // 32
        if (value(level, "xPos", 3), value(level, "zPos", 3)) != expected:
            raise ValueError("Chunk coordinates differ from region entry")
        return level


def sections(chunk):
    result = {}
    for section in compounds(chunk, "Sections"):
        y = value(section, "Y", 1)
        if not 0 <= y <= 15 or y in result:
            raise ValueError("Invalid or duplicate chunk section")
        blocks = value(section, "Blocks", 7)
        data = value(section, "Data", 7)
        if len(blocks) != 4096 or len(data) != 2048:
            raise ValueError("Unsupported section block layout")
        for key in ("Add", "Add2"):
            if key in section and len(value(section, key, 7)) != 2048:
                raise ValueError("Invalid extended block IDs")
        result[y] = section
    return result


def block_id(section_map, x, y, z):
    if not 0 <= y <= 255:
        raise ValueError("Block height outside Forge 1.12.2")
    section = section_map.get(y >> 4)
    if section is None:
        return None  # Caller resolves air through the actual FML registry.
    index = (y & 15) * 256 + (z & 15) * 16 + (x & 15)

    def nibble(name):
        data = section.get(name)
        return 0 if data is None else (data.value[index // 2] >> (4 * (index % 2))) & 15

    return section["Blocks"].value[index] | nibble("Add") << 8 | nibble("Add2") << 12
