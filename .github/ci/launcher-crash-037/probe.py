"""Local full-client check of the launcher's crash dialog."""

import contextlib
import hashlib
import json
import os
import secrets
import shutil
import socket
import sys
import threading
import time
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4

tools_root = Path(__file__).resolve().parent.parent
lab = Path(os.environ.get("OMK_CRASH_PROBE_ROOT", str(Path(__file__).resolve().parent)))
worktree = Path(os.environ.get("OMK_CRASH_TEST_REPO", str(tools_root / "full-dj2-crash-check")))
assert (lab / "OWNED_CRASH_PROBE").is_file()
sys.path.insert(0, str(worktree))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QLabel, QLineEdit

from launcher.accounts import AccountService
from launcher.app import LauncherWindow
from launcher.controller import InstallationResult
from launcher.game import GameRunner
from launcher.releases import Artifact, read_release
from launcher.session import Session
from launcher.storage import FileSessionStore
from launcher.ui.crash_dialog import CrashDialog
from omk.accounts.drasl import DraslClient
from omk.labs.launcher.client_crash_fixture import CrashLabRunner
from omk.labs.mcp.mcmcp_lab import _config


class Metadata(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.rstrip("/") != "/authlib-injector":
            self.send_error(404)
            return
        payload = json.dumps({
            "meta": {
                "serverName": "Omkality local crash check",
                "implementationName": "Local fixture",
                "implementationVersion": "1",
            },
            "skinDomains": [],
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):
        pass


class VirtualMacCrashRunner(CrashLabRunner):
    """Use a software context on the hosted macOS test worker."""

    def command(self, *args, **kwargs):
        command = super().command(*args, **kwargs)
        if sys.platform == "darwin" and os.environ.get("OMK_TEST_MAC_SOFTWARE_GL") == "1":
            command.insert(1, "-Dorg.lwjgl.opengl.Display.allowSoftwareOpenGL=true")
        return command


def free_local_port():
    with socket.socket() as stream:
        stream.bind(("127.0.0.1", 0))
        return stream.getsockname()[1]


def main(mode):
    assert mode in {"report", "no-report", "normal", "baseline"}
    stage = json.loads((lab / "stage.json").read_text())
    root, folder = Path(stage["root"]), Path(stage["game"])
    assert root == lab / "client" and folder == root / "instances/dj2"
    keys = json.loads((worktree / "launcher/assets/release-keys.json").read_text())
    signed = read_release(Path(stage["manifest"]).read_bytes(), keys)
    mcp_pin = json.loads((worktree / "profiles/lab/mcmcp.json").read_text())["artifacts"][0]
    jar_source = Path(os.environ.get("OMK_CRASH_TOOLING", str(tools_root / "tooling"))) / mcp_pin["name"]
    data = jar_source.read_bytes()
    assert len(data) == mcp_pin["size"] and hashlib.sha256(data).hexdigest() == mcp_pin["sha256"]
    relative_jar = "mods/" + jar_source.name
    release = signed
    if mode != "baseline":
        shutil.copyfile(jar_source, folder / relative_jar)
        release = replace(signed, files=(*signed.files, Artifact(relative_jar, mcp_pin["sha256"], mcp_pin["size"])))
    client_port = free_local_port()
    link_port = int(os.environ.get("OMK_CRASH_LAB_LINK_PORT", "25680"))
    (folder / "config/mcmcp.cfg").write_text(
        _config(lab.name.removeprefix("client-crash-lab-"), client_port, link_port)
        .replace("B:allowCommands=true", "B:allowCommands=false"),
        encoding="utf-8",
    )
    request = lab / "request-client-crash"
    no_report = lab / "request-log-only-failure"
    stop = lab / "request-close-validated-probe"
    for path in (request, no_report, stop):
        path.unlink(missing_ok=True)
    previous = set((folder / "crash-reports").glob("crash-*.txt"))
    start = time.monotonic()
    state = {
        "mode": mode,
        "version": signed.version,
        "manifest_digest": signed.digest,
        "signed_artifacts": len(signed.files),
        "mcp_endpoint": f"http://127.0.0.1:{client_port}/mcp",
        "previous_reports": len(previous),
        "runner_pid": os.getpid(),
        "process_terminated_by_probe": False,
    }

    def status(phase, **new):
        state.update(new, phase=phase)
        where = lab / "probe-state.json"
        temp = where.with_suffix(".new")
        temp.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        os.replace(temp, where)
        print(phase, flush=True)

    with ThreadingHTTPServer(("127.0.0.1", 0), Metadata) as metadata:
        threading.Thread(target=metadata.serve_forever, daemon=True).start()
        origin = f"http://127.0.0.1:{metadata.server_port}"
        session = Session(
            origin, "Dj2CrashProbe", str(uuid4()), "Dj2CrashProbe",
            secrets.token_hex(24), secrets.token_hex(24),
        )
        service = AccountService(DraslClient(origin), FileSessionStore(root / "userdata/session.json"))
        service.current = session
        runner = (
            GameRunner(root) if mode == "baseline"
            else VirtualMacCrashRunner(root, fixture=Path(stage["agent"]), marker=request)
        )
        app = QApplication([])
        app.setQuitOnLastWindowClosed(False)
        window = LauncherWindow(service, auto_restore=False, runner=runner)
        window.pages.setCurrentWidget(window.home_page)
        window.greeting.setText("Привет, Dj2CrashProbe!")
        window.show()
        status("launching")
        game = runner.start(release, folder, session)
        status("java-started", game_pid=game.process.pid)
        window._installed("dj2", InstallationResult(release, folder, game))
        result_written = False
        report_seen_at = None
        gui_timer = QTimer(window)
        gui_timer.setInterval(450)

        def check():
            nonlocal result_written, report_seen_at
            if stop.exists() or time.monotonic() - start > 900:
                app.quit()
                return
            if result_written:
                return
            saved = set((folder / "crash-reports").glob("crash-*.txt")) - previous
            raw = next((p for p in saved if b"ControlledClientCrash" in p.read_bytes()), None)
            alive = game.poll() is None
            if mode == "report" and alive and raw is not None:
                if report_seen_at is None:
                    report_seen_at = time.monotonic()
                    status("minecraft-report-written", raw_report=raw.name)
                elif time.monotonic() - report_seen_at > 8:
                    # Recovered modded crashes may keep the process alive.
                    state["process_terminated_by_probe"] = True
                    game.process.terminate()
            elif mode == "no-report" and alive and no_report.exists():
                state["process_terminated_by_probe"] = True
                game.process.terminate()
            if game.poll() is None or not game.diagnostics_done.is_set() or window.game is not None:
                return
            dialogs = [item for item in window.findChildren(CrashDialog) if item.isVisible()]
            expected = {"report": folder / "crash-reports", "no-report": game.log_path.parent}.get(mode)
            actual = (
                dialogs[0].findChild(QLineEdit, "crashDirectory").text() if len(dialogs) == 1 else None
            )
            labels = [label.text() for item in dialogs for label in item.findChildren(QLabel)]
            ok = len(dialogs) == int(expected is not None) and actual == (str(expected) if expected else None)
            if mode in {"normal", "baseline"}:
                ok = ok and game.poll() == 0 and not saved
            else:
                ok = ok and "Minecraft вылетел" in labels and "Мы получили отчёт" not in labels
                ok = ok and game.poll() != 0 and game.log_path.is_file()
                if mode == "report":
                    ok = ok and raw is not None
                else:
                    ok = ok and not saved
            screenshot = lab / f"dj2-full-crash-{mode}-20261125.png"
            if dialogs:
                assert not screenshot.exists() and dialogs[0].grab().save(str(screenshot))
            status(
                "verified" if ok else "unexpected-result",
                ok=ok,
                game_exit=game.poll(),
                crash_dialog_count=len(dialogs),
                dialog_directory=actual,
                new_report_names=sorted(p.name for p in saved),
                labels=labels,
            )
            result_written = True

        gui_timer.timeout.connect(check)
        gui_timer.start()
        try:
            app.exec()
        finally:
            if game.poll() is None:
                game.process.terminate()
                game.process.wait(15)
            game.diagnostics_done.wait(15)
            metadata.shutdown()
        return 0 if state.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
