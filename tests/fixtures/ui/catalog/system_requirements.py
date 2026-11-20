"""Test dependencies for system requirements."""

import pytest

from launcher.memory import MemorySnapshot
from launcher.ui.theme import STYLE, install_font
from launcher.widgets import PackCard
from omk.shared.profiles import load_profiles


@pytest.fixture
def card(qtbot, qapp):
    install_font(qapp)
    card = PackCard(load_profiles()[0], MemorySnapshot(16384, 12000))
    card.setStyleSheet(STYLE)
    card.resize(620, 440)
    qtbot.addWidget(card)
    card.show()
    return card
