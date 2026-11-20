"""Test dependencies for api compose status."""

import json
import os
import subprocess
import time
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from urllib.request import urlopen
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[3]

PEER = ROOT / "tests/fixtures/minecraft_status_peer.py"

COMPOSE = ROOT / "deploy/api/compose.yaml"


def docker(*args: str, env=None, timeout: int = 30, check: bool = True) -> str:
    """Run Docker for an owned fixture and report only its synthetic diagnostics."""
    result = subprocess.run(
        ["docker", *args],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        env=env,
        timeout=timeout,
        check=False,
    )
    if check and result.returncode:
        raise RuntimeError(
            f"Docker {args[0]} exited {result.returncode}: {result.stderr}"
        )
    return result.stdout.strip()


@pytest.fixture(scope="module")
def api_image(tmp_path_factory):
    docker("info", "--format", "{{.ServerVersion}}")
    lab = tmp_path_factory.mktemp("omk-compose-integration")
    reference = "omkalitycraft-api-integration:" + uuid4().hex[:12]
    try:
        docker(
            "build",
            "-f",
            str(ROOT / "deploy/api/Dockerfile"),
            "-t",
            reference,
            str(ROOT),
            timeout=300,
        )
        yield lab, reference
    finally:
        docker("image", "rm", reference, check=False)


@contextmanager
def service(
    api_image, *, target: str | None, network: str | None = None
) -> Generator[str]:
    """Start one API using the canonical env boundary and Docker-assigned port."""
    lab, reference = api_image
    project = "omk-status-" + uuid4().hex[:12]
    location = lab / project / "Тестовые данные"
    location.mkdir(parents=True)
    env_file = location.parent / "settings.env"
    lines = [
        f'OMK_API_CONTENT_SOURCE="{location.as_posix()}"',
        "SERVER_STATUS_CACHE_SECONDS=1",
        "SERVER_STATUS_TIMEOUT_SECONDS=0.5",
    ]
    if target is not None:
        lines.append("SERVER_STATUS_TARGETS='" + target + "'")
    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    override = location.parent / "compose.fixture.yaml"
    subnet = os.environ.get("OMK_TEST_DOCKER_SUBNET")
    network_config = ""
    if network is not None:
        network_config = (
            f"networks:\n  default:\n    name: {network}\n    external: true\n"
        )
    elif subnet:
        network_config = f"networks:\n  default:\n    ipam:\n      config:\n        - subnet: {subnet}\n"
    override.write_text(
        "services:\n  api:\n"
        f"    image: {reference}\n"
        "    ports: !override\n      - '127.0.0.1::8000'\n" + network_config,
        encoding="utf-8",
    )
    command = (
        "compose",
        "-p",
        project,
        "--env-file",
        str(env_file),
        "-f",
        str(COMPOSE),
        "-f",
        str(override),
    )
    fixture_env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("SERVER_STATUS_", "OMK_API_", "COMPOSE_"))
        and key
        not in {
            "API_PORT",
            "WORKERS_NUM",
            "API_REQUESTS_PER_SECOND",
            "CLIENT_REPORTS_PRUNE_INTERVAL_SECONDS",
        }
    }
    try:
        docker(*command, "config", "--quiet", env=fixture_env)
        docker(*command, "up", "-d", "--no-build", "--pull", "never", env=fixture_env)
        origin = "http://" + docker(*command, "port", "api", "8000", env=fixture_env)
        wait_for(lambda: request(origin, "/health"))
        yield origin
    finally:
        docker(*command, "down", "--timeout", "5", env=fixture_env)


def request(origin, route):
    with urlopen(origin + route, timeout=2) as response:
        assert response.status == 200
        return json.load(response)


def wait_for(predicate):
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        try:
            value = predicate()
            if value:
                return value
        except OSError:
            pass
        time.sleep(0.1)
    raise AssertionError("Owned API/peer did not reach the expected protocol state")
