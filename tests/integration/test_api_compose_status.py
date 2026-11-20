"""Use the canonical Compose configuration over an isolated Docker network."""

import json
import os
import time
from uuid import uuid4

import pytest
from testcontainers.core.config import testcontainers_config
from testcontainers.core.container import DockerContainer

from tests.fixtures.integration.api_compose_status import (
    COMPOSE,
    PEER,
    ROOT,
    api_image,
    docker,
    request,
    service,
    wait_for,
)

__all__ = [
    "COMPOSE",
    "PEER",
    "ROOT",
    "api_image",
    "docker",
    "request",
    "service",
    "wait_for",
]


def test_configured_minecraft_status_and_expiry(api_image, monkeypatch):
    # The context managers already own both the peer and its network.
    monkeypatch.setattr(testcontainers_config, "ryuk_disabled", True)
    network = "omk-status-peer-" + uuid4().hex[:12]
    subnet = os.environ.get("OMK_TEST_DOCKER_SUBNET")
    docker("network", "create", *(["--subnet", subnet] if subnet else []), network)
    image = next(
        line.split()[1]
        for line in (ROOT / "deploy/api/Dockerfile")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.startswith("FROM python:")
    )
    peer_name = network + "-peer"
    targets = json.dumps({"dj2": {"host": peer_name, "port": 25565}})
    try:
        with service(api_image, target=targets, network=network) as origin:
            container = (
                DockerContainer(image, name=peer_name)
                .with_kwargs(network=network)
                .with_volume_mapping(str(PEER), "/fixture.py", mode="ro")
                .with_command(["python", "/fixture.py"])
            )
            with container:

                def online():
                    snapshot = request(origin, "/servers/status")
                    value = snapshot["servers"].get("dj2", {})
                    return value if value.get("state") == "online" else None

                value = wait_for(online)
                assert set(value) == {"state", "online", "max", "checked_at"}
                assert (value["online"], value["max"]) == (3, 15)
            started = time.monotonic()

            def offline():
                value = request(origin, "/servers/status")["servers"]["dj2"]
                return value if value["state"] == "offline" else None

            value = wait_for(offline)
            assert time.monotonic() - started < 6
            assert set(value) == {"state", "checked_at"}
    finally:
        docker("network", "rm", network)


@pytest.mark.parametrize("target", [None, "", "{}"])
def test_optional_targets_return_empty_object(api_image, target):
    with service(api_image, target=target) as origin:
        assert request(origin, "/servers/status") == {"servers": {}}
