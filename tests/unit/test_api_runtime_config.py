import asyncio
import os
import subprocess
import sys
from pathlib import Path

import pytest
from litestar.testing import TestClient
from pydantic import ValidationError

from api import lifecycle
from api.__main__ import server_command
from api.app import create_app
from api.settings.config import Settings, settings


@pytest.fixture
def clean_settings_env(monkeypatch):
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)


def test_native_defaults_and_command_share_settings(clean_settings_env):
    value = Settings(_env_file=None)
    assert (value.api_host, value.api_port, value.workers_num) == ("127.0.0.1", 8000, 1)
    assert server_command(value)[-6:] == [
        "--host",
        "127.0.0.1",
        "--port",
        "8000",
        "--workers",
        "1",
    ]


def test_environment_overrides_dotenv_then_defaults(
    tmp_path, monkeypatch, clean_settings_env
):
    dotenv = tmp_path / "settings.env"
    dotenv.write_text("API_PORT=8123\nWORKERS_NUM=2\nAPI_HOST=::1\n", encoding="utf-8")
    monkeypatch.setenv("API_PORT", "8124")
    value = Settings(_env_file=dotenv)
    assert (value.api_host, value.api_port, value.workers_num) == ("::1", 8124, 2)
    assert server_command(value)[-6:] == [
        "--host",
        "::1",
        "--port",
        "8124",
        "--workers",
        "2",
    ]


@pytest.mark.parametrize(
    "key,value",
    [
        ("api_port", 0),
        ("api_port", 65536),
        ("workers_num", 0),
        ("workers_num", 33),
        ("api_host", "not-an-address"),
        ("api_requests_per_second", 0),
        ("api_requests_per_second", 10001),
        ("client_reports_prune_interval_seconds", 59),
        ("client_reports_prune_interval_seconds", 86401),
        ("omk_api_cpus", 0),
        ("omk_api_cpus", 65),
        ("omk_api_memory_mib", 127),
        ("omk_api_memory_mib", 65537),
        ("omk_api_log_mib", 0),
        ("omk_api_log_files", 0),
        ("omk_api_log_files", 31),
    ],
)
def test_invalid_settings_are_rejected(key, value, clean_settings_env):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{key: value})


@pytest.mark.parametrize(
    "key", ["WORKERS_NUM", "API_HOST", "API_PORT", "SERVER_STATUS_TARGETS"]
)
def test_entrypoint_rejects_bad_environment_without_echoing_it(tmp_path, key):
    project = Path(__file__).resolve().parents[2]
    secret = "fixture-do-not-print-this-value"
    result = subprocess.run(
        [sys.executable, "-m", "api"],
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(project), key: secret},
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 2
    assert secret not in result.stdout + result.stderr
    assert "Traceback" not in result.stderr
    assert "Invalid API configuration" in result.stderr


def test_request_limit_uses_environment_setting_but_keeps_test_override(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(settings, "content_root", str(tmp_path))
    monkeypatch.setattr(settings, "api_requests_per_second", 1)
    with TestClient(create_app()) as client:
        assert 429 in [client.get("/version").status_code for _ in range(10)]
    with TestClient(create_app(requests_per_second=128)) as client:
        assert all(client.get("/version").status_code == 200 for _ in range(10))


def test_report_retention_uses_configured_interval(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "client_reports_root", str(tmp_path / "private"))
    monkeypatch.setattr(settings, "client_reports_auth_url", "http://127.0.0.1:9")
    monkeypatch.setattr(settings, "client_reports_prune_interval_seconds", 90)
    monkeypatch.setattr(lifecycle, "prune_reports", lambda: None)
    delays = []

    async def run():
        observed = asyncio.Event()

        async def sleep(delay):
            delays.append(delay)
            observed.set()
            raise asyncio.CancelledError

        monkeypatch.setattr(lifecycle.asyncio, "sleep", sleep)
        async with lifecycle.report_retention(None):
            await asyncio.wait_for(observed.wait(), 5)

    asyncio.run(run())
    assert delays == [90]
