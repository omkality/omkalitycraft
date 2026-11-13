import threading

import pytest
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QLabel, QPushButton

from launcher.accounts import AccountService
from launcher.app import LauncherWindow, PasswordDialog
from launcher.skin_view import default_skin
from launcher.storage import FileSessionStore
from omk.drasl import DraslError
from omk.lab import skin_fixture
from tests.fakes import FakeDrasl


@pytest.fixture
def window(qtbot, tmp_path):
    service = AccountService(FakeDrasl(), FileSessionStore(tmp_path / "session.json"))
    window = LauncherWindow(service, auto_restore=False)
    qtbot.addWidget(window)
    window.show()
    window._authenticated(service.login("test_player", "test-password"))
    window.skin_preview.set_skin(skin_fixture(), "classic")
    return window


def test_password_labels_center_on_fields_and_buttons_fill_the_row(qtbot, window):
    dialog = PasswordDialog(window)
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitUntil(lambda: dialog.width() >= 700)
    for edit in (dialog.old, dialog.new, dialog.repeat):
        caption = edit.parentWidget().layout().itemAt(1).layout().labelForField(edit)
        assert abs(caption.geometry().center().y() - edit.geometry().center().y()) <= 1
    notice = dialog.findChild(QLabel, "passwordChangeNotice")
    assert not notice.wordWrap()
    assert notice.fontMetrics().horizontalAdvance(notice.text()) <= notice.width()
    save, cancel = [
        dialog.findChild(QPushButton, name)
        for name in ("savePassword", "cancelPassword")
    ]
    assert abs(save.width() - cancel.width()) <= 1
    assert save.geometry().left() == notice.geometry().left()
    assert cancel.geometry().right() == notice.geometry().right()


def test_reset_cancel_and_escape_never_change_skin(qtbot, window):
    before = window.skin_preview.image.copy()
    for dismiss in (
        lambda dialog: dialog.reject(),
        lambda dialog: qtbot.keyClick(dialog, Qt.Key.Key_Escape),
    ):
        QTimer.singleShot(
            0, lambda dismiss=dismiss: dismiss(QApplication.activeModalWidget())
        )
        qtbot.mouseClick(window.home_page.reset_skin_button, Qt.MouseButton.LeftButton)
    assert window.skin_preview.image == before
    assert not any(call[0] == "upload_skin" for call in window.service.client.calls)


def test_password_save_still_validates_before_accepting(qtbot, window):
    dialog = PasswordDialog(window)
    qtbot.addWidget(dialog)
    dialog.show()
    dialog.old.setText("old-fixture-password")
    dialog.new.setText("new-fixture-password")
    dialog.repeat.setText("different-fixture-password")
    save = dialog.findChild(QPushButton, "savePassword")
    qtbot.mouseClick(save, Qt.MouseButton.LeftButton)
    assert dialog.isVisible() and "не совпадают" in dialog.error.text()
    dialog.repeat.setText(dialog.new.text())
    qtbot.mouseClick(save, Qt.MouseButton.LeftButton)
    assert dialog.result() == dialog.DialogCode.Accepted and not dialog.isVisible()


def test_confirmed_reset_waits_for_backend_and_coalesces_repeated_clicks(
    qtbot, window, monkeypatch
):
    entered, release = threading.Event(), threading.Event()
    calls = []
    before = window.skin_preview.image.copy()

    def held():
        calls.append(True)
        entered.set()
        release.wait(3)

    monkeypatch.setattr(window.service, "reset_skin", held)

    def confirm():
        dialog = QApplication.activeModalWidget()
        assert "Вы уверены?" in dialog.findChild(QLabel, "resetSkinQuestion").text()
        qtbot.mouseClick(
            dialog.findChild(QPushButton, "confirmSkinReset"), Qt.MouseButton.LeftButton
        )

    QTimer.singleShot(0, confirm)
    try:
        qtbot.mouseClick(window.home_page.reset_skin_button, Qt.MouseButton.LeftButton)
        qtbot.waitUntil(entered.is_set)
        assert window.home_page.reset_skin_button._busy
        assert window.skin_preview.image == before
        for _ in range(10):
            window._reset_skin()
        assert calls == [True]
    finally:
        release.set()
        qtbot.waitUntil(lambda: not window.busy)
    assert window.skin_preview.image == default_skin()
    assert window.skin_preview.model == "slim"
    assert "Скин сброшен" in window.status.text()


@pytest.mark.parametrize(
    "error", [TimeoutError("private connection detail"), DraslError(429)]
)
def test_failed_reset_keeps_custom_preview_and_allows_retry(
    qtbot, window, monkeypatch, error
):
    before = window.skin_preview.image.copy()

    def fail():
        raise error

    monkeypatch.setattr(window.service, "reset_skin", fail)
    QTimer.singleShot(0, lambda: QApplication.activeModalWidget().accept())
    qtbot.mouseClick(window.home_page.reset_skin_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: not window.busy)
    assert window.skin_preview.image == before
    assert window.home_page.reset_skin_button.isEnabled()
    assert "private connection detail" not in window.status.text()
    assert "Скин сброшен" not in window.status.text()
