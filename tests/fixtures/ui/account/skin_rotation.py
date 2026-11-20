"""Test dependencies for skin rotation."""

import pytest
from PySide6.QtCore import QPointF
from PySide6.QtGui import QEnterEvent
from PySide6.QtWidgets import QApplication

from launcher.skin_view import SkinView


@pytest.fixture
def view(qtbot):
    widget = SkinView()
    qtbot.addWidget(widget)
    widget.resize(240, 360)
    widget.show()
    enter(widget)
    return widget


def enter(view):
    point = QPointF(100, 100)
    QApplication.sendEvent(view, QEnterEvent(point, point, point))
