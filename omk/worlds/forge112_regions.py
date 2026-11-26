"""Bounded Anvil reads and isolated candidate edits for Forge 1.12.2."""

import hashlib
import os
import re
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path

from omk.backups.ftb_restore_authority import regular
from omk.shared.nbt import MAX_BYTES, Tag, read_nbt, write_nbt

DATA_VERSION = 1343
SECTOR = 4096


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


def check_editable(name, root, raw):
    """Require a lossless round trip of the original 1.12.2 chunk."""
    if value(root, "DataVersion", 3) != DATA_VERSION or write_nbt(name, root) != raw:
        raise ValueError("Unreviewed or non-round-trippable Anvil chunk")


@dataclass(frozen=True)
class RegionEdit:
    """Sector replacements within a region copied from the verified backup."""

    replacements: tuple[tuple[int, bytes], ...]

    def __post_init__(self):
        end = 2 * SECTOR
        for offset, data in self.replacements:
            if offset < end or offset % SECTOR or not data or len(data) % SECTOR:
                raise ValueError("Invalid or overlapping Anvil replacement")
            end = offset + len(data)

    def record(self, path, size):
        """Hash the complete candidate file without allocating its unchanged bytes."""
        digest = hashlib.sha256()
        with path.open("rb") as original:
            if os.fstat(original.fileno()).st_size != size:
                raise ValueError("Region changed before planning")
            for offset, data in self.replacements:
                while (remaining := offset - original.tell()) > 0:
                    part = original.read(min(remaining, 1024**2))
                    if not part:
                        raise ValueError("Region changed before planning")
                    digest.update(part)
                original.seek(len(data), os.SEEK_CUR)
                digest.update(data)
            while part := original.read(1024**2):
                digest.update(part)
            if original.tell() != size:
                raise ValueError("Region changed before planning")
        return {"bytes": size, "sha256": digest.hexdigest()}

    def apply(self, path):
        """Write the planned sectors into the isolated candidate copy."""
        with path.open("r+b") as target:
            size = target.seek(0, os.SEEK_END)
            if self.replacements:
                offset, data = self.replacements[-1]
                if offset + len(data) > size:
                    raise ValueError("Truncated Anvil candidate")
            for offset, data in self.replacements:
                target.seek(offset)
                target.write(data)
            target.flush()
            os.fsync(target.fileno())


class Region:
    """Read chunks from one Minecraft 1.12 Anvil region file."""

    def __init__(self, path: Path, world: Path):
        if not regular(path, world):
            raise ValueError("Linked or missing region")
        match = re.fullmatch(r"r\.(-?\d+)\.(-?\d+)\.mca", path.name)
        if not match:
            raise ValueError("Unsupported region filename")
        self.path = path
        self.x, self.z = map(int, match.groups())
        self.size = path.stat().st_size
        if not 2 * SECTOR <= self.size <= 1024**3 or self.size % SECTOR:
            raise ValueError("Unsupported region size")
        with path.open("rb") as source:
            header = source.read(SECTOR)
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
                or (offset + count) * SECTOR > self.size
                or occupied & sectors
            ):
                raise ValueError("Invalid or overlapping region allocation")
            occupied.update(sectors)
            self.locations[index] = offset, count

    def chunk(self, index):
        """Decode the stored chunk at the requested region coordinates."""
        return value(self.record(index)[1], "Level", 10)

    def record(self, index):
        """Read the complete chunk record and its original uncompressed bytes."""
        if index not in self.locations:
            raise ValueError("Landing chunk is not saved")
        offset, count = self.locations[index]
        with self.path.open("rb") as source:
            source.seek(offset * SECTOR)
            header = source.read(5)
            if len(header) != 5:
                raise ValueError("Truncated chunk header")
            length, codec = struct.unpack(">IB", header)
            if codec != 2 or not 1 < length <= count * SECTOR - 4:
                raise ValueError("Unsupported chunk compression")
            compressed = source.read(length - 1)
        if len(compressed) != length - 1:
            raise ValueError("Truncated compressed chunk")
        inflater = zlib.decompressobj()
        raw = inflater.decompress(compressed, MAX_BYTES + 1)
        if len(raw) > MAX_BYTES or not inflater.eof or inflater.unused_data:
            raise ValueError("Invalid or oversized chunk NBT")
        name, root = read_nbt(raw)
        level = value(root, "Level", 10)
        expected = self.x * 32 + index % 32, self.z * 32 + index // 32
        if (value(level, "xPos", 3), value(level, "zPos", 3)) != expected:
            raise ValueError("Chunk coordinates differ from region entry")
        return name, root, raw

    def replacement(self, index, name, root):
        """Encode a verified chunk inside its current allocation."""
        raw = write_nbt(name, root)
        if read_nbt(raw) != (name, root):
            raise ValueError("Edited chunk failed typed readback")
        encoded = zlib.compress(raw)
        payload = struct.pack(">IB", len(encoded) + 1, 2) + encoded
        offset, count = self.locations[index]
        if len(payload) > count * SECTOR:
            raise ValueError("Edited chunk exceeds its original Anvil allocation")
        return offset * SECTOR, payload.ljust(count * SECTOR, b"\0")


def block_registry(root):
    registries = value(value(root, "FML", 10), "Registries", 10)
    registry = value(registries, "minecraft:blocks", 10)
    ids, names = {}, set()
    for row in compounds(registry, "ids"):
        number, name = value(row, "V", 3), value(row, "K", 8)
        if not 0 <= number <= 65535 or number in ids or name in names:
            raise ValueError("Ambiguous FML block registry")
        ids[number] = name
        names.add(name)
    if "minecraft:air" not in names:
        raise ValueError("FML registry has no air")
    return ids


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
