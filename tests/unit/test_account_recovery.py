import copy
import json
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest

from omk import account_recovery as recovery
from omk.admin import AdminError, _write_private
from omk.cli import main
from omk.recovery_console import ConsoleConfig
from tests.unit.test_operator_commands import config


@pytest.fixture
def setup(tmp_path, monkeypatch):
    cfg, path = config(tmp_path)
    cfg = replace(cfg, recovery_consoles={"dj2": ConsoleConfig(25577, "rcon.json")})
    _write_private(
        cfg.private / "rcon.json", cfg.private, {"password": "private-rcon-secret"}
    )
    account, operator = str(uuid4()), str(uuid4())
    players = [
        {"uuid": str(uuid4()), "name": "player" + str(i), "userUuid": account}
        for i in range(2)
    ]
    user = {
        "uuid": account,
        "username": "test_player",
        "isAdmin": False,
        "isLocked": False,
        "players": players,
    }
    calls, passwords = [], []

    def request(method, route, payload=None, token=None):
        calls.append((method, route, copy.deepcopy(payload)))
        if method == "PATCH":
            user.update({k: v for k, v in payload.items() if k == "isLocked"})
            if "password" in payload:
                passwords.append(payload["password"])
        return (
            [copy.deepcopy(user)] if route.endswith("/users") else copy.deepcopy(user)
        )

    client = Mock(request=Mock(side_effect=request))
    monkeypatch.setattr(
        recovery, "_operator", lambda _: (client, "admin-secret", operator)
    )
    console = Mock()
    console.online.return_value = {}
    console.remaining.return_value = 0
    monkeypatch.setattr(recovery, "RecoveryConsole", lambda *a: console)
    return SimpleNamespace(
        config=cfg,
        path=path,
        user=user,
        account=account,
        players=players,
        calls=calls,
        passwords=passwords,
        client=client,
        console=console,
    )


def test_plan_is_non_mutating_and_preserves_all_game_profiles(setup):
    result = recovery.prepare(setup.config, "TEST_PLAYER")
    assert (
        result["ok"] and len(result["players"]) == 2 and not result["account_changed"]
    )
    assert not any(method == "PATCH" for method, _, _ in setup.calls)
    assert (
        recovery.status(setup.config, setup.account)["recovery"]["stage"] == "planned"
    )


def test_complete_recovery_orders_lock_reset_disconnect_unlock_and_never_saves_secret(
    setup,
):
    recovery.prepare(setup.config, "test_player")
    output = []

    def disconnect(players):
        assert setup.user["isLocked"]
        assert set(players) == {p["uuid"] for p in setup.players}
        assert len(setup.passwords) == 1

    setup.console.disconnect.side_effect = disconnect
    result = recovery.execute(setup.config, setup.account, emit=output.append)
    assert result["ok"] and not setup.user["isLocked"] and output == setup.passwords
    mutations = [payload for method, _, payload in setup.calls if method == "PATCH"]
    assert mutations[0] == {"isLocked": True} and mutations[-1] == {"isLocked": False}
    assert mutations[1]["resetApiToken"] and mutations[1]["resetMinecraftToken"]
    data = "".join(p.read_text() for p in setup.config.private.rglob("*.json"))
    assert output[0] not in data and "admin-secret" not in data
    with pytest.raises(AdminError):
        recovery.execute(setup.config, setup.account, resume=True, emit=output.append)


def test_server_failure_preflight_never_locks_or_changes_password(setup):
    recovery.prepare(setup.config, "test_player")
    setup.console.online.side_effect = OSError("secret-server-details")
    with pytest.raises(OSError):
        recovery.execute(setup.config, setup.account, emit=pytest.fail)
    assert not setup.user["isLocked"] and not setup.passwords
    assert (
        recovery.status(setup.config, setup.account)["recovery"]["stage"] == "planned"
    )


def test_second_server_failure_keeps_account_locked_and_explicit_resume_rotates_again(
    setup,
):
    cfg = replace(
        setup.config,
        servers={**setup.config.servers, "second": setup.config.private},
        recovery_consoles={
            **setup.config.recovery_consoles,
            "second": ConsoleConfig(25578, "rcon.json"),
        },
    )
    recovery.prepare(cfg, "test_player")
    setup.console.disconnect.side_effect = [None, OSError("private-error")]
    delivered = []
    with pytest.raises(AdminError, match="incomplete"):
        recovery.execute(cfg, setup.account, emit=delivered.append)
    record = recovery.status(cfg, setup.account)["recovery"]
    assert record["stage"] == "incomplete" and record["lock_confirmed_after_failure"]
    assert setup.user["isLocked"] and not delivered
    with pytest.raises(AdminError, match="explicit resume"):
        recovery.execute(cfg, setup.account, emit=delivered.append)
    setup.console.disconnect.side_effect = None
    assert recovery.execute(cfg, setup.account, resume=True, emit=delivered.append)[
        "ok"
    ]
    assert len(setup.passwords) == 2 and setup.passwords[0] != delivered[0]
    assert delivered == [setup.passwords[1]]
    assert "private-error" not in json.dumps(recovery.status(cfg, setup.account))


