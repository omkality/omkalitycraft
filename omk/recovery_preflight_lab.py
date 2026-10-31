"""Read-only coverage check for small overworld lab selections, not production apply."""

import zipfile
import zlib

from omk.recovery_nbt_lab import chunk_level


def preflight(snapshot, minimum, maximum, *, dimension=0):
    if type(dimension) is not int or dimension != 0:
        raise ValueError("Only allowlisted lab dimension 0 is supported")
    if any(
        not isinstance(point, (tuple, list))
        or len(point) != 3
        or any(type(value) is not int for value in point)
        for point in (minimum, maximum)
    ):
        raise ValueError("Expected integer selection coordinates")
    if any(minimum[i] > maximum[i] for i in range(3)):
        raise ValueError("Selection bounds are reversed")
    if not 0 <= minimum[1] <= maximum[1] <= 255 or any(
        abs(point[i]) > 29999983 for point in (minimum, maximum) for i in (0, 2)
    ):
        raise ValueError("Selection exceeds lab world bounds")
    blocks = 1
    for i in range(3):
        blocks *= maximum[i] - minimum[i] + 1
    if blocks > 4096:
        raise ValueError("Selection exceeds lab block limit")
    chunks = [
        (x, z)
        for x in range(minimum[0] // 16, maximum[0] // 16 + 1)
        for z in range(minimum[2] // 16, maximum[2] // 16 + 1)
    ]
    if len(chunks) > 16:
        raise ValueError("Selection exceeds lab chunk limit")
    for x, z in chunks:
        _check_chunk(snapshot, x, z)
    return {"dimension": dimension, "blocks": blocks, "chunks": len(chunks)}


def _check_chunk(snapshot, x, z):
    try:
        level = chunk_level(snapshot, x, z)
        if any(
            level[key].kind != 3 or level[key].value != value
            for key, value in (("xPos", x), ("zPos", z))
        ):
            raise ValueError("Snapshot chunk coordinates do not match selection")
        if any(level[key].kind != 9 for key in ("Sections", "TileEntities")):
            raise ValueError("Invalid snapshot chunk structure")
    except (
        KeyError,
        AttributeError,
        TypeError,
        zlib.error,
        zipfile.BadZipFile,
    ) as error:
        raise ValueError("Unreadable selected lab chunk") from error
