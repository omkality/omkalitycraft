import os

from tests.fixtures.ui.environment import cyclic_gc_stress, planned_profile, qtbot

__all__ = ["cyclic_gc_stress", "planned_profile", "qtbot"]

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
