"""Test dependencies for enderutilities reset preflight."""

import hashlib
import json

import pytest

from omk.worlds import enderutilities_reset as ender
from omk.worlds.reset import resource_reset_preflight as preflight
from tests.fixtures.unit.worlds.enderutilities_reset import crystal, player, porter
from tests.fixtures.unit.worlds.resource_reset_preflight import (
    encoded,
    saved,
)

__all__ = ["saved"]


PLAYER = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa.dat"


@pytest.fixture
def ready(saved, monkeypatch):
    server, world, _, chunk = saved
    data = b"explicit synthetic Ender Utilities artifact"
    digest = hashlib.sha256(data).hexdigest()
    (server / "mods" / ender.ARTIFACT).write_bytes(data)
    profile = json.loads(preflight.PROFILE.read_text())
    profile["artifacts"][ender.ARTIFACT] = digest
    preflight.PROFILE.write_text(json.dumps(profile))
    monkeypatch.setattr(ender, "SHA256", digest)
    root = player(crystal(-18000), porter())
    encoded(world / "playerdata" / PLAYER, root)
    return server, world, root, chunk
