"""Serialize network operations outside the GUI thread."""

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QRunnable, Signal, Slot


class TaskSignals(QObject):
    progress = Signal(object)
    completed = Signal(object)
    failed = Signal(object)


class Task(QRunnable):
    def __init__(self, operation: Callable[[], Any]) -> None:
        super().__init__()
        self.operation = operation
        self.signals = TaskSignals()

    @Slot()
    def run(self) -> None:
        try:
            result = self.operation()
        except Exception as error:
            self.signals.failed.emit(error)
        else:
            self.signals.completed.emit(result)
