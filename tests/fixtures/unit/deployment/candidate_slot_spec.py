"""Test dependencies for candidate slot spec."""

from types import SimpleNamespace

import pytest


@pytest.fixture
def configured(tmp_path):
    private = tmp_path / ".omk-admin"
    private.mkdir(mode=0o700)
    cfg = SimpleNamespace(
        private=private,
        servers={"dj2": tmp_path / "server"},
        recovery_consoles={"dj2": SimpleNamespace(port=25577)},
    )
    entry = {
        "container": "candidate",
        "network": "owned-net",
        "network_label": "omkality.network.id",
        "network_owner": "owned",
        "game_host_port": 25578,
        "rcon_host_port": 25579,
        "game_container_port": 25576,
        "rcon_container_port": 25575,
        "auth_url": "http://drasl:25585/authlib-injector",
        "metadata_file": "public.json",
    }
    return cfg, entry
