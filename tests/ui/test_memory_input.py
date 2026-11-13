"""Memory choices require deliberate input, even in a scrolling pack list."""

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication, QScrollArea, QStyle, QStyleOptionSlider

from launcher.dashboard import Dashboard
from launcher.memory import STEP_MB, MemorySnapshot, Preferences


@pytest.fixture
def panel(qtbot, tmp_path):
    preferences = Preferences(tmp_path / "preferences.json")
    preferences.save_memory("dj2", 6144)
    widget = Dashboard(preferences, MemorySnapshot(32768, 24000))
    qtbot.addWidget(widget)
    widget.resize(1020, 520)
    widget.show()
    return widget


def wheel(slider, angle, pixels=QPoint(), *, modifiers=Qt.KeyboardModifier.NoModifier):
    window = slider.window()
    QTest.wheelEvent(
        window.windowHandle(),
        slider.mapTo(window, slider.rect().center()),
        angle,
        pixelDelta=pixels,
        stateKey=modifiers,
        phase=(
            Qt.ScrollPhase.ScrollUpdate
            if not pixels.isNull()
            else Qt.ScrollPhase.NoScrollPhase
        ),
    )


@pytest.mark.parametrize("focused", [False, True])
@pytest.mark.parametrize(
    ("angle", "pixels", "modifiers"),
    [
        (QPoint(0, 120), QPoint(), Qt.KeyboardModifier.NoModifier),
        (QPoint(0, -120), QPoint(), Qt.KeyboardModifier.NoModifier),
        (QPoint(120, 0), QPoint(), Qt.KeyboardModifier.NoModifier),
        (QPoint(), QPoint(0, -24), Qt.KeyboardModifier.NoModifier),
        (QPoint(), QPoint(24, 0), Qt.KeyboardModifier.NoModifier),
        (QPoint(0, 120), QPoint(), Qt.KeyboardModifier.ControlModifier),
    ],
)
def test_wheel_never_changes_memory_or_persisted_choice(
    panel, focused, angle, pixels, modifiers
):
    control = panel.cards["dj2"].memory
    slider = control.slider
    slider.setFocus() if focused else slider.clearFocus()
    QApplication.processEvents()
    assert slider.hasFocus() is focused
    before = panel.preferences.path.read_bytes()
    changed = QSignalSpy(control.changed)
    wheel(slider, angle, pixels, modifiers=modifiers)
    assert control.selected_mb == 6144
    assert changed.count() == 0
    assert panel.preferences.path.read_bytes() == before


def test_vertical_wheel_over_focused_slider_scrolls_pack_list(panel):
    slider = panel.cards["dj2"].memory.slider
    scroll = panel.findChild(QScrollArea)
    scroll.ensureWidgetVisible(slider)
    slider.setFocus()
    QApplication.processEvents()
    bar = scroll.verticalScrollBar()
    assert bar.maximum() > bar.value()
    before = bar.value()
    wheel(slider, QPoint(0, -120))
    assert bar.value() > before
    assert panel.cards["dj2"].memory.selected_mb == 6144


def test_keyboard_and_drag_still_save_memory(qtbot, panel):
    control = panel.cards["dj2"].memory
    slider = control.slider
    slider.setFocus()
    qtbot.keyClick(slider, Qt.Key.Key_Right)
    assert control.selected_mb == 6144 + STEP_MB
    assert Preferences(panel.preferences.path).memory["dj2"] == control.selected_mb
    # Drag from the current handle to the right, rather than setting the value in code.
    option = QStyleOptionSlider()
    slider.initStyleOption(option)
    handle = slider.style().subControlRect(
        QStyle.ComplexControl.CC_Slider,
        option,
        QStyle.SubControl.SC_SliderHandle,
        slider,
    )
    before = control.selected_mb
    qtbot.mousePress(slider, Qt.MouseButton.LeftButton, pos=handle.center())
    qtbot.mouseMove(slider, handle.center() + QPoint(60, 0))
    qtbot.mouseRelease(
        slider, Qt.MouseButton.LeftButton, pos=handle.center() + QPoint(60, 0)
    )
    assert control.selected_mb > before
    assert Preferences(panel.preferences.path).memory["dj2"] == control.selected_mb
