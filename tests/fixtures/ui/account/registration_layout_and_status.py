"""Test dependencies for registration layout and status."""

import pytest

from launcher.accounts import AccountService
from launcher.app import LauncherWindow
from launcher.game import GameRunner
from launcher.storage import FileSessionStore
from tests.fixtures.fakes import FakeDrasl


@pytest.fixture
def window(qtbot, tmp_path):
    service = AccountService(FakeDrasl(), FileSessionStore(tmp_path / "session.json"))
    window = LauncherWindow(service, runner=GameRunner(tmp_path), auto_restore=False)
    qtbot.addWidget(window)
    window.show()
    return window
