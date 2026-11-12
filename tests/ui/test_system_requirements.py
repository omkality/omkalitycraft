from dataclasses import replace

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QPushButton

from launcher.memory import MemorySnapshot
from launcher.requirements_dialog import RequirementsDialog
from launcher.theme import STYLE, install_font
from launcher.widgets import PackCard
from omk.profiles import load_profiles


@pytest.fixture
def card(qtbot, qapp):
    install_font(qapp)
    card = PackCard(load_profiles()[0], MemorySnapshot(16384, 12000))
    card.setStyleSheet(STYLE)
    card.resize(620, 440)
    qtbot.addWidget(card)
    card.show()
    return card


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
    assert "Минимум ещё проверяем" in dialog.findChild(QLabel, "minimumPending").text()
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


def test_small_dialog_scrolls_and_plain_text_cannot_create_links(qtbot, card):
    requirements = replace(
        card.profile.requirements, macos="<a href='https://example.invalid'>Mac</a>"
    )
    dialog = RequirementsDialog(replace(card.profile, requirements=requirements), card)
    qtbot.addWidget(dialog)
    dialog.resize(560, 420)
    dialog.show()
    mac = dialog.findChild(QLabel, "requirementsMac")
    assert mac.textFormat() == Qt.TextFormat.PlainText
    dialog.scroll.ensureWidgetVisible(mac)
    qtbot.waitUntil(lambda: dialog.scroll.verticalScrollBar().maximum() > 0)
    viewport = dialog.scroll.viewport()
    assert viewport.rect().contains(mac.mapTo(viewport, mac.rect().center()))
    assert dialog.scroll.horizontalScrollBar().maximum() == 0


def test_pending_pack_and_missing_requirements_do_not_advertise_readiness(qtbot, card):
    gtnh = PackCard(load_profiles()[1], MemorySnapshot(16384, 12000))
    qtbot.addWidget(gtnh)
    gtnh.show()
    qtbot.mouseClick(gtnh.requirements_button, Qt.MouseButton.LeftButton)
    assert not gtnh.action.isEnabled() and not gtnh.memory.slider.isEnabled()
    assert (
        gtnh._requirements_dialog.findChild(QLabel, "requirementsState").text()
        == "СБОРКА ГОТОВИТСЯ"
    )
    assert gtnh._requirements_dialog.findChild(QLabel, "recommended_ram") is None
    dialog = RequirementsDialog(replace(card.profile, requirements=None), card)
    qtbot.addWidget(dialog)
    assert "Требования для этой сборки пока не подготовлены." in [
        label.text() for label in dialog.findChildren(QLabel)
    ]
