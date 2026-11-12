import copy
import json
import socket
import threading
import time

import pytest

from omk import (
    maintenance_console as module,
    recovery_console as rcon,
)

BOOT, OP = "a" * 32, "b" * 32
ADAPTER = "ftb-backups-1.1.0.1-disabled-v1"
PROBE = {
    "schema": 1,
    "boot": BOOT,
    "main_thread": True,
    "backup_adapter": ADAPTER,
    "automatic_backups_disabled": True,
    "backup_running": False,
}
RECEIPT = {
    "schema": 1,
    "boot": BOOT,
    "main_thread": True,
    "operation": OP,
    "seconds_before": 60,
    "delivered": 2,
    "replayed": False,
}


def client(monkeypatch, response, calls=None):
    monkeypatch.setattr(
        module,
        "command",
        lambda _c, _p, text: (calls.append(text) if calls is not None else None)
        or "OMK_MAINTENANCE_V1 " + json.dumps(response),
    )
    return module.MaintenanceConsole(
        rcon.ConsoleConfig(25577, "credential.json"), "fixture-password-12345"
    )


def test_typed_loaded_state_and_notice_keep_boot_and_operation(monkeypatch):
    calls = []
    actor = client(monkeypatch, PROBE, calls)
    assert actor.ready(ADAPTER, boot=BOOT) == PROBE
    client(monkeypatch, RECEIPT, calls)
    assert actor.warn(BOOT, OP, 60) == RECEIPT
    assert calls == [
        "list omk-maintenance probe",
        f"list omk-maintenance warn {BOOT} {OP} 60",
    ]


@pytest.mark.parametrize(
    "change",
    [
        {"schema": True},
        {"boot": "bad"},
        {"main_thread": False},
        {"automatic_backups_disabled": 1},
        {"backup_running": 0},
        {"backup_adapter": "bad\ncommand"},
        {"extra": True},
    ],
)
def test_invalid_loaded_state_fails_closed(monkeypatch, change):
    with pytest.raises(rcon.ConsoleError):
        client(monkeypatch, {**PROBE, **change}).probe()


@pytest.mark.parametrize(
    "change",
    [
        {"automatic_backups_disabled": False},
        {"backup_running": True},
        {"backup_adapter": "unavailable"},
        {"boot": "c" * 32},
    ],
)
def test_busy_enabled_unknown_or_restarted_server_not_ready(monkeypatch, change):
    with pytest.raises(rcon.ConsoleError, match="not ready"):
        client(monkeypatch, {**PROBE, **change}).ready(ADAPTER, boot=BOOT)


@pytest.mark.parametrize(
    "change",
    [
        {"boot": "c" * 32},
        {"operation": "c" * 32},
        {"seconds_before": True},
        {"seconds_before": 30},
        {"delivered": True},
        {"delivered": -1},
        {"delivered": 10001},
        {"replayed": 1},
        {"extra": True},
    ],
)
def test_unmatched_or_invalid_notice_ack_cannot_mean_sent(monkeypatch, change):
    with pytest.raises(rcon.ConsoleError):
        client(monkeypatch, {**RECEIPT, **change}).warn(BOOT, OP, 60)


@pytest.mark.parametrize(
    "args",
    [
        (BOOT, OP, 0),
        (BOOT, OP, 3601),
        (BOOT, OP, True),
        ("bad", OP, 60),
        (BOOT, "bad", 60),
    ],
)
def test_invalid_notice_never_opens_transport(monkeypatch, args):
    monkeypatch.setattr(module, "command", lambda *a: pytest.fail("transport opened"))
    with pytest.raises(rcon.ConsoleError):
        module.MaintenanceConsole(None, "fixture").warn(*args)


@pytest.mark.parametrize(
    "response",
    [
        "Unknown command",
        "OMK_MAINTENANCE_ERROR refused",
        "OMK_MAINTENANCE_V1 {",
        "OMK_MAINTENANCE_V1 []",
    ],
)
def test_missing_or_failed_bridge_never_ready(monkeypatch, response):
    monkeypatch.setattr(module, "command", lambda *a: response)
    with pytest.raises(rcon.ConsoleError):
        module.MaintenanceConsole(None, "fixture").probe()


@pytest.mark.parametrize(
    "suffix",
    [
        f"warn {BOOT} {OP} 0",
        f"warn {BOOT} {OP} 3601",
        f"warn {BOOT} {OP} 01",
        f"warn {BOOT} {OP} 60\nstop",
        "say arbitrary-text",
    ],
)
def test_transport_rejects_noncanonical_or_unrestricted_requests(monkeypatch, suffix):
    monkeypatch.setattr(
        rcon.socket, "create_connection", lambda *a, **kw: pytest.fail("network opened")
    )
    with pytest.raises(rcon.ConsoleError):
        rcon.command(
            rcon.ConsoleConfig(25577, "credential.json"),
            "fixture-password",
            "list omk-maintenance " + suffix,
        )


def test_real_socket_notice_ack_round_trip_and_replayed_receipt():
    errors, requests = [], []
    value = copy.deepcopy(RECEIPT)
    value["replayed"] = True
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)

        def serve():
            try:
                with listener.accept()[0] as stream:
                    stream.settimeout(3)
                    deadline = time.monotonic() + 5
                    assert rcon._receive(stream, deadline) == (
                        1,
                        3,
                        "fixture-password-12345",
                    )
                    stream.sendall(rcon._packet(1, 2, ""))
                    number, kind, text = rcon._receive(stream, deadline)
                    requests.append(text)
                    assert (number, kind) == (2, 2)
                    payload = "OMK_MAINTENANCE_V1 " + json.dumps(value)
                    stream.sendall(rcon._packet(2, 0, payload[:45]))
                    assert rcon._receive(stream, deadline) == (3, 2, "list uuids")
                    stream.sendall(
                        rcon._packet(2, 0, payload[45:])
                        + rcon._packet(3, 0, "sentinel")
                    )
            except Exception as error:
                errors.append(type(error).__name__)

        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        actor = module.MaintenanceConsole(
            rcon.ConsoleConfig(listener.getsockname()[1], "credential.json"),
            "fixture-password-12345",
        )
        assert actor.warn(BOOT, OP, 60) == value
        thread.join(5)
        assert not thread.is_alive() and not errors
        assert requests == [f"list omk-maintenance warn {BOOT} {OP} 60"]
