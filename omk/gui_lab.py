"""Exercise real Qt widgets against disposable Drasl accounts, never real players."""

import secrets
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import patch

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication,
    QDialogButtonBox,
    QFileDialog,
    QPushButton,
    QTabWidget,
)

from launcher.accounts import AccountService, Registration
from launcher.app import LauncherWindow, PasswordDialog
from launcher.skin_defaults import SKIN_ASSETS, default_skin_bytes
from launcher.skin_dialog import SkinDialog
from launcher.storage import FileSessionStore
from omk.drasl import DraslClient
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
    registration = window.service.prepare_registration(
        "omk_gui_test", invite, secrets.token_urlsafe(24)
    )
    window.signup_password.setText(registration.password)
    window.signup_repeat.setText(registration.password)
    _click(window, "registerButton")
    _wait(app, lambda: not window.busy)
    _assert_home(window)
    return registration


def _skin_controls(app, window, client, folder, passed):
    session = window.service.store.load()
    result = client.skin_profile(session.player_uuid)
    if (
        result is None
        or result[1] != "slim"
        or QImage.fromData(result[0], "PNG")
        != QImage.fromData(default_skin_bytes(), "PNG")
    ):
        raise RuntimeError("Drasl did not serve the project default skin")
    passed("real_drasl_project_default_skin_and_slim_metadata")
    for filename, model in [
        ("default-slim.png", "slim"),
        ("default-classic.png", "classic"),
        ("default-legacy.png", "classic"),
    ]:
        png = Path(folder) / "skin.png"
        png.write_bytes((SKIN_ASSETS / filename).read_bytes())

        def confirm(model=model):
            dialog = app.activeModalWidget()
            if not isinstance(dialog, SkinDialog) or dialog.model != model:
                raise RuntimeError("Automatic skin preview selected wrong model")
            QTest.mouseClick(dialog.upload, Qt.MouseButton.LeftButton)

        with patch.object(
            QFileDialog, "getOpenFileName", return_value=(str(png), "PNG")
        ):
            QTimer.singleShot(0, confirm)
            _click(window, "uploadSkin")
            _wait(app, lambda: not window.busy)
        result = client.skin_profile(session.player_uuid)
        if (
            "Скин загружен" not in window.status.text()
            or result is None
            or result[1] != model
            or QImage.fromData(result[0], "PNG")
            != QImage.fromData(png.read_bytes(), "PNG")
        ):
            raise RuntimeError("Uploaded skin pixels/model did not round trip")
        passed("real_gui_one_upload_" + filename.removesuffix(".png"))


def _lost_registration_response(app, client, admin, folder, windows, passed):
    invite = client.request("POST", "/drasl/api/v3/invites", {}, admin["apiToken"])[
        "code"
    ]
    store = FileSessionStore(Path(folder) / "lost-registration/session.json")
    window = LauncherWindow(AccountService(client, store), auto_restore=False)
    windows.append(window)
    window.show()
    window.auth_page.findChild(QTabWidget).setCurrentIndex(1)
    password = secrets.token_urlsafe(24)
    window.signup_name.setText("omk_lost_signup")
    window.signup_password.setText(password)
    window.signup_repeat.setText(password)
    window.invitation.setText(invite)
    original = client.register

    def committed_but_reply_lost(*args, **kwargs):
        original(*args, **kwargs)
        raise TimeoutError("Owned fixture drops the reply after Drasl commits")

    with patch.object(client, "register", side_effect=committed_but_reply_lost):
        _click(window, "registerButton")
        _wait(app, lambda: not window.busy)
    if (
        window.pages.currentWidget() != window.auth_page
        or store.path.exists()
        or window.signup_password.text() != password
        or not window.retry_login.isVisible()
    ):
        raise RuntimeError("Registration reply-loss state was not preserved")
    passed("real_committed_registration_reply_loss_keeps_typed_password")
    _click(window, "retryRegistrationLogin")
    _wait(app, lambda: not window.busy)
    _assert_home(window)
    if (
        password in store.path.read_text()
        or window.signup_password.text()
        or window.signup_repeat.text()
    ):
        raise RuntimeError("Recovered registration password was persisted")
    passed("real_registration_recovery_uses_login_without_second_account")
    window.service.revoke_all(password)
    window.close()


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
                or window.signup_password.text()
                or window.signup_repeat.text()
            ):
                raise RuntimeError(
                    "Registration password remains in launcher storage or widgets"
                )
            passed("real_gui_registration_with_chosen_confirmed_password")
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

            _skin_controls(app, window, client, folder, passed)

            password = _password_controls(app, window, registration.password)
            passed("real_gui_password_change")
            window.service.revoke_all(password)
            if store.load() is not None:
                raise RuntimeError("Disposable session was not revoked")
            passed("real_backend_cleanup_sessions_revoked")
            _lost_registration_response(app, client, admin, folder, windows, passed)
        finally:
            for window in windows:
                _wait(app, lambda window=window: not window.busy)
                window.close()
                window.deleteLater()
            app.processEvents()
