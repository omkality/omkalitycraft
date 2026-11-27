"""Portable distribution entry point, including automatic startup updates."""

import argparse
import json
import queue
import sys
import threading
import time
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QLabel, QMessageBox

from launcher.accounts import AccountService
from launcher.app import LauncherLocks, LauncherWindow
from launcher.branding import install_branding
from launcher.game import GameRunner
from launcher.install import Installer, ReleaseClient
from launcher.paths import default_data_dir
from launcher.storage import FileSessionStore
from launcher.ui.theme import ASSETS, STYLE, install_font
from launcher.updater import LauncherUpdater, acknowledge_health
from launcher.version import VERSION
from omk.accounts.drasl import DraslClient
from omk.observability.diagnostics import event, failure


def _startup(app: QApplication, operation):
    splash = QLabel("Проверяем обновления лаунчера…")
    splash.setWindowTitle("OmkalityCraft")
    splash.setStyleSheet(STYLE + "QLabel { padding:32px; }")
    splash.resize(480, 100)
    splash.show()
    messages: queue.SimpleQueue = queue.SimpleQueue()
    result: list = []

    def work():
        try:
            result.append(operation(messages.put))
        except Exception as error:
            result.append(error)

    worker = threading.Thread(target=work, daemon=True)
    worker.start()
    while worker.is_alive():
        while not messages.empty():
            splash.setText(messages.get())
        app.processEvents()
        time.sleep(0.015)
    splash.close()
    app.processEvents()
    return result[0]


def _arguments():
    parser = argparse.ArgumentParser(prog="OmkalityCraft")
    parser.add_argument("--root", type=Path, default=default_data_dir().parent)
    parser.add_argument("--health-file", type=Path)
    parser.add_argument("--health-nonce")
    args = parser.parse_args()
    return args


def _bootstrap_lock(root: Path, handoff: bool):
    if handoff:
        return None
    lock = LauncherLocks.acquire(root / "userdata/updates", "bootstrap.lock")
    if lock is None:
        raise OSError("Another bootstrap is running")
    return lock


def _startup_locks(root: Path, handoff: bool):
    bootstrap = _bootstrap_lock(root, handoff)
    try:
        return bootstrap, LauncherLocks.acquire(root / "userdata")
    except OSError:
        if bootstrap is not None:
            bootstrap.unlock()
        raise


def _update_before_window(app: QApplication, updater: LauncherUpdater, lock):
    warning = ""
    result = _startup(app, updater.prepare)
    if isinstance(result, Exception):
        failure(updater.root, "launcher_update", result)
        warning = (
            "Не удалось проверить обновления. Используется рабочая версия лаунчера."
        )
    fallback = updater.active()
    candidates = (
        [result, fallback]
        if not isinstance(result, Exception) and result is not None
        else [fallback]
    )
    attempted = set()
    for update in candidates:
        if update is None or update.digest in attempted:
            continue
        attempted.add(update.digest)
        lock.unlock()

        def handoff(progress, target=update):
            progress("Запускаем и проверяем новую версию…")
            return updater.handoff(target)

        outcome = _startup(app, handoff)
        if outcome is True:
            return 0, lock, warning
        event(updater.root, "launcher_handoff_failed")
        lock = LauncherLocks.acquire(updater.root / "userdata")
        if lock is None:
            return 2, lock, warning
    return None, lock, warning


def main() -> int:
    args = _arguments()
    root = args.root.resolve()
    event(root, "launcher_started", version=VERSION)
    app = QApplication.instance() or QApplication(sys.argv[:1])
    install_branding(app)
    install_font(app)
    app.setQuitOnLastWindowClosed(False)
    try:
        bootstrap_lock, lock = _startup_locks(root, args.health_file is not None)
    except OSError:
        QMessageBox.information(
            None,
            "OmkalityCraft",
            "Лаунчер уже запускается или папка данных недоступна.",
        )
        return 2
    if lock is None:
        if bootstrap_lock is not None:
            bootstrap_lock.unlock()
        QMessageBox.information(None, "OmkalityCraft", "Лаунчер уже открыт.")
        return 2
    try:
        config = json.loads((ASSETS / "deployment.json").read_text(encoding="utf-8"))
        updater = LauncherUpdater(
            root, config["api_url"], (ASSETS / "tuf-root.json").read_bytes(), VERSION
        )
        update_warning = ""
        if args.health_file is None:
            exit_code, lock, update_warning = _update_before_window(app, updater, lock)
            if exit_code is not None:
                return exit_code
        keys = json.loads((ASSETS / "release-keys.json").read_text(encoding="utf-8"))
        service = AccountService(
            DraslClient(config["auth_url"]),
            FileSessionStore(root / "userdata/session.json"),
        )
        installer = Installer(
            root,
            ReleaseClient(
                config["api_url"],
                keys,
                minimum_generations=config.get("minimum_pack_generations"),
            ),
        )
        report_origin = (
            config["api_url"] if config.get("send_client_reports") is True else None
        )
        window = LauncherWindow(
            service,
            installer=installer,
            runner=GameRunner(root, report_origin=report_origin),
            status_origin=config["api_url"],
            update_warning=update_warning,
        )
        window.setWindowTitle(f"OmkalityCraft · {VERSION}")

        def window_ready():
            event(
                root, "launcher_window_painted", version=VERSION, qt=app.platformName()
            )
            if args.health_file is not None:
                acknowledge_health(root, args.health_file, args.health_nonce or "")

        window.first_painted.connect(window_ready)
        window.show()

        # Closing the launcher while the game runs keeps the instance lock held.
        def maybe_quit():
            if not window.isVisible() and window.game is None and not window.busy:
                app.quit()

        timer = QTimer()
        timer.setInterval(500)
        timer.timeout.connect(maybe_quit)
        timer.start()
        return app.exec()
    except OSError, ValueError, KeyError:
        QMessageBox.warning(
            None,
            "OmkalityCraft",
            "Не удалось открыть настройки лаунчера. Проверьте файлы дистрибутива.",
        )
        return 2
    finally:
        if lock is not None:
            lock.unlock()
        if bootstrap_lock is not None:
            bootstrap_lock.unlock()


if __name__ == "__main__":
    raise SystemExit(main())
