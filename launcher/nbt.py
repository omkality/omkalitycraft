"""Compatibility imports for the shared Java NBT implementation."""

from omk.shared.nbt import (
    FORMATS,
    MAX_BYTES,
    Reader,
    Tag,
    read_nbt,
    utf_encode,
    write_nbt,
)

__all__ = [
    "FORMATS",
    "MAX_BYTES",
    "Reader",
    "Tag",
    "read_nbt",
    "utf_encode",
    "write_nbt",
]
