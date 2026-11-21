"""Fixtures for the launcher window during game startup."""

import pytest

from launcher.accounts import AccountService
from launcher.app import LauncherWindow
from launcher.game import GameRunner
from launcher.install import Installer, ReleaseClient
from launcher.memory import MemorySnapshot
from launcher.storage import FileSessionStore
from tests.fixtures.fakes import FakeDrasl


@pytest.fixture
def game_launch_window(qtbot, tmp_path, monkeypatch):
    monkeypatch.setattr(
        MemorySnapshot, "read", classmethod(lambda cls: MemorySnapshot(16384, 12000))
    )
    monkeypatch.setattr(
        Installer, "local_state", lambda *_: {"state": "installed", "version": "2.23.4"}
    )
    service = AccountService(
        FakeDrasl(), FileSessionStore(tmp_path / "userdata/session.json")
    )
    widget = LauncherWindow(
        service,
        auto_restore=False,
        installer=Installer(tmp_path, ReleaseClient("https://test.invalid", {})),
        runner=GameRunner(tmp_path),
    )
    qtbot.addWidget(widget)
    assert widget.installation.pool.waitForDone(5000)
    widget.pages.setCurrentWidget(widget.home_page)
    widget.show()
    qtbot.waitUntil(lambda: widget.home_page.cards["dj2"].installed)
    return widget
