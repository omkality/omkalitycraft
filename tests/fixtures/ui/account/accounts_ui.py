"""Test dependencies for accounts ui."""

from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot

from launcher.accounts import AccountService
from launcher.app import LauncherWindow
from launcher.storage import FileSessionStore
from tests.fixtures.fakes import FakeDrasl


@pytest.fixture
def window(qtbot: QtBot, tmp_path: Path) -> LauncherWindow:
    service = AccountService(
        FakeDrasl(), FileSessionStore(tmp_path / "userdata" / "session.json")
    )
    widget = LauncherWindow(service, auto_restore=False)
    qtbot.addWidget(widget)
    widget.show()
    return widget
