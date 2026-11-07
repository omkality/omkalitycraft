import pytest
from PySide6.QtCore import QAbstractAnimation, QEvent, QPoint, QPointF, Qt
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


def leave(view):
    QApplication.sendEvent(view, QEvent(QEvent.Type.Leave))


def test_drag_rotates_and_tilts_without_changing_skin(qtbot, view):
    before, image = view.get_angle(), view.image.copy()
    qtbot.mousePress(view, Qt.MouseButton.LeftButton, pos=QPoint(90, 100))
    qtbot.mouseMove(view, QPoint(160, 140))
    qtbot.mouseRelease(view, Qt.MouseButton.LeftButton, pos=QPoint(160, 140))
    assert view.get_angle() != before
    assert view._pitch != -12
    assert view.image == image
    assert view.animation.state() == QAbstractAnimation.State.Paused
    assert view.cursor().shape() == Qt.CursorShape.OpenHandCursor


def test_autorotation_resumes_from_selected_pose_without_snapping(qtbot, view):
    qtbot.mousePress(view, Qt.MouseButton.LeftButton, pos=QPoint(70, 120))
    qtbot.mouseMove(view, QPoint(170, 120))
    qtbot.mouseRelease(view, Qt.MouseButton.LeftButton, pos=QPoint(170, 120))
    selected = view.get_angle()
    leave(view)
    assert view.get_angle() == pytest.approx(selected)
    assert view.animation.duration() == 45000
    qtbot.waitUntil(lambda: view.get_angle() > selected, timeout=1000)


def test_leaving_while_dragging_waits_for_release(qtbot, view):
    qtbot.mousePress(view, Qt.MouseButton.LeftButton, pos=QPoint(100, 100))
    leave(view)
    assert view.animation.state() == QAbstractAnimation.State.Paused
    qtbot.mouseRelease(view, Qt.MouseButton.LeftButton, pos=QPoint(100, 100))
    assert view.animation.state() == QAbstractAnimation.State.Running


def test_hidden_view_pauses_and_cancels_drag_without_resetting_pose(qtbot, view):
    qtbot.mousePress(view, Qt.MouseButton.LeftButton, pos=QPoint(90, 100))
    qtbot.mouseMove(view, QPoint(170, 100))
    selected = view.get_angle()
    view.hide()
    assert view.animation.state() != QAbstractAnimation.State.Running
    assert view._drag_position is None
    view.show()
    leave(view)
    assert view.get_angle() == pytest.approx(selected)


def test_right_button_does_not_rotate(qtbot, view):
    selected = view.get_angle()
    qtbot.mousePress(view, Qt.MouseButton.RightButton, pos=QPoint(90, 100))
    qtbot.mouseMove(view, QPoint(170, 100))
    qtbot.mouseRelease(view, Qt.MouseButton.RightButton, pos=QPoint(170, 100))
    assert view.get_angle() == pytest.approx(selected)


def test_vertical_drag_is_bounded(qtbot, view):
    qtbot.mousePress(view, Qt.MouseButton.LeftButton, pos=QPoint(90, 100))
    qtbot.mouseMove(view, QPoint(90, 350))
    assert -45 <= view._pitch <= 35
    qtbot.mouseMove(view, QPoint(90, 0))
    assert -45 <= view._pitch <= 35
    qtbot.mouseRelease(view, Qt.MouseButton.LeftButton, pos=QPoint(90, 0))
