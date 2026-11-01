"""Quiet, coalesced status polling independent of authentication and pack adapters."""

from PySide6.QtCore import QObject, QThreadPool, QTimer, Signal

from launcher.tasks import Task
from omk.drasl import DraslClient


class ServerStatusController(QObject):
    updated = Signal(object)

    def __init__(self, parent, *, origin=None, active=lambda: True):
        super().__init__(parent)
        self.active = active
        self.fetcher = None
        if origin is not None:
            transport = DraslClient(origin, timeout=3)
            self.fetcher = lambda: transport.request("GET", "/servers/status")
        self.busy = False
        self.task = None
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        self.timer = QTimer(self)
        self.timer.setInterval(30000)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()

    def refresh(self):
        if self.busy or self.fetcher is None or not self.active():
            return
        self.busy = True
        self.task = Task(self.fetcher)
        self.task.signals.completed.connect(self._completed)
        self.task.signals.failed.connect(self._failed)
        self.pool.start(self.task)

    def _completed(self, value):
        self.busy = False
        self.task = None
        servers = value.get("servers") if isinstance(value, dict) else None
        self.updated.emit(servers if isinstance(servers, dict) else None)

    def _failed(self, _error):
        self.busy = False
        self.task = None
        self.updated.emit(None)
