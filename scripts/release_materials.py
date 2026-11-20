"""Run the release_materials tool from a checkout or as a module."""

import sys
from pathlib import Path

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.release.release_materials import (
    analysis_entries,
    json_file,
    main,
    prepare_notices,
    verify_materials,
    write_materials,
)

__all__ = [
    "analysis_entries",
    "json_file",
    "main",
    "prepare_notices",
    "verify_materials",
    "write_materials",
]

if __name__ == "__main__":
    main()
