"""Serialize network operations outside the GUI thread."""

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QRunnable, Signal, Slot


class TaskSignals(QObject):
    """Expose completion and failure signals for a background Qt task."""

    progress = Signal(object)
    completed = Signal(object)
    failed = Signal(object)


class Task(QRunnable):
    """Run a callable in a Qt thread pool and emit its result."""

    def __init__(self, operation: Callable[[], Any]) -> None:
        super().__init__()
        self.operation = operation
        self.signals = TaskSignals()

    @Slot()
    def run(self) -> None:
        """Execute the operation and deliver either its result or exception."""
        try:
            result = self.operation()
        except Exception as error:
            self.signals.failed.emit(error)
        else:
            self.signals.completed.emit(result)
