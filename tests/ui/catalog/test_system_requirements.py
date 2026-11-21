from dataclasses import replace

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QPushButton

from launcher.memory import MemorySnapshot
from launcher.ui.requirements_dialog import RequirementsDialog
from launcher.widgets import PackCard
from tests.fixtures.ui.catalog.system_requirements import card

__all__ = ["card"]


def test_open_repeatedly_and_close_by_keyboard_without_touching_installation(
    qtbot, card
):
    calls = []
    card.action.clicked.connect(lambda: calls.append("install"))
    selected = card.memory.selected_mb
    qtbot.mouseClick(card.requirements_button, Qt.MouseButton.LeftButton)
    dialog = card._requirements_dialog
    assert dialog.isVisible() and dialog.parentWidget() is card
    assert dialog.findChild(QLabel, "recommended_ram").text() == "16 ГБ"
    assert "6 ГБ" in dialog.findChild(QLabel, "requirementsJavaMemory").text()
    assert dialog.findChild(QLabel, "minimum_ram").text() == "8 ГБ"
    card._show_requirements()
    assert card._requirements_dialog is dialog
    qtbot.keyClick(dialog, Qt.Key.Key_Escape)
    assert not dialog.isVisible()
    qtbot.mouseClick(card.requirements_button, Qt.MouseButton.LeftButton)
    assert card._requirements_dialog is dialog and dialog.isVisible()
    qtbot.mouseClick(
        dialog.findChild(QPushButton, "closeRequirements"),
        Qt.MouseButton.LeftButton,
    )
    assert not dialog.isVisible()
    assert calls == [] and card.memory.selected_mb == selected


def test_requirements_fit_without_scroll_and_keep_platforms_plain(qtbot, card):
    requirements = replace(
        card.profile.requirements,
        platforms="<a href='https://example.invalid'>Windows</a>",
    )
    dialog = RequirementsDialog(replace(card.profile, requirements=requirements), card)
    qtbot.addWidget(dialog)
    dialog.show()
    text = dialog.findChild(QLabel, "requirementsOS")
    assert text.textFormat() == Qt.TextFormat.PlainText
    assert dialog.height() <= dialog.screen().availableGeometry().height()
    assert dialog.windowType() == Qt.WindowType.Popup
    assert dialog.findChild(QLabel, "minimum_storage").text() == "10 ГБ"


def test_pending_pack_and_missing_requirements_do_not_advertise_readiness(
    qtbot, card, planned_profile
):
    planned = PackCard(planned_profile, MemorySnapshot(16384, 12000))
    qtbot.addWidget(planned)
    planned.show()
    qtbot.mouseClick(planned.requirements_button, Qt.MouseButton.LeftButton)
    assert not planned.action.isEnabled() and not planned.memory.slider.isEnabled()
    assert (
        planned._requirements_dialog.findChild(QLabel, "requirementsState").text()
        == "СБОРКА ГОТОВИТСЯ"
    )
    assert planned._requirements_dialog.findChild(QLabel, "recommended_ram") is None
    dialog = RequirementsDialog(replace(card.profile, requirements=None), card)
    qtbot.addWidget(dialog)
    assert "Требования для этой сборки пока не подготовлены." in [
        label.text() for label in dialog.findChildren(QLabel)
    ]
