import threading

import pytest
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QLabel, QTabWidget

from launcher.accounts import AccountError, AccountService
from launcher.app import LauncherWindow
from launcher.game import GameRunner
from launcher.storage import FileSessionStore
from tests.fakes import FakeDrasl


@pytest.fixture
def window(qtbot, tmp_path):
    service = AccountService(FakeDrasl(), FileSessionStore(tmp_path / "session.json"))
    window = LauncherWindow(service, runner=GameRunner(tmp_path), auto_restore=False)
    qtbot.addWidget(window)
    window.show()
    return window


def test_labels_center_on_inputs_and_nickname_uses_bundled_pixel_font(qtbot, window):
    window.auth_page.findChild(QTabWidget).setCurrentIndex(1)
    qtbot.waitUntil(
        lambda: all(
            abs(
                edit.parentWidget().layout().labelForField(edit).geometry().center().y()
                - edit.geometry().center().y()
            )
            <= 1
            for edit in (window.signup_name, window.invitation)
        )
    )
    for edit in (window.signup_name, window.invitation):
        caption = edit.parentWidget().layout().labelForField(edit)
        assert abs(caption.geometry().center().y() - edit.geometry().center().y()) <= 1
    assert window.invitation.font().family() == "Rubik"
    assert window.invitation.font().weight() == QFont.Weight.Bold
    assert window.signup_name.font().family() == "Monocraft"
    window._authenticated(window.service.login("test_player", "test-password"))
    window.resize(1020, 680)
    qtbot.waitUntil(lambda: window.home_page.cards["dj2"].width() > 100)
    for pack_id, card in window.home_page.cards.items():
        description = card.findChild(QLabel, "description_" + pack_id)
        assert (
            description.fontMetrics().horizontalAdvance(description.text())
            <= description.width()
        )


def test_nickname_typing_accepts_legacy_java_alphabet_and_limits_length(window):
    name = window.signup_name
    for invalid in ("Игрок", "bad name", "ab.c", "user-01"):
        name.clear()
        name.insert(invalid)
        assert name.text() == ""
    name.insert("Abc_0123456789012")
    assert name.hasAcceptableInput() and len(name.text()) == 16
    name.clear()
    name.insert("ab")
    assert not name.hasAcceptableInput()
    with pytest.raises(AccountError):
        window.service.prepare_registration(name.text(), "lab-invitation")


def test_online_poll_is_coalesced_and_unavailable_does_not_show_zero(qtbot, window):
    window._authenticated(window.service.login("test_player", "test-password"))
    release = threading.Event()
    calls = []

    def fetch():
        calls.append(True)
        release.wait(2)
        return {"servers": {"dj2": {"state": "online", "online": 1, "max": 20}}}

    window.server_status.fetcher = fetch
    window.server_status.refresh()
    window.server_status.refresh()
    release.set()
    qtbot.waitUntil(lambda: not window.server_status.busy)
    card = window.home_page.cards["dj2"]
    assert len(calls) == 1 and card.online_label.text() == "Онлайн: 1 / 20"
    window._server_status_updated({"dj2": {"state": "offline"}})
    assert card.online_label.text() == "Сервер недоступен"
    window._server_status_updated(None)
    assert card.online_label.text() == "Онлайн недоступен"
