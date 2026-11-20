"""Test dependencies for nickname feedback."""

import pytest

from launcher.accounts import AccountService
from launcher.app import LauncherWindow
from launcher.storage import FileSessionStore
from tests.fixtures.fakes import FakeDrasl


@pytest.fixture
def window(qtbot, tmp_path):
    service = AccountService(FakeDrasl(), FileSessionStore(tmp_path / "session.json"))
    window = LauncherWindow(service, auto_restore=False)
    qtbot.addWidget(window)
    window.show()
    return window
