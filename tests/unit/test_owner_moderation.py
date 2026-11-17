import base64
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from omk import owner_moderation as moderation
from omk.cli import main
from omk.recovery_console import ConsoleConfig
from tests.unit.test_operator_commands import config

UID = "12345678-1234-1234-1234-123456789abc"
ONLINE = f"There are 1/4 players online:\nTestPlayer ({UID})"


@pytest.mark.parametrize(
    "value,seconds",
    [("10m", 600), ("20h", 72000), ("1d", 86400), ("1s", 1), ("365d", 31536000)],
)
def test_durations(value, seconds):
    assert moderation.duration_seconds(value) == seconds


@pytest.mark.parametrize(
    "value", ["", "0s", "01d", "-1m", "1d2h", "1D", "366d", "99999999w", "1m\n", "1💩"]
)
def test_invalid_durations(value):
    with pytest.raises(ValueError):
        moderation.duration_seconds(value)


def setup(tmp_path, monkeypatch):
    _, path = config(tmp_path)
    monkeypatch.setattr(
        "omk.admin_maintenance.credential",
        lambda *a: (ConsoleConfig(25577, "rcon.json"), "synthetic-private-password"),
    )
    return path


def reply(text, **overrides):
    parts = text.split()
    return "OMK_MODERATION_V1 " + json.dumps(
        {
            "command": parts[2],
            "nonce": parts[3],
            "uuid": parts[4],
            "ok": True,
            "effect": "applied",
            "expires_at": None if parts[2] == "kick" else 2000000000,
            "error": None,
            **overrides,
        }
    )


@pytest.mark.parametrize("action", ["kick", "ban", "mute"])
def test_one_correlated_mutation_with_encoded_reason(tmp_path, monkeypatch, action):
    path = setup(tmp_path, monkeypatch)
    calls = []

    def command(endpoint, password, text):
        calls.append(text)
        return ONLINE if text == "list uuids" else reply(text)

    monkeypatch.setattr("omk.recovery_console.command", command)
    result = moderation.run(
        path,
        "dj2",
        action,
        "TestPlayer",
        duration="" if action == "kick" else "10m",
        reason='Причина /ban @a; "hello"',
        confirmed=True,
    )
    assert result["ok"] and result["effect"] == "applied"
    assert len(calls) == 2 and calls[0] == "list uuids"
    assert f"{UID} TestPlayer {0 if action == 'kick' else 600}" in calls[1]
    encoded = calls[1].split()[-2]
    assert (
        base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)).decode()
        == 'Причина /ban @a; "hello"'
    )


@pytest.mark.parametrize(
    "action,player,duration,reason,confirm",
    [
        ("ban", "TestPlayer", "1d", "", False),
        ("mute", "TestPlayer", "0m", "", True),
        ("kick", "TestPlayer", "1m", "", True),
        ("kick", "@a", "", "", True),
        ("kick", "TestPlayer", "", "bad\nreason", True),
        ("mute", "TestPlayer", "1d", "bad\u202ereason", True),
    ],
)
def test_invalid_request_never_reaches_transport(
    tmp_path, monkeypatch, action, player, duration, reason, confirm
):
    path = setup(tmp_path, monkeypatch)
    command = Mock(side_effect=AssertionError("must not send"))
    monkeypatch.setattr("omk.recovery_console.command", command)
    assert (
        moderation.run(
            path,
            "dj2",
            action,
            player,
            duration=duration,
            reason=reason,
            confirmed=confirm,
        )["error"]
        == "invalid_request"
    )
    command.assert_not_called()


def test_private_owner_guard_precedes_credential_or_network(tmp_path, monkeypatch):
    _, path = config(tmp_path)
    monkeypatch.setattr(
        moderation, "load_operator_config", Mock(side_effect=PermissionError())
    )
    credential = Mock(side_effect=AssertionError("must not read"))
    monkeypatch.setattr("omk.admin_maintenance.credential", credential)
    assert moderation.run(path, "dj2", "kick", "TestPlayer")["effect"] == "none"
    credential.assert_not_called()


@pytest.mark.parametrize(
    "fault", ["lost", "nonce", "uuid", "command", "effect", "extra", "no_bridge"]
)
def test_uncertain_response_never_resends_mutation(tmp_path, monkeypatch, fault):
    path = setup(tmp_path, monkeypatch)
    calls = []

    def command(endpoint, password, text):
        calls.append(text)
        if text == "list uuids":
            return ONLINE
        if fault == "lost":
            raise OSError("private transport diagnostic")
        if fault == "no_bridge":
            return ONLINE
        changes = {
            "nonce": {"nonce": "0" * 32},
            "uuid": {"uuid": "0" * 36},
            "command": {"command": "ban"},
            "effect": {"effect": "none"},
            "extra": {"unexpected": True},
        }
        return reply(text, **changes[fault])

    monkeypatch.setattr("omk.recovery_console.command", command)
    result = moderation.run(path, "dj2", "mute", "TestPlayer", duration="10m")
    assert not result["ok"] and result["effect"] == "unknown" and len(calls) == 2
    assert "private transport" not in str(result)


def test_offline_target_is_not_a_typo_ban_or_remote_profile_lookup(
    tmp_path, monkeypatch
):
    path = setup(tmp_path, monkeypatch)
    command = Mock(return_value=ONLINE)
    monkeypatch.setattr("omk.recovery_console.command", command)
    result = moderation.run(
        path, "dj2", "ban", "WrongName", duration="1d", confirmed=True
    )
    assert (
        result["error"] == "player_offline"
        and result["effect"] == "none"
        and command.call_count == 1
    )


def test_cli_ban_requires_its_own_confirmation(tmp_path, capsys):
    _, path = config(tmp_path)
    assert (
        main(
            [
                "admin",
                "--config",
                str(path),
                "moderation",
                "--server",
                "dj2",
                "--command",
                "ban",
                "--player",
                "TestPlayer",
                "--duration",
                "1d",
            ]
        )
        == 1
    )
    result = moderation.ModerationResult.model_validate_json(capsys.readouterr().out)
    assert (
        result.command == "ban"
        and result.effect == "none"
        and result.error == "invalid_request"
    )


def test_published_moderation_schema_matches_model():
    path = Path(__file__).parents[2] / "docs/contracts/owner-moderation-v1.schema.json"
    assert (
        json.loads(path.read_text(encoding="utf-8"))
        == moderation.ModerationResult.model_json_schema()
    )
