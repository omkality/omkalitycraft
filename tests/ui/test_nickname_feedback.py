import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QInputMethodEvent, QWheelEvent
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication, QTabWidget, QToolTip

from launcher.accounts import AccountService
from launcher.app import LauncherWindow
from launcher.dashboard import Dashboard
from launcher.memory import MemorySnapshot, Preferences
from launcher.storage import FileSessionStore
from tests.fakes import FakeDrasl


@pytest.fixture
def window(qtbot, tmp_path):
    service = AccountService(FakeDrasl(), FileSessionStore(tmp_path / "session.json"))
    window = LauncherWindow(service, auto_restore=False)
    qtbot.addWidget(window)
    window.show()
    return window


def test_planned_profile_ignores_mouse_keyboard_and_wheel_without_saving(
    qtbot, tmp_path
):
    preferences = Preferences(tmp_path / "preferences.json")
    panel = Dashboard(preferences=preferences, machine=MemorySnapshot(32768, 24000))
    qtbot.addWidget(panel)
    panel.show()
    slider = panel.cards["gtnh"].memory.slider
    changed = QSignalSpy(panel.cards["gtnh"].memory.changed)
    before = slider.value()
    assert not slider.isEnabled() and not panel.cards["gtnh"].memory.value.isEnabled()
    qtbot.mouseClick(slider, Qt.MouseButton.LeftButton, pos=slider.rect().topRight())
    qtbot.keyClick(slider, Qt.Key.Key_End)
    event = QWheelEvent(
        QPointF(5, 5),
        QPointF(slider.mapToGlobal(QPoint(5, 5))),
        QPoint(),
        QPoint(0, 120),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    QApplication.sendEvent(slider, event)
    assert slider.value() == before and changed.count() == 0
    assert not preferences.path.exists()
    working = panel.cards["dj2"].memory.slider
    assert working.isEnabled()
    qtbot.keyClick(working, Qt.Key.Key_Right)
    assert working.value() != before


@pytest.mark.parametrize("field", ["signup_name", "login_name"])
def test_rejected_character_is_not_inserted_and_notice_does_not_steal_focus(
    qtbot, window, field
):
    edit = getattr(window, field)
    window.pages.setCurrentWidget(window.auth_page)
    window.auth_page.findChild(QTabWidget).setCurrentIndex(
        1 if field == "signup_name" else 0
    )
    edit.setFocus()
    qtbot.keyClicks(edit, "Alex")
    qtbot.keyClicks(edit, "!")
    assert edit.text() == "Alex" and edit.hasFocus()
    assert "латинские" in edit.notice.text() and edit.notice.isVisible()
    assert edit.notice_timer.isActive()
    qtbot.keyClicks(edit, "_01")
    assert edit.text() == "Alex_01"
    qtbot.waitUntil(lambda: not edit.notice_timer.isActive(), timeout=3000)
    assert not edit.notice.isVisible()


@pytest.mark.parametrize("value", ["bad name", "bad-name", "Игрок", "a\u200bb", "a😀b"])
def test_invalid_clipboard_paste_is_rejected_without_silently_changing_name(
    qtbot, window, value
):
    edit = window.login_name
    edit.setText("Alex")
    edit.selectAll()
    QApplication.clipboard().setText(value)
    edit.paste()
    assert edit.text() == "Alex" and edit.notice_timer.isActive()
    assert window.service.client.calls == []


def test_ime_and_length_limit_have_feedback_but_editing_deleting_and_undo_work(
    qtbot, window
):
    edit = window.login_name
    edit.setFocus()
    event = QInputMethodEvent()
    event.setCommitString("Игрок")
    QApplication.sendEvent(edit, event)
    assert edit.text() == "" and edit.notice_timer.isActive()
    qtbot.keyClicks(edit, "Abc_0123456789012")
    assert len(edit.text()) == 16 and edit.hasAcceptableInput()
    qtbot.keyClicks(edit, "3")
    assert len(edit.text()) == 16 and "16" in edit.notice.text()
    qtbot.keyClick(edit, Qt.Key.Key_Backspace)
    assert len(edit.text()) == 15
    edit.undo()
    assert len(edit.text()) == 16
    edit.selectAll()
    QApplication.clipboard().setText("New_name")
    edit.paste()
    assert edit.text() == "New_name"


def test_overlong_clipboard_input_reports_length_and_never_exceeds_limit(window):
    edit = window.login_name
    QApplication.clipboard().setText("Abc_01234567890123")
    edit.paste()
    assert len(edit.text()) == 16
    assert edit.notice_timer.isActive() and "16" in edit.notice.text()


def test_leaving_nickname_hides_validation_notice(qtbot, window):
    edit = window.login_name
    edit.setFocus()
    qtbot.keyClicks(edit, "!")
    assert edit.notice.isVisible()
    window.login_password.setFocus()
    QApplication.processEvents()
    assert not edit.notice_timer.isActive()
    assert not edit.notice.isVisible()
    assert window.login_password.hasFocus()


@pytest.mark.parametrize("notice", [False, True])
def test_tooltip_background_has_transparent_corners(qtbot, window, notice):
    edit = window.login_name
    edit.setFocus()
    if notice:
        qtbot.keyClicks(edit, "!")
    else:
        QToolTip.showText(
            edit.mapToGlobal(QPoint(0, edit.height())), edit.toolTip(), edit
        )
    qtbot.waitUntil(edit.notice.isVisible if notice else QToolTip.isVisible)
    assert (edit.notice.text() if notice else QToolTip.text()) == (
        edit.notice_text if notice else edit.toolTip()
    )
    tip = (
        edit.notice
        if notice
        else next(
            widget
            for widget in QApplication.topLevelWidgets()
            if widget.windowType() == Qt.WindowType.ToolTip and widget.isVisible()
        )
    )
    image = tip.grab().toImage()
    for point in (
        image.rect().topLeft(),
        image.rect().topRight(),
        image.rect().bottomLeft(),
        image.rect().bottomRight(),
    ):
        assert image.pixelColor(point).alpha() == 0
    assert image.pixelColor(image.rect().center()).alpha() > 0
