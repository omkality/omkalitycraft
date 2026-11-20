"""Test dependencies for stopped world backup."""

from dataclasses import replace

import pytest

from omk.backups import stopped_world_backup as backup


@pytest.fixture
def fixture(tmp_path):
    world = tmp_path / "lab-world"
    world.mkdir()
    for name, data in {
        "level.dat": b"level fixture",
        "playerdata/player.dat": b"inventory",
        "DIM-1/region/r.0.0.mca": b"nether",
        "data/ftb_lib/teams/team.dat": b"claims",
    }.items():
        path = world / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    storage = tmp_path / "backups"
    storage.mkdir()
    return world, storage, replace(backup.LAB_POLICY, max_count=2)
