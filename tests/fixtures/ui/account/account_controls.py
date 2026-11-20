"""Test dependencies for account controls."""

import pytest

from launcher.accounts import AccountService
from launcher.app import LauncherWindow
from launcher.storage import FileSessionStore
from omk.labs.launcher.lab import skin_fixture
from tests.fixtures.fakes import FakeDrasl


@pytest.fixture
def window(qtbot, tmp_path):
    service = AccountService(FakeDrasl(), FileSessionStore(tmp_path / "session.json"))
    window = LauncherWindow(service, auto_restore=False)
    qtbot.addWidget(window)
    window.show()
    window._authenticated(service.login("test_player", "test-password"))
    window.skin_preview.set_skin(skin_fixture(), "classic")
    return window
