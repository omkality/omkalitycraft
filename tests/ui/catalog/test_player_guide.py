from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QPushButton

from launcher.dashboard import Dashboard
from launcher.memory import MemorySnapshot
from launcher.ui.player_guide import PlayerGuideDialog


def test_player_guide_opens_from_dashboard_and_keeps_pack_controls(qtbot):
    window = Dashboard(machine=MemorySnapshot(16384, 12000))
    qtbot.addWidget(window)
    window.resize(1100, 675)
    window.show()
    card = window.cards["dj2"]
    memory = card.memory.selected_mb

    qtbot.mouseClick(window.guide_button, Qt.MouseButton.LeftButton)
    dialog = window.findChild(PlayerGuideDialog, "playerGuide")
    assert dialog.isVisible()
    assert dialog.tabs.count() == 5

    for title in ("Приваты", "Квесты и команды", "Миры и /rtp", "Правила"):
        tab = next(
            index
            for index in range(dialog.tabs.count())
            if dialog.tabs.tabText(index) == title
        )
        qtbot.mouseClick(
            dialog.tabs.tabBar(),
            Qt.MouseButton.LeftButton,
            pos=dialog.tabs.tabBar().tabRect(tab).center(),
        )
        assert dialog.tabs.currentIndex() == tab
        labels = dialog.tabs.widget(tab).findChildren(QLabel)
        assert any(label.isVisible() and label.text() for label in labels)

    qtbot.keyClick(dialog, Qt.Key.Key_Escape)
    assert not dialog.isVisible()
    assert card.memory.selected_mb == memory
    qtbot.mouseClick(window.guide_button, Qt.MouseButton.LeftButton)
    assert window.findChildren(PlayerGuideDialog) == [dialog] and dialog.isVisible()
    qtbot.mouseClick(
        dialog.findChild(QPushButton, "closePlayerGuide"), Qt.MouseButton.LeftButton
    )
    assert not dialog.isVisible()
