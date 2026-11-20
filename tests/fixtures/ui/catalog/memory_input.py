"""Test dependencies for memory input."""

import pytest

from launcher.dashboard import Dashboard
from launcher.memory import MemorySnapshot, Preferences


@pytest.fixture
def panel(qtbot, tmp_path):
    preferences = Preferences(tmp_path / "preferences.json")
    preferences.save_memory("dj2", 6144)
    widget = Dashboard(preferences, MemorySnapshot(32768, 24000))
    qtbot.addWidget(widget)
    widget.resize(1020, 520)
    widget.show()
    return widget