@pytest.mark.parametrize("phase", ["lock", "reset", "unlock", "delivery"])
def test_ambiguous_reply_or_delivery_failure_never_reports_success(setup, phase):
    recovery.prepare(setup.config, "test_player")
    original = setup.client.request.side_effect
    failed = False

    def request(method, route, payload=None, token=None):
        nonlocal failed
        value = original(method, route, payload, token)
        condition = payload and (
            (phase == "lock" and payload.get("isLocked") is True)
            or (phase == "unlock" and payload.get("isLocked") is False)
            or (phase == "reset" and "password" in payload)
        )
        if condition and not failed:
            failed = True
            raise OSError("private reply lost")
        return value

    setup.client.request.side_effect = request
    emit = (
        Mock(side_effect=OSError("private terminal error"))
        if phase == "delivery"
        else Mock()
    )
    with pytest.raises(AdminError, match="incomplete"):
        recovery.execute(setup.config, setup.account, emit=emit)
    assert setup.user["isLocked"]
    record = recovery.status(setup.config, setup.account)["recovery"]
    assert record["stage"] == "incomplete" and "private" not in json.dumps(record)


@pytest.mark.parametrize("change", ["uuid", "name", "new-profile", "admin"])
def test_changed_target_cannot_be_silently_recovered(setup, change):
    recovery.prepare(setup.config, "test_player")
    if change == "new-profile":
        setup.user["players"].append(
            {"uuid": str(uuid4()), "name": "new_player", "userUuid": setup.account}
        )
    elif change == "admin":
        setup.user["isAdmin"] = True
    else:
        setup.user["players"][0][change] = (
            str(uuid4()) if change == "uuid" else "different"
        )
    with pytest.raises(AdminError):
        recovery.execute(setup.config, setup.account, emit=pytest.fail)
    assert not setup.passwords


def test_changed_config_and_missing_server_adapter_fail_before_mutation(setup):
    recovery.prepare(setup.config, "test_player")
    bad = replace(
        setup.config, servers={**setup.config.servers, "missing": setup.config.private}
    )
    with pytest.raises(AdminError, match="Every configured server"):
        recovery.execute(bad, setup.account, emit=pytest.fail)
    bad = replace(
        setup.config, recovery_consoles={"dj2": ConsoleConfig(25579, "rcon.json")}
    )
    with pytest.raises(AdminError, match="differs"):
        recovery.execute(bad, setup.account, emit=pytest.fail)
    assert not setup.passwords


def test_parallel_operator_attempt_cannot_enter_mutation(setup):
    recovery.prepare(setup.config, "test_player")
    with recovery._locked(setup.config), pytest.raises(OSError):
        recovery.execute(setup.config, setup.account, emit=pytest.fail)
    assert not setup.passwords


def test_cli_refuses_nonterminal_password_output_before_mutation(
    setup, monkeypatch, capsys
):
    monkeypatch.setattr("omk.admin.load_operator_config", lambda _: setup.config)
    monkeypatch.setattr(recovery.sys.stdin, "isatty", lambda: False)
    assert (
        main(
            [
                "admin",
                "--config",
                str(setup.path),
                "recover-account",
                "run",
                "--account",
                setup.account,
            ]
        )
        == 1
    )
    assert "private terminal" in capsys.readouterr().out
    assert not setup.passwords


def test_full_journal_before_lock_never_mutates_account(setup, monkeypatch):
    recovery.prepare(setup.config, "test_player")
    monkeypatch.setattr(recovery, "_save", Mock(side_effect=OSError("disk full")))
    with pytest.raises(OSError):
        recovery.execute(setup.config, setup.account, emit=pytest.fail)
    assert not setup.user["isLocked"] and not setup.passwords


def test_journal_failure_after_reset_does_not_unlock_account(setup, monkeypatch):
    recovery.prepare(setup.config, "test_player")
    original = recovery._save

    def save(config, record, stage):
        if stage == "disconnecting":
            raise OSError("disk full")
        return original(config, record, stage)

    monkeypatch.setattr(recovery, "_save", save)
    delivered = []
    with pytest.raises(AdminError):
        recovery.execute(setup.config, setup.account, emit=delivered.append)
    assert setup.user["isLocked"] and len(setup.passwords) == 1 and not delivered
