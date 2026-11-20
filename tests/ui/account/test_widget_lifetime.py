import gc
import weakref

import pytest
from PySide6.QtWidgets import QWidget
from shiboken6 import isValid


@pytest.mark.parametrize("method", ["addWidget", "add_widget"])
def test_registered_window_survives_creator_scope_until_framework_teardown(
    qtbot, method
):
    def create():
        widget = QWidget()
        getattr(qtbot, method)(widget)
        with qtbot.waitExposed(widget):
            widget.show()
        return weakref.ref(widget)

    reference = create()
    gc.collect()
    widget = reference()
    assert widget is not None and isValid(widget) and widget.isVisible()
    widget.update()
    qtbot.wait(20)
    assert isValid(widget) and widget.isVisible()
