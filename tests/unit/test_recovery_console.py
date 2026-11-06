import socket
import struct
import threading
import time
from uuid import uuid4

import pytest

from omk import recovery_console as module


@pytest.mark.parametrize(
    "text",
    [
        "",
        "Unknown command",
        "There are 1/20 players online:",
        "There are 0/20 players online:unparsed",
        "There are 2/1 players online:",
    ],
)
def test_inventory_never_treats_unrecognized_or_truncated_output_as_empty(text):
    with pytest.raises(module.ConsoleError):
        module.online_players(text)


def test_inventory_contains_uuid_and_name_and_rejects_duplicates():
    identity = str(uuid4())
    assert module.online_players(
        f"There are 1/20 players online:player ({identity})"
    ) == {identity: "player"}
    assert module.online_players("There are 0/20 players online:") == {}
    with pytest.raises(module.ConsoleError):
        module.online_players(
            f"There are 2/20 players online:player ({identity}), other ({identity})"
        )


@pytest.mark.parametrize(
    "change",
    [{"host": "0.0.0.0"}, {"port": True}, {"port": 65536}, {"adapter": "unknown"}],
)
def test_nonloopback_or_unknown_adapter_rejected(change):
    with pytest.raises(module.ConsoleError):
        module.ConsoleConfig(
            **{"port": 25577, "credential_file": "rcon.json", **change}
        )


def test_kick_uses_only_uuid_and_checks_disconnect(monkeypatch):
    first, unrelated = str(uuid4()), str(uuid4())
    calls = []
    replies = iter(
        [
            f"There are 2/20 players online:target ({first}), other ({unrelated})",
            "ignored kick output",
            f"There are 1/20 players online:other ({unrelated})",
        ]
    )
    monkeypatch.setattr(
        module, "command", lambda _c, _p, text: calls.append(text) or next(replies)
    )
    client = module.RecoveryConsole(module.ConsoleConfig(25577, "rcon.json"), "secret")
    client.disconnect([first])
    assert calls == ["list uuids", f"kick {first} omk_account_recovery", "list uuids"]


@pytest.mark.parametrize("command", ["stop", "kick @a", "list uuids\nstop"])
def test_unrestricted_commands_never_open_connection(monkeypatch, command):
    monkeypatch.setattr(
        module.socket,
        "create_connection",
        lambda *a, **kw: pytest.fail("connection opened"),
    )
    with pytest.raises(module.ConsoleError):
        module.command(
            module.ConsoleConfig(25577, "rcon.json"), "private-password", command
        )


def test_actual_loopback_framing_handles_split_packets_and_never_returns_sentinel():
    failures = []
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)

        def serve():
            try:
                with listener.accept()[0] as stream:
                    stream.settimeout(3)
                    assert module._receive(stream, time.monotonic() + 3) == (
                        1,
                        3,
                        "private-test-password",
                    )
                    stream.sendall(module._packet(1, 2, ""))
                    assert module._receive(stream, time.monotonic() + 3) == (
                        2,
                        2,
                        "list uuids",
                    )
                    # Do not require the client to pipeline an unread next command.
                    stream.sendall(module._packet(2, 0, "There are 0/"))
                    assert module._receive(stream, time.monotonic() + 3) == (
                        3,
                        2,
                        "list uuids",
                    )
                    response = (
                        module._packet(2, 0, "20 players online:")
                        + module._packet(3, 0, "sentinel body")
                    )
                    for part in (response[:3], response[3:17], response[17:]):
                        stream.sendall(part)
            except Exception as error:
                failures.append(error)

        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        result = module.command(
            module.ConsoleConfig(listener.getsockname()[1], "rcon.json"),
            "private-test-password",
            "list uuids",
        )
        thread.join(timeout=4)
        assert not thread.is_alive() and not failures
        assert module.online_players(result) == {}


@pytest.mark.parametrize("body", [struct.pack("<i", 999999), struct.pack("<i", -1)])
def test_untrusted_frame_length_rejected_without_allocating_payload(body):
    class Stream:
        def settimeout(self, _):
            pass

        def recv(self, _):
            return body

    with pytest.raises(module.ConsoleError):
        module._receive(Stream(), float("inf"))
