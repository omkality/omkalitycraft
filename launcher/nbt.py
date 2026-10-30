"""Bounded, uncompressed Java NBT for servers.dat, retaining unknown fields."""

import io
import struct
from dataclasses import dataclass
from typing import Any

MAX_BYTES = 2 * 1024**2
FORMATS = {1: ">b", 2: ">h", 3: ">i", 4: ">q", 5: ">f", 6: ">d"}


@dataclass
class Tag:
    kind: int
    value: Any


def utf_encode(value: str) -> bytes:
    result = bytearray()
    units = value.encode("utf-16-be", errors="surrogatepass")
    for (unit,) in struct.iter_unpack(">H", units):
        if 0 < unit < 128:
            result.append(unit)
        elif unit < 2048:
            result.extend((0xC0 | unit >> 6, 0x80 | unit & 63))
        else:
            result.extend((0xE0 | unit >> 12, 0x80 | unit >> 6 & 63, 0x80 | unit & 63))
    if len(result) > 65535:
        raise ValueError("NBT string too long")
    return struct.pack(">H", len(result)) + result


class Reader:
    def __init__(self, data: bytes):
        if len(data) > MAX_BYTES:
            raise ValueError("NBT file too large")
        self.stream = io.BytesIO(data)

    def read(self, size: int) -> bytes:
        if not 0 <= size <= MAX_BYTES:
            raise ValueError("NBT length out of bounds")
        data = self.stream.read(size)
        if len(data) != size:
            raise ValueError("Truncated NBT")
        return data

    def number(self, fmt: str):
        return struct.unpack(fmt, self.read(struct.calcsize(fmt)))[0]

    def text(self) -> str:
        raw = self.read(self.number(">H"))
        text = raw.replace(b"\xc0\x80", b"\0").decode("utf-8", errors="surrogatepass")
        return text.encode("utf-16-be", errors="surrogatepass").decode(
            "utf-16-be", errors="surrogatepass"
        )

    def count(self) -> int:
        value = self.number(">i")
        if not 0 <= value <= 100000:
            raise ValueError("NBT list too large")
        return value

    def payload(self, kind: int, depth: int = 0):
        if depth > 32:
            raise ValueError("NBT nesting too deep")
        if kind in FORMATS:
            return self.number(FORMATS[kind])
        if kind == 7:
            return self.read(self.count())
        if kind == 8:
            return self.text()
        if kind == 9:
            child, count = self.number(">B"), self.count()
            if child not in range(1, 13) and not (child == 0 and count == 0):
                raise ValueError("Invalid NBT list type")
            return child, [
                Tag(child, self.payload(child, depth + 1)) for _ in range(count)
            ]
        if kind == 10:
            result = {}
            while child := self.number(">B"):
                name = self.text()
                if name in result or len(result) > 4096:
                    raise ValueError("Invalid NBT compound")
                result[name] = Tag(child, self.payload(child, depth + 1))
            return result
        if kind in {11, 12}:
            return [
                self.number(">i" if kind == 11 else ">q") for _ in range(self.count())
            ]
        raise ValueError("Unknown NBT tag")


def read_nbt(data: bytes) -> tuple[str, dict[str, Tag]]:
    reader = Reader(data)
    if reader.number(">B") != 10:
        raise ValueError("Expected compound NBT root")
    name, root = reader.text(), reader.payload(10)
    if reader.stream.read(1):
        raise ValueError("Trailing NBT data")
    return name, root


def _payload(tag: Tag) -> bytes:
    kind, value = tag.kind, tag.value
    if kind in FORMATS:
        return struct.pack(FORMATS[kind], value)
    if kind == 7:
        return struct.pack(">i", len(value)) + value
    if kind == 8:
        return utf_encode(value)
    if kind == 9:
        child, entries = value
        return struct.pack(">Bi", child, len(entries)) + b"".join(
            _payload(entry) for entry in entries
        )
    if kind == 10:
        return (
            b"".join(
                bytes([entry.kind]) + utf_encode(name) + _payload(entry)
                for name, entry in value.items()
            )
            + b"\0"
        )
    if kind in {11, 12}:
        return struct.pack(">i", len(value)) + b"".join(
            struct.pack(">i" if kind == 11 else ">q", item) for item in value
        )
    raise ValueError("Unknown NBT tag")


def write_nbt(name: str, root: dict[str, Tag]) -> bytes:
    data = b"\x0a" + utf_encode(name) + _payload(Tag(10, root))
    if len(data) > MAX_BYTES:
        raise ValueError("NBT file too large")
    return data
