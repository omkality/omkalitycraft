"""Run the smoke_bundle tool from a checkout or as a module."""

import sys
from pathlib import Path

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.release.smoke_bundle import (
    main,
    prepare,
    smoke,
    smoke_archive,
)

__all__ = ['main', 'prepare', 'smoke', 'smoke_archive']

if __name__ == "__main__":
    main()
