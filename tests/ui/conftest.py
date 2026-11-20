import gc
import os
from dataclasses import replace

import pytest

from omk.profiles import load_profiles

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture
def qtbot(qtbot):
    """Keep Python-owned top-level widgets alive until pytest-qt closes them."""
    retained = []
    original, original_alias = qtbot.addWidget, qtbot.add_widget

    def register(widget, *, before_close_func=None):
        original(widget, before_close_func=before_close_func)
        retained.append(widget)

    qtbot.addWidget = qtbot.add_widget = register
    try:
        yield qtbot
    finally:
        qtbot.addWidget, qtbot.add_widget = original, original_alias
        retained.clear()


@pytest.fixture(scope="session", autouse=True)
def cyclic_gc_stress():
    previous = gc.get_threshold()
    if os.environ.get("OMK_TEST_QT_GC_STRESS") == "1":
        gc.set_threshold(20, 2, 2)
    try:
        yield
    finally:
        gc.set_threshold(*previous)


@pytest.fixture
def planned_profile():
    (dj2,) = load_profiles()
    return replace(
        dj2,
        id="planned",
        name="Тестовая сборка",
        status="planned",
        requirements=replace(dj2.requirements, state="pending", recommended=None),
    )
