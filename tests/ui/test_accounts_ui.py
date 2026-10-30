import threading
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog, QLabel, QPushButton, QTabWidget
from pytestqt.qtbot import QtBot

from launcher.__main__ import _bootstrap_lock
from launcher.accounts import AccountService
from launcher.app import LauncherWindow, instance_lock
from launcher.dashboard import Dashboard
from launcher.game import GameRunner
from launcher.install import Progress
from launcher.memory import MemorySnapshot, Preferences
from launcher.skin_view import default_skin
from launcher.storage import FileSessionStore
from omk.lab import skin_fixture
from tests.fakes import FakeDrasl


def test_player_launcher_has_no_diagnostic_or_administration_menu(qtbot, tmp_path):
    service = AccountService(
        FakeDrasl(), FileSessionStore(tmp_path / "userdata/session.json")
    )
    window = LauncherWindow(service, runner=GameRunner(tmp_path), auto_restore=False)
    qtbot.addWidget(window)
    assert window.menuBar().actions() == []
    assert not service.store.path.exists()
    assert service.client.calls == []


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


def test_home_has_no_session_management_clutter(
    qtbot: QtBot, window: LauncherWindow
) -> None:
    window._authenticated(window.service.login("test_player", "test-password"))
    assert window.findChild(QPushButton, "forgetDevice") is None
    assert window.findChild(QPushButton, "revokeAll") is None
    assert window.status.text() == ""
    assert window.font().family() == "Rubik Medium"


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


def test_repeated_login_clicks_do_not_duplicate_requests(
    qtbot: QtBot, window: LauncherWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    entered, release = threading.Event(), threading.Event()
    login = window.service.login
    calls = []

    def slow_login(name, password):
        calls.append(name)
        entered.set()
        release.wait(timeout=3)
        return login(name, password)

    monkeypatch.setattr(window.service, "login", slow_login)
    window.login_name.setText("test_player")
    window.login_password.setText("test-password")
    try:
        click(qtbot, window, "loginButton")
        qtbot.waitUntil(entered.is_set)
        assert window.findChild(QPushButton, "loginButton")._busy
        for _ in range(20):
            window._login()
        assert calls == ["test_player"]
    finally:
        release.set()
        wait_idle(qtbot, window)


def test_pack_download_progress_and_planned_profile(
    qtbot: QtBot, window: LauncherWindow
) -> None:
    cards = window.home_page.cards
    assert not cards["gtnh"].action.isEnabled()
    cards["dj2"].update_progress(Progress("Скачиваем сборку", 50, 100))
    assert cards["dj2"].progress.value() == 50
    assert cards["dj2"].action._busy
    assert "50%" in cards["dj2"].state_label.text()
    cards["dj2"].finished(success=True)
    assert cards["dj2"].action.text() == "Играть"


def test_missing_or_malformed_texture_does_not_block_login(
    qtbot: QtBot, window: LauncherWindow, monkeypatch: pytest.MonkeyPatch
):
    def malformed(_player_id):
        raise TypeError("invalid public texture payload")

    monkeypatch.setattr(window.service.client, "skin_profile", malformed)
    window.login_name.setText("test_player")
    window.login_password.setText("test-password")
    click(qtbot, window, "loginButton")
    wait_idle(qtbot, window)
    assert window.pages.currentWidget() == window.home_page
    assert window.status.text() == ""


def test_bootstrap_lock_protects_gap_during_handoff(tmp_path: Path, qtbot: QtBot):
    bootstrap = _bootstrap_lock(tmp_path, False)
    session = instance_lock(tmp_path / "userdata")
    session.unlock()
    try:
        with pytest.raises(OSError):
            _bootstrap_lock(tmp_path, False)
        assert _bootstrap_lock(tmp_path, True) is None
        child = instance_lock(tmp_path / "userdata")
        assert child is not None
        child.unlock()
    finally:
        bootstrap.unlock()


def test_heap_slider_saves_profiles_independently(qtbot: QtBot, tmp_path: Path):
    preferences = Preferences(tmp_path / "preferences.json")
    panel = Dashboard(preferences, MemorySnapshot(16384, 12000))
    qtbot.addWidget(panel)
    panel.cards["dj2"].memory.slider.setValue(20)
    panel.cards["gtnh"].memory.slider.setValue(28)
    assert Preferences(preferences.path).memory == {"dj2": 5120, "gtnh": 7168}
    assert panel.cards["dj2"].memory.selected_mb == 5120


def test_weak_machine_caps_slider_and_shows_warning(qtbot: QtBot):
    panel = Dashboard(machine=MemorySnapshot(4096, 3000))
    qtbot.addWidget(panel)
    memory = panel.cards["dj2"].memory
    assert memory.selected_mb == 2048
    assert memory.slider.maximum() == 8
    assert "не запуститься" in memory.warning.text()


def test_default_skin_has_hair_on_both_sides_and_top(qtbot: QtBot):
    image = default_skin()
    for x, y in [(3, 9), (19, 9), (11, 3), (27, 9)]:
        assert image.pixelColor(x, y).name() == "#3b3531"


def test_social_footer_and_clear_planned_version(window: LauncherWindow):
    assert "ещё не подготовлена" in window.home_page.cards["gtnh"].version_link.text()
    assert "https://kick.com/omkality" in window.findChild(QLabel, "social_kick").text()
    assert "обычные руки" not in window.skin_model.itemText(0)
