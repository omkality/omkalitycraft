from unittest.mock import Mock

import pytest

from omk import owner_console as console
from omk.admin import _write_private
from omk.cli import main
from omk.recovery_console import ConsoleConfig
from tests.unit.test_operator_commands import config


@pytest.mark.parametrize("action,text", console.COMMANDS.items())
def test_fixed_actions_use_private_transport_once(tmp_path, monkeypatch, action, text):
    _, path = config(tmp_path)
    monkeypatch.setattr(
        "omk.admin_maintenance.credential",
        lambda *a: (ConsoleConfig(25577, "rcon.json"), "synthetic-private-password"),
    )
    command = Mock(return_value="Server response\nsecond line")
    monkeypatch.setattr("omk.recovery_console.command", command)
    result = console.run(path, "dj2", action, confirmed=True)
    assert console.ConsoleResult.model_validate(result).ok
    assert command.call_count == 1 and command.call_args.args[2] == text
    assert result["effect"] == ("unknown" if action == "save" else "none")


def test_unconfirmed_save_or_unbound_server_does_not_touch_transport(
    tmp_path, monkeypatch
):
    _, path = config(tmp_path)
    command = Mock(side_effect=AssertionError("must not dispatch"))
    monkeypatch.setattr("omk.recovery_console.command", command)
    assert console.run(path, "dj2", "save")["error"] == "invalid_configuration"
    assert console.run(path, "other", "players")["error"] == "invalid_configuration"
    command.assert_not_called()


def test_lost_save_reply_keeps_effect_unknown_without_retry(tmp_path, monkeypatch):
    _, path = config(tmp_path)
    monkeypatch.setattr(
        "omk.admin_maintenance.credential",
        lambda *a: (ConsoleConfig(25577, "rcon.json"), "synthetic-private-password"),
    )
    command = Mock(side_effect=OSError("private details"))
    monkeypatch.setattr("omk.recovery_console.command", command)
    result = console.run(path, "dj2", "save", confirmed=True)
    assert not result["ok"] and result["effect"] == "unknown"
    assert "private details" not in str(result) and command.call_count == 1


def test_terminal_controls_and_credential_echo_are_not_forwarded(tmp_path, monkeypatch):
    _, path = config(tmp_path)
    monkeypatch.setattr(
        "omk.admin_maintenance.credential",
        lambda *a: (ConsoleConfig(25577, "rcon.json"), "synthetic-private-password"),
    )
    monkeypatch.setattr(
        "omk.recovery_console.command", lambda *a: "hello\x1b[2J\u202eworld"
    )
    assert "\x1b" not in console.run(path, "dj2", "tps")["output"]
    monkeypatch.setattr(
        "omk.recovery_console.command", lambda *a: "synthetic-private-password"
    )
    assert not console.run(path, "dj2", "tps")["ok"]


def test_real_cli_routes_without_overwriting_top_level_command(tmp_path, capsys):
    settings, path = config(tmp_path)
    _write_private(
        settings.private / "rcon.json",
        settings.private,
        {"password": "synthetic-private-password"},
    )
    assert (
        main(
            [
                "admin",
                "--config",
                str(path),
                "console",
                "--server",
                "dj2",
                "--command",
                "players",
            ]
        )
        == 1
    )
    result = console.ConsoleResult.model_validate_json(capsys.readouterr().out)
    assert result.command == "players" and result.server_id == "dj2"
