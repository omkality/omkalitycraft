import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from litestar.testing import TestClient

from api.app import create_app
from api.settings.config import ServerStatusTarget, settings
from omk.minecraft_status import ServerStatusCache, _varint, query_players


def reply(value):
    text = json.dumps(value).encode()
    packet = b"\0" + _varint(len(text)) + text
    return _varint(len(packet)) + packet


def exercise_server(data, *, timeout=1, stall=False):
    async def run():
        async def handle(reader, writer):
            try:
                await reader.read(1024)
                if stall:
                    await asyncio.sleep(0.5)
                else:
                    writer.write(data)
                    await writer.drain()
            finally:
                writer.close()
                await writer.wait_closed()

        server = await asyncio.start_server(handle, "127.0.0.1", 0)
        async with server:
            return await query_players(
                "127.0.0.1", server.sockets[0].getsockname()[1], timeout=timeout
            )

    return asyncio.run(run())


def test_real_tcp_status_returns_only_counts_not_sample_names_motd_or_addresses():
    result = exercise_server(
        reply(
            {
                "players": {
                    "online": 3,
                    "max": 20,
                    "sample": [{"name": "private-player", "id": "private-id"}],
                },
                "description": "private MOTD",
            }
        )
    )
    assert result == {"state": "online", "online": 3, "max": 20}


@pytest.mark.parametrize(
    "data",
    [
        b"\x81" * 5,
        _varint(70000),
        reply({"players": {"online": True, "max": 20}}),
        reply({"players": {"online": -1, "max": 20}}),
        reply({"players": {"online": 1, "max": 0}}),
        reply({"players": []}),
    ],
)
def test_bounded_protocol_rejects_bad_packets_or_counts(data):
    with pytest.raises((ValueError, TypeError, asyncio.IncompleteReadError)):
        exercise_server(data)


def test_status_timeout_is_bounded():
    with pytest.raises(TimeoutError):
        exercise_server(b"", timeout=0.03, stall=True)


def test_cache_coalesces_concurrent_requests_and_reuses_counts(monkeypatch):
    async def run():
        release = asyncio.Event()

        async def probe(*_args, **_kwargs):
            await release.wait()
            return {"state": "online", "online": 0, "max": 20}

        mock = AsyncMock(side_effect=probe)
        monkeypatch.setattr("omk.minecraft_status.query_players", mock)
        cache = ServerStatusCache(
            {"dj2": SimpleNamespace(host="127.0.0.1", port=25565)}
        )
        first = asyncio.create_task(cache.snapshot())
        await asyncio.sleep(0)
        assert (await cache.snapshot())["servers"]["dj2"]["state"] == "checking"
        release.set()
        result = await first
        assert result == await cache.snapshot()
        assert mock.await_count == 1 and result["servers"]["dj2"]["max"] == 20

    asyncio.run(run())


def test_failed_probe_is_offline_without_fabricated_zero_players(monkeypatch):
    monkeypatch.setattr(
        "omk.minecraft_status.query_players", AsyncMock(side_effect=TimeoutError)
    )
    result = asyncio.run(
        ServerStatusCache(
            {"dj2": SimpleNamespace(host="127.0.0.1", port=25565)}
        ).snapshot()
    )
    assert result["servers"]["dj2"]["state"] == "offline"
    assert "online" not in result["servers"]["dj2"]


def test_api_has_no_player_supplied_probe_target(monkeypatch):
    monkeypatch.setattr(settings, "server_status_targets", {})
    with TestClient(create_app()) as client:
        response = client.get("/servers/status?host=untrusted.invalid&port=25")
        assert response.status_code == 200 and response.json() == {"servers": {}}
        assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "host",
    ["http://example.invalid", "user:password@example.invalid", "example.invalid/path"],
)
def test_config_rejects_urls_and_credentials_as_server_hosts(host):
    with pytest.raises(ValueError):
        ServerStatusTarget(host=host)
