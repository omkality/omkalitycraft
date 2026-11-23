from types import SimpleNamespace
from unittest.mock import Mock

from omk.cli import main
from omk.game import project_moderation as moderation
from omk.owner.panels import owner_player_stats as stats
from tests.fixtures.unit.game.project_moderation import UUID, project

__all__ = ["project"]


def test_stats_cli_reads_saved_time_and_active_and_past_moderation(
    project, capsys, monkeypatch
):
    assert moderation.run(
        project.path, "ban", "FirstJoin", duration="1d", reason="Спам", confirmed=True
    )["ok"]
    assert moderation.run(project.path, "unban", "FirstJoin")["ok"]
    assert moderation.run(
        project.path, "mute", "FirstJoin", duration="20m", reason="Флуд"
    )["ok"]
    project.online.clear()
    lookup = Mock(return_value=(UUID, "FirstJoin"))
    monkeypatch.setattr(
        stats, "_client", lambda _: SimpleNamespace(game_profile=lookup)
    )
    monkeypatch.setattr(stats, "credential", lambda *_: ("alpha", "private"))
    transport = Mock(return_value="There are 0/4 players online:")
    monkeypatch.setattr(stats, "command", transport)
    saved = Mock(
        return_value={"available": True, "ticks": 150_000, "active_millis": 3_662_000}
    )
    monkeypatch.setattr(stats, "saved_playtime", saved)
    assert (
        main(
            [
                "admin",
                "--config",
                str(project.path),
                "player-stats",
                "--server",
                "alpha",
                "--player",
                "firstjoin",
            ]
        )
        == 0
    )
    result = stats.Result.model_validate_json(capsys.readouterr().out)
    assert result.ok and result.player == "firstjoin" and result.server_id == "alpha"
    assert "Сейчас не в игре" in result.output
    assert "1 ч 01 мин 02 с" in result.output
    assert "Флуд" in result.output
    assert "Спам" in result.output and "Разбан" in result.output
    assert UUID not in result.output and "private" not in result.output
    lookup.assert_called_once_with("firstjoin")
    transport.assert_called_once_with("alpha", "private", "list uuids")
    assert saved.call_args.args[1:] == ("alpha", UUID)


def test_missing_stats_and_profile_are_distinct_from_zero(project, monkeypatch):
    lookup = Mock(return_value=(UUID, "FirstJoin"))
    monkeypatch.setattr(
        stats, "_client", lambda _: SimpleNamespace(game_profile=lookup)
    )
    monkeypatch.setattr(stats, "saved_playtime", lambda *_: {"available": False})
    first = stats.run(project.path, "alpha", "FirstJoin")
    assert first["ok"] and "Активное время появится после игры" in first["output"]
    assert "0 ч" not in first["output"]
    lookup.return_value = None
    missing = stats.run(project.path, "alpha", "FirstJoin")
    assert not missing["ok"] and missing["error"] == "profile_not_found"
