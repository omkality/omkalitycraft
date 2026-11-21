"""End-to-end Qt state transitions around the Play button."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from launcher.controller import InstallationResult
from launcher.game import GameProcess
from launcher.releases import ReleaseError
from tests.fixtures.ui.catalog.game_launch import game_launch_window

__all__ = ["game_launch_window"]


@pytest.mark.parametrize("exit_code", [0, 1])
def test_play_locks_memory_and_hides_window_until_game_exits(
    game_launch_window, tmp_path, monkeypatch, exit_code
):
    window = game_launch_window
    card = window.home_page.cards["dj2"]
    assert card.memory.slider.isEnabled()
    play = Mock()
    monkeypatch.setattr(window.installation, "start", play)

    memory_mb = card.memory.selected_mb
    card.action.click()
    play.assert_called_once_with("dj2", play=True, memory_mb=memory_mb)
    assert not card.memory.slider.isEnabled()
    assert window.isVisible()

    process = Mock()
    process.poll.return_value = None
    game = GameProcess(process, tmp_path / "game.log", tmp_path)
    result = InstallationResult(SimpleNamespace(version="2.23.4"), tmp_path, game)
    window.installation.completed.emit("dj2", result)
    assert window.isHidden()
    assert not card.memory.slider.isEnabled()
    assert window.game_timer.isActive()

    process.poll.return_value = exit_code
    window._poll_game()
    assert window.isHidden()
    game.diagnostics_done.set()
    window._poll_game()
    assert window.isVisible()
    assert card.memory.slider.isEnabled()
    assert card.action.text() == "Играть"
    assert bool(window.status.text()) is bool(exit_code)


def test_startup_failure_unlocks_memory_without_hiding(game_launch_window, monkeypatch):
    window = game_launch_window
    card = window.home_page.cards["dj2"]
    monkeypatch.setattr(window.installation, "start", Mock())
    card.action.click()
    assert not card.memory.slider.isEnabled()

    window.installation.failed.emit("dj2", ReleaseError("Ошибка запуска"))
    assert window.isVisible()
    assert card.memory.slider.isEnabled()
    assert card.state_label.text() == "Ошибка запуска"


def test_install_without_start_keeps_launcher_visible(
    game_launch_window, tmp_path, monkeypatch
):
    window = game_launch_window
    card = window.home_page.cards["dj2"]
    card.installed = False
    start = Mock()
    monkeypatch.setattr(window.installation, "start", start)
    card.action.click()
    start.assert_called_once_with("dj2", play=False, memory_mb=card.memory.selected_mb)

    result = InstallationResult(SimpleNamespace(version="2.23.4"), tmp_path)
    window.installation.completed.emit("dj2", result)
    assert window.isVisible()
    assert card.memory.slider.isEnabled()
    assert card.action.text() == "Играть"
