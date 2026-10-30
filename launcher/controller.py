"""One bounded installation/launch operation at a time; UI receives state signals."""

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, QThreadPool, Signal, Slot

from launcher.accounts import AccountService
from launcher.game import GameProcess, GameRunner
from launcher.install import InstallCancelled, Installer
from launcher.mod_policy import clean_extra_mods
from launcher.releases import Release, ReleaseError
from launcher.tasks import Task


@dataclass(frozen=True)
class InstallationResult:
    release: Release
    folder: Path
    game: GameProcess | None = None


class InstallController(QObject):
    started = Signal(str)
    progress = Signal(str, object)
    completed = Signal(str, object)
    failed = Signal(str, object)
    states = Signal(object)

    def __init__(
        self,
        installer: Installer,
        service: AccountService,
        runner: GameRunner,
        parent: QObject,
    ) -> None:
        super().__init__(parent)
        self.installer, self.service, self.runner = installer, service, runner
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        self.busy = False
        self.active_pack: str | None = None
        self._task: Task | None = None
        self._state_task: Task | None = None

    def inspect(self, pack_ids: list[str]) -> None:
        task = Task(
            lambda: {
                pack_id: self.installer.local_state(pack_id) for pack_id in pack_ids
            }
        )
        task.signals.completed.connect(self.states.emit)
        self._state_task = task
        self.pool.start(task)

    def start(self, pack_id: str, *, play: bool, memory_mb: int | None = None) -> None:
        if self.busy:
            return
        self.busy, self.active_pack = True, pack_id
        self.installer.cancel.clear()
        self.started.emit(pack_id)

        def operation() -> InstallationResult:
            local = self.installer.local_state(pack_id)
            try:
                release = self.installer.client.fetch(pack_id)
            except ReleaseError, OSError:
                if play and local.get("state") == "installed":
                    release = local["release"]
                else:
                    raise
            if self.installer.cancel.is_set():
                raise InstallCancelled("Загрузка приостановлена.")
            clean_extra_mods(release, self.installer.directory(pack_id))
            folder = self.installer.install(release, task.signals.progress.emit)
            game = (
                self.runner.start(
                    release, folder, self.service.renew_for_game(), memory_mb=memory_mb
                )
                if play
                else None
            )
            return InstallationResult(release, folder, game)

        task = Task(operation)
        task.signals.progress.connect(lambda value: self.progress.emit(pack_id, value))
        task.signals.completed.connect(self._done)
        task.signals.failed.connect(self._failed)
        self._task = task
        self.pool.start(task)

    @Slot(object)
    def _done(self, result: InstallationResult) -> None:
        pack_id = self.active_pack
        self.busy, self._task, self.active_pack = False, None, None
        self.completed.emit(pack_id, result)

    @Slot(object)
    def _failed(self, error: Exception) -> None:
        pack_id = self.active_pack
        self.busy, self._task, self.active_pack = False, None, None
        self.failed.emit(pack_id, error)

    def cancel(self) -> None:
        self.installer.cancel.set()
