import json

import pytest

from omk.cli import main
from omk.owner.panels import owner_moderation as moderation
from tests.fixtures.unit.owner.owner_moderation import UID, reply, setup

TOKEN = "f" * 64


def lookup(text, **changes):
    return "OMK_BAN_LOOKUP_V1 " + json.dumps(
        {
            "nonce": text.split()[3],
            "player": "TestPlayer",
            "uuid": UID,
            "token": TOKEN,
            "error": None,
            **changes,
        }
    )


def test_unban_resolves_offline_native_ban_and_binds_the_specific_entry(
    tmp_path, monkeypatch
):
    path = setup(tmp_path, monkeypatch)
    calls = []

    def command(endpoint, password, text):
        calls.append(text)
        if "lookup-ban" in text:
            return lookup(text)
        assert text.split()[-2] == TOKEN
        return reply(text, expires_at=None)

    monkeypatch.setattr("omk.labs.recovery.recovery_console.command", command)
    result = moderation.run(path, "dj2", "unban", "testplayer")
    assert (
        result["ok"] and result["effect"] == "applied" and result["expires_at"] is None
    )
    assert result["player"] == "testplayer" and len(calls) == 2
    assert (
        "lookup-ban" in calls[0] and "unban" in calls[1] and "list uuids" not in calls
    )
    assert f"{UID} TestPlayer 0 {TOKEN}" in calls[1]


def test_missing_ban_is_read_only_and_not_a_remote_profile_search(
    tmp_path, monkeypatch
):
    path = setup(tmp_path, monkeypatch)
    calls = []

    def command(endpoint, password, text):
        calls.append(text)
        return lookup(text, uuid=None, token=None, error="not_banned")

    monkeypatch.setattr("omk.labs.recovery.recovery_console.command", command)
    result = moderation.run(path, "dj2", "unban", "TestPlayer")
    assert (
        result["error"] == "not_banned"
        and result["effect"] == "none"
        and len(calls) == 1
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"nonce": "0" * 32},
        {"player": "OtherPlayer"},
        {"uuid": "invalid"},
        {"token": "invalid"},
        {"uuid": None},
        {"error": "refused"},
        {"extra": True},
    ],
)
def test_invalid_ban_lookup_cannot_dispatch_unban(tmp_path, monkeypatch, changes):
    path = setup(tmp_path, monkeypatch)
    calls = []

    def command(endpoint, password, text):
        calls.append(text)
        return lookup(text, **changes)

    monkeypatch.setattr("omk.labs.recovery.recovery_console.command", command)
    result = moderation.run(path, "dj2", "unban", "TestPlayer")
    assert not result["ok"] and result["effect"] == "none" and len(calls) == 1


@pytest.mark.parametrize("fault", ["changed", "lost_lookup", "lost_mutation"])
def test_unban_uncertainty_and_changed_ban_never_retry(tmp_path, monkeypatch, fault):
    path = setup(tmp_path, monkeypatch)
    calls = []

    def command(endpoint, password, text):
        calls.append(text)
        if "lookup-ban" in text:
            if fault == "lost_lookup":
                raise OSError("private details")
            return lookup(text)
        if fault == "lost_mutation":
            raise OSError("private details")
        return reply(text, ok=False, effect="none", expires_at=None, error="changed")

    monkeypatch.setattr("omk.labs.recovery.recovery_console.command", command)
    result = moderation.run(path, "dj2", "unban", "TestPlayer")
    assert not result["ok"] and len(calls) == (1 if fault == "lost_lookup" else 2)
    assert result["effect"] == ("unknown" if fault == "lost_mutation" else "none")
    assert "private details" not in str(result)


def test_unban_rejects_duration_before_transport(tmp_path, monkeypatch):
    path = setup(tmp_path, monkeypatch)
    result = moderation.run(path, "dj2", "unban", "TestPlayer", duration="1d")
    assert (
        not result["ok"]
        and result["effect"] == "none"
        and result["error"] == "invalid_request"
    )


def test_cli_unban_needs_no_fake_online_player_or_ban_confirmation(
    tmp_path, monkeypatch, capsys
):
    path = setup(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "omk.labs.recovery.recovery_console.command",
        lambda endpoint, password, text: (
            lookup(text) if "lookup-ban" in text else reply(text, expires_at=None)
        ),
    )
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
                "unban",
                "--player",
                "TestPlayer",
            ]
        )
        == 0
    )
    result = moderation.ModerationResult.model_validate_json(capsys.readouterr().out)
    assert result.ok and result.command == "unban"
