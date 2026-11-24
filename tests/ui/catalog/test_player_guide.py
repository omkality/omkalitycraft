from dataclasses import replace

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QLabel, QPushButton, QTabWidget, QWidget

from launcher.dashboard import Dashboard
from launcher.memory import MemorySnapshot
from launcher.ui.player_guide import PlayerGuideDialog
from omk.shared.profiles import load_profiles


def _open_guide(qtbot, tmp_path):
    window = Dashboard(
        machine=MemorySnapshot(16384, 12000),
        instance_directory=lambda pack_id: tmp_path / pack_id,
    )
    qtbot.addWidget(window)
    window.resize(1060, 675)
    window.show()
    qtbot.mouseClick(window.guide_button, Qt.MouseButton.LeftButton)
    return window, window.findChild(PlayerGuideDialog, "playerGuide")


def _select(qtbot, dialog, name):
    qtbot.mouseClick(dialog.findChild(QPushButton, name), Qt.MouseButton.LeftButton)
    page = dialog.pages.currentWidget()
    assert page.objectName() == name + "Page"
    return page


def test_commands_live_in_the_command_section_and_rules_have_no_commands(
    qtbot, tmp_path
):
    window, dialog = _open_guide(qtbot, tmp_path)
    assert dialog.isVisible() and dialog.pages.count() == 4
    for name in ("guideRules", "guideClaims_dj2", "guideWorlds_dj2"):
        page = _select(qtbot, dialog, name)
        labels = [label.text() for label in page.findChildren(QLabel)]
        assert labels and not any(text.startswith("/") for text in labels)
        if name == "guideClaims_dj2":
            for object_name in ("claimsButtonScreenshot", "claimsMapScreenshot"):
                assert not page.findChild(QLabel, object_name).pixmap().isNull()
        if name == "guideRules":
            assert any("X-ray" in text for text in labels)
            assert any("Краш-машины" in text for text in labels)
        if name == "guideWorlds_dj2":
            assert "Вещи после смерти" in labels
            assert any(
                "своей могиле" in text and "приседания" in text for text in labels
            )

    page = _select(qtbot, dialog, "guideCommands")
    scopes = dialog.findChild(QTabWidget, "guideCommandsPage")
    assert page is scopes
    assert scopes.count() == 2
    common = [label.text() for label in scopes.widget(0).findChildren(QLabel)]
    assert {
        "/sethome",
        "/sethome base",
        "/home",
        "/home base",
        "/delhome",
        "/delhome base",
        "/rtp",
        "/tpaccept Alex",
    }.issubset(common)
    dj2 = [label.text() for label in scopes.widget(1).findChildren(QLabel)]
    assert {"/resource", "/chunks claim", "/bq_user refresh"}.issubset(dj2)
    assert all(text.isascii() for text in common + dj2 if text.startswith("/"))

    memory = window.cards["dj2"].memory.selected_mb
    qtbot.keyClick(dialog, Qt.Key.Key_Escape)
    assert not dialog.isVisible()
    assert window.cards["dj2"].memory.selected_mb == memory
    qtbot.mouseClick(window.guide_button, Qt.MouseButton.LeftButton)
    assert window.findChildren(PlayerGuideDialog) == [dialog] and dialog.isVisible()
    qtbot.mouseClick(
        dialog.findChild(QPushButton, "closePlayerGuide"), Qt.MouseButton.LeftButton
    )
    assert not dialog.isVisible()


def test_clicking_outside_the_guide_dismisses_the_popup(qtbot, tmp_path):
    window, dialog = _open_guide(qtbot, tmp_path)
    assert dialog.windowType() == Qt.WindowType.Popup
    assert not dialog.isModal()
    qtbot.mouseClick(
        dialog,
        Qt.MouseButton.LeftButton,
        pos=QPoint(-10, dialog.height() // 2),
    )
    assert not dialog.isVisible() and window.isVisible()
    qtbot.mouseClick(window.guide_button, Qt.MouseButton.LeftButton)
    assert dialog.isVisible()


def test_controls_refresh_and_arrows_bisect_the_step_gaps(qtbot, tmp_path):
    options = tmp_path / "dj2/options.txt"
    options.parent.mkdir()
    options.write_text("key_key.betterquesting.quests:41\nkey_key.inventory:18\n")
    window, dialog = _open_guide(qtbot, tmp_path)
    scopes = _select(qtbot, dialog, "guideCommands")
    scopes.setCurrentIndex(1)
    hint = dialog.findChild(QLabel, "questBookControl")
    assert "Ё / `" in hint.text()
    qtbot.waitUntil(hint.isVisible)
    steps = scopes.findChildren(QWidget, "questFlowStep")
    arrows = scopes.findChildren(QLabel, "questFlowArrow")
    for index, arrow in enumerate(arrows):
        left, right = (step.geometry() for step in steps[index : index + 2])
        assert (
            abs(arrow.geometry().center().x() - (left.right() + right.left()) / 2) <= 1
        )
        assert abs(arrow.geometry().center().y() - left.center().y()) <= 1

    dialog.accept()
    options.write_text("key_key.betterquesting.quests:34:CONTROL\n")
    qtbot.mouseClick(window.guide_button, Qt.MouseButton.LeftButton)
    assert "Ctrl + G" in hint.text()


def test_unknown_pack_gets_the_common_guide_without_ftb_pages(qtbot):
    parent = QWidget()
    qtbot.addWidget(parent)
    future = replace(next(iter(load_profiles())), id="future_pack")
    dialog = PlayerGuideDialog(parent, [future])
    qtbot.addWidget(dialog)
    assert dialog.pages.count() == 2
    assert dialog.findChild(QTabWidget, "guideCommandsPage").count() == 1
