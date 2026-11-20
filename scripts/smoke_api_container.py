"""Run the smoke_api_container tool from a checkout or as a module."""

import sys
from pathlib import Path

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.infrastructure.smoke_api_container import (
    DockerFailure,
    docker_failure_category,
    main,
)

__all__ = ["DockerFailure", "docker_failure_category", "main"]

if __name__ == "__main__":
    main()
