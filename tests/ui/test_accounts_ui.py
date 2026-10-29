from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog, QPushButton, QTabWidget
from pytestqt.qtbot import QtBot

from launcher.accounts import AccountService
from launcher.app import LauncherWindow, instance_lock
from launcher.storage import FileSessionStore
from omk.lab import skin_fixture
from tests.fakes import FakeDrasl


@pytest.fixture
def window(qtbot: QtBot, tmp_path: Path) -> LauncherWindow:
    service = AccountService(
        FakeDrasl(), FileSessionStore(tmp_path / "userdata" / "session.json")
    )
    widget = LauncherWindow(service, auto_restore=False)
    qtbot.addWidget(widget)
    widget.show()
    return widget


def click(qtbot: QtBot, window: LauncherWindow, name: str) -> None:
    qtbot.mouseClick(window.findChild(QPushButton, name), Qt.MouseButton.LeftButton)


def wait_idle(qtbot: QtBot, window: LauncherWindow) -> None:
    qtbot.waitUntil(lambda: not window.busy, timeout=4000)


def test_registration_requires_saved_password_before_server_request(
    qtbot: QtBot, window: LauncherWindow
) -> None:
    window.signup_name.setText("test_player")
    window.invitation.setText("test-invitation")
    window.auth_page.findChild(QTabWidget).setCurrentIndex(1)
    click(qtbot, window, "prepareRegistration")
    assert window.pages.currentWidget() == window.password_page
    issued = window.issued_password.text()
    assert len(issued) >= 32
    assert not window.register_button.isEnabled()
    assert window.service.client.calls == []
    qtbot.keyClick(window.saved_password, Qt.Key.Key_Space)
    click(qtbot, window, "registerButton")
    wait_idle(qtbot, window)
    assert window.pages.currentWidget() == window.home_page
    assert issued not in window.service.store.path.read_text(encoding="utf-8")
    assert window.issued_password.text() == ""
    assert window.pending is None


def test_login_and_new_window_auto_login(qtbot: QtBot, window: LauncherWindow) -> None:
    window.login_name.setText("test_player")
    window.login_password.setText("test-password")
    click(qtbot, window, "loginButton")
    wait_idle(qtbot, window)
    assert window.login_password.text() == ""
    assert window.pages.currentWidget() == window.home_page
    service = AccountService(window.service.client, window.service.store)
    restored = LauncherWindow(service)
    qtbot.addWidget(restored)
    restored.show()
    qtbot.waitUntil(
        lambda: restored.pages.currentWidget() == restored.home_page, timeout=4000
    )


def test_network_error_keeps_issued_password_for_retry(
    qtbot: QtBot, window: LauncherWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    window.signup_name.setText("test_player")
    window.invitation.setText("test-invitation")
    window._prepare_registration()
    issued = window.issued_password.text()

    def lost_response(*args: object, **kwargs: object) -> None:
        raise TimeoutError("sensitive server details must not appear")

    monkeypatch.setattr(window.service.client, "register", lost_response)
    qtbot.keyClick(window.saved_password, Qt.Key.Key_Space)
    click(qtbot, window, "registerButton")
    wait_idle(qtbot, window)
    assert window.pages.currentWidget() == window.password_page
    assert window.issued_password.text() == issued
    assert window.retry_login.isVisible()
    assert "sensitive server details" not in window.status.text()
    click(qtbot, window, "retryIssuedLogin")
    wait_idle(qtbot, window)
    assert window.pages.currentWidget() == window.home_page


def test_skin_file_upload_uses_selected_model(
    qtbot: QtBot,
    window: LauncherWindow,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window._authenticated(window.service.login("test_player", "test-password"))
    png = tmp_path / "skin.png"
    png.write_bytes(skin_fixture())
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args: (str(png), "PNG"))
    window.skin_model.setCurrentIndex(1)
    click(qtbot, window, "uploadSkin")
    wait_idle(qtbot, window)
    assert ("upload_skin", "slim") in window.service.client.calls
    assert "Скин загружен" in window.status.text()


def test_forget_button_removes_only_test_session(
    qtbot: QtBot, window: LauncherWindow
) -> None:
    window._authenticated(window.service.login("test_player", "test-password"))
    window.service.client.calls.clear()
    click(qtbot, window, "forgetDevice")
    assert window.pages.currentWidget() == window.auth_page
    assert not window.service.store.path.exists()
    assert window.service.client.calls == []


def test_second_instance_cannot_use_same_token_file(
    tmp_path: Path, qtbot: QtBot
) -> None:
    first = instance_lock(tmp_path)
    assert first is not None
    try:
        assert instance_lock(tmp_path) is None
    finally:
        first.unlock()
    second = instance_lock(tmp_path)
    assert second is not None
    second.unlock()
