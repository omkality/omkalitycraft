"""Exercise real Qt widgets against disposable Drasl accounts, never real players."""

import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import patch

from PySide6.QtCore import Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication,
    QDialogButtonBox,
    QFileDialog,
    QInputDialog,
    QPushButton,
    QTabWidget,
)

from launcher.accounts import AccountService, Registration
from launcher.app import LauncherWindow, PasswordDialog
from launcher.storage import FileSessionStore
from omk.drasl import DraslClient
from omk.lab import skin_fixture
from omk.profiles import PROJECT_ROOT


def _wait(app: QApplication, predicate: Callable[[], bool]) -> None:
    deadline = time.monotonic() + 12
    while not predicate():
        if time.monotonic() >= deadline:
            raise RuntimeError("Timed out waiting for the disposable launcher UI")
        app.processEvents()
        time.sleep(0.01)
    app.processEvents()


def _click(window: LauncherWindow, name: str) -> None:
    widget = window.findChild(QPushButton, name)
    if widget is None or not widget.isEnabled():
        raise RuntimeError("Launcher test button is unavailable")
    QTest.mouseClick(widget, Qt.MouseButton.LeftButton)


def _assert_home(window: LauncherWindow) -> None:
    if window.pages.currentWidget() != window.home_page:
        raise RuntimeError("Launcher did not complete the disposable account workflow")


def _password_controls(app: QApplication, window: LauncherWindow, password: str) -> str:
    new_password = password + "-changed"

    def fill_password() -> None:
        dialog = app.activeModalWidget()
        if not isinstance(dialog, PasswordDialog):
            raise RuntimeError("Password test dialog is unavailable")
        dialog.old.setText(password)
        dialog.new.setText(new_password)
        dialog.repeat.setText(new_password)
        save = dialog.findChild(QDialogButtonBox).button(
            QDialogButtonBox.StandardButton.Save
        )
        QTest.mouseClick(save, Qt.MouseButton.LeftButton)

    QTimer.singleShot(0, fill_password)
    _click(window, "changePassword")
    _wait(app, lambda: not window.busy)
    _assert_home(window)
    return new_password


def _revoke_control(app: QApplication, window: LauncherWindow, password: str) -> None:
    def confirm_password() -> None:
        dialog = app.activeModalWidget()
        if not isinstance(dialog, QInputDialog):
            raise RuntimeError("Revocation test dialog is unavailable")
        dialog.setTextValue(password)
        dialog.accept()

    QTimer.singleShot(0, confirm_password)
    _click(window, "revokeAll")
    _wait(app, lambda: not window.busy)
    if (
        window.pages.currentWidget() != window.auth_page
        or window.service.store.load() is not None
    ):
        raise RuntimeError("Launcher did not complete remote session revocation")


def _registration_control(
    app: QApplication,
    window: LauncherWindow,
    client: DraslClient,
    admin: dict[str, Any],
) -> Registration:
    invite = client.request("POST", "/drasl/api/v3/invites", {}, admin["apiToken"])[
        "code"
    ]
    window.auth_page.findChild(QTabWidget).setCurrentIndex(1)
    window.signup_name.setText("omk_gui_test")
    window.invitation.setText(invite)
    _click(window, "prepareRegistration")
    registration = window.pending
    if registration is None or window.register_button.isEnabled():
        raise RuntimeError("Password acknowledgement is missing")
    QTest.mouseClick(window.saved_password, Qt.MouseButton.LeftButton)
    _click(window, "registerButton")
    _wait(app, lambda: not window.busy)
    _assert_home(window)
    return registration


def launcher_checks(
    client: DraslClient, admin: dict[str, Any], passed: Callable[[str], None]
) -> None:
    # This tool operates only on accounts and files created inside the auth lab.
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    local = PROJECT_ROOT / ".local"
    local.mkdir(exist_ok=True)
    windows: list[LauncherWindow] = []
    with tempfile.TemporaryDirectory(prefix="gui-auth-", dir=local) as folder:
        store = FileSessionStore(Path(folder) / "session.json")
        try:
            window = LauncherWindow(AccountService(client, store), auto_restore=False)
            windows.append(window)
            window.show()
            app.processEvents()
            registration = _registration_control(app, window, client, admin)
            if (
                registration.password in store.path.read_text()
                or window.issued_password.text()
            ):
                raise RuntimeError(
                    "Issued password remains in launcher storage or widgets"
                )
            passed("real_gui_registration_after_password_acknowledgement")
            window.close()

            window = LauncherWindow(AccountService(client, store))
            windows.append(window)
            window.show()
            _wait(
                app,
                lambda: window.pages.currentWidget() == window.home_page
                and not window.busy,
            )
            passed("real_gui_restart_auto_login")

            png = Path(folder) / "skin.png"
            png.write_bytes(skin_fixture())
            with patch.object(
                QFileDialog, "getOpenFileName", return_value=(str(png), "PNG")
            ):
                _click(window, "uploadSkin")
                _wait(app, lambda: not window.busy)
            if "Скин загружен" not in window.status.text():
                raise RuntimeError("Launcher skin upload did not complete")
            passed("real_gui_skin_upload")

            password = _password_controls(app, window, registration.password)
            passed("real_gui_password_change")
            _revoke_control(app, window, password)
            passed("real_gui_all_sessions_revoked")
        finally:
            for window in windows:
                _wait(app, lambda window=window: not window.busy)
                window.close()
                window.deleteLater()
            app.processEvents()
