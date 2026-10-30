"""Small atomic writes, with temporary files inside the portable destination."""

import contextlib
import os
import tempfile
from pathlib import Path

from omk.fs import resolved


def local_file(folder: Path, name: str) -> Path:
    path = folder / name
    if not resolved(path).is_relative_to(resolved(folder)):
        raise ValueError("Player settings path escapes the instance")
    return path


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=".omk-write-", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            temporary.unlink()
