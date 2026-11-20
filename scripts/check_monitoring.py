"""Run the check_monitoring tool from a checkout or as a module."""

import sys
from pathlib import Path

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.infrastructure.check_monitoring import main

__all__ = ["main"]

if __name__ == "__main__":
    main()
