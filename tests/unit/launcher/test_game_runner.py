import io
import json
import os
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock, patch
from uuid import uuid4

import psutil
import pytest

from launcher.game import GameRunner
from launcher.paths import BRAND_ICON
from launcher.releases import ReleaseError
from omk.accounts.drasl import DraslError
from omk.observability.incidents import capture_incident
from tests.fixtures.unit.launcher.game_runner import fixture

__all__ = ["fixture"]


def test_game_uses_portable_java_and_paths_without_shell(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = tmp_path / "portable folder with spaces"
    folder, release, session = fixture(root)
    runner = GameRunner(root)
    for name in ["JAVA_TOOL_OPTIONS", "_JAVA_OPTIONS", "JDK_JAVA_OPTIONS"]:
        monkeypatch.setenv(name, "unexpected global java option")
    process = Mock()
    process.wait.return_value = 0
    process.stdout = io.BytesIO(b"test-game-token test-client-token\nnormal output\n")
    with patch("launcher.game.subprocess.Popen", return_value=process) as start:
        result = runner.start(release, folder, session)
    command = start.call_args.args[0]
    assert command[0] == str(folder / "runtime/bin/java")
    assert "test-game-token" in command  # A game-scoped token is required by Minecraft.
    assert "test-client-token" not in command
    assert "-Dfile.encoding=UTF-8" in command
    assert f"-XX:ErrorFile={folder / 'hs_err_pid%p.log'}" in command
    assert any(str(root / "userdata/java-home") in argument for argument in command)
    assert start.call_args.kwargs["shell"] is False
    assert start.call_args.kwargs["stdout"] == subprocess.PIPE
    assert (
        start.call_args.kwargs["env"]["DisableEntirelyCrashAssistantModOnSystem"]
        == "true"
    )
    assert all(
        name not in start.call_args.kwargs["env"]
        for name in ["JAVA_TOOL_OPTIONS", "_JAVA_OPTIONS", "JDK_JAVA_OPTIONS"]
    )
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        if result.log_path.exists() and "normal output" in result.log_path.read_text():
            break
        time.sleep(0.01)
    text = result.log_path.read_text()
    assert "test-game-token" not in text and "test-client-token" not in text
    assert "normal output" in text
    assert result.diagnostics_done.wait(2)
    assert result.crash_report is None


def test_game_refuses_external_instance(tmp_path: Path):
    folder, release, session = fixture(tmp_path / "outside")
    with pytest.raises(ReleaseError):
        GameRunner(tmp_path / "portable").command(release, folder, session)


@pytest.mark.parametrize(
    ("platform", "minecraft", "lwjgl", "keep_first_thread"),
    [
        ("macos-arm64", "1.12.2", "2.9.4-nightly-20150209", False),
        ("macos-x64", "1.12.2", "2.9.4-nightly-20150209", True),
        ("macos-arm64", "1.12.2", "3.3.1", True),
        ("macos-arm64", "1.20.1", "3.3.1", True),
        ("windows-x64", "1.12.2", "2.9.4-nightly-20150209", True),
    ],
)
def test_first_thread_flag_respects_the_graphics_stack(
    tmp_path, platform, minecraft, lwjgl, keep_first_thread
):
    folder, release, session = fixture(tmp_path)
    first_thread = "-XstartOnFirstThread"
    release = replace(
        release,
        platform=platform,
        minecraft=minecraft,
        launch={
            **release.launch,
            "classpath": [f"libraries/org/lwjgl/lwjgl/{lwjgl}/lwjgl-{lwjgl}.jar"],
            "jvm_args": ["-XX:+UseG1GC", first_thread, "-Dtest.option=kept"],
        },
    )
    command = GameRunner(tmp_path).command(release, folder, session)
    assert (first_thread in command) is keep_first_thread
    assert command.count("-XX:+UseG1GC") == 1
    assert "-Dtest.option=kept" in command
    dock_args = [value for value in command if value.startswith("-Xdock:")]
    assert dock_args == (
        ["-Xdock:name=OmkalityCraft", f"-Xdock:icon={BRAND_ICON}"]
        if platform.startswith("macos-")
        else []
    )


def test_restart_refuses_a_second_copy_of_the_same_pack(tmp_path, monkeypatch):
    previous = tmp_path / "previous portable copy"
    old_folder, release, session = fixture(previous)
    command = GameRunner(previous).command(release, old_folder, session)
    user = psutil.Process().username()
    process = Mock(pid=1234, info={"name": "java", "username": user})
    process.cmdline.return_value = command
    monkeypatch.setattr(psutil, "process_iter", lambda *_: [process])
    new_root = tmp_path / "new portable copy"
    folder, _, _ = fixture(new_root)
    with (
        patch("launcher.game.subprocess.Popen", side_effect=AssertionError) as start,
        pytest.raises(ReleaseError, match="Minecraft уже запущен"),
    ):
        GameRunner(new_root).start(release, folder, session)
    start.assert_not_called()


def test_running_checks_distinguish_game_from_java_helpers(tmp_path, monkeypatch):
    folder, release, session = fixture(tmp_path)
    command = GameRunner(tmp_path).command(release, folder, session)
    user = psutil.Process().username()
    helper = Mock(pid=1234, info={"name": "java", "username": user})
    helper.cmdline.return_value = [
        *command[: command.index("-cp")],
        "-jar",
        "helper.jar",
    ]
    other_user = Mock(pid=1235, info={"name": "java", "username": user + "-other"})
    other_user.cmdline.return_value = command
    monkeypatch.setattr(psutil, "process_iter", lambda *_: [helper, other_user])
    GameRunner(tmp_path).ensure_stopped(release)
    other_user.cmdline.assert_not_called()


def test_mac_duplicate_game_with_an_application_name_is_detected(tmp_path, monkeypatch):
    folder, release, session = fixture(tmp_path)
    release = replace(release, platform="macos-arm64")
    runner = GameRunner(tmp_path)
    child = Mock(
        pid=1234, info={"name": "Launch", "username": psutil.Process().username()}
    )
    child.exe.return_value = str(folder / "runtime/bin/java")
    child.cmdline.return_value = runner.command(release, folder, session)
    monkeypatch.setattr(psutil, "process_iter", lambda *_: [child])
    with pytest.raises(ReleaseError, match="Minecraft уже запущен"):
        runner.ensure_stopped(release)


def test_selected_heap_reaches_java_arguments(tmp_path: Path):
    folder, release, session = fixture(tmp_path)
    command = GameRunner(tmp_path).command(release, folder, session, memory_mb=5120)
    assert [argument for argument in command if argument.startswith("-Xmx")] == [
        "-Xmx5120M"
    ]
    with pytest.raises(ReleaseError):
        GameRunner(tmp_path).command(release, folder, session, memory_mb=100000)


@pytest.mark.parametrize(
    "outcome", ["disabled", "accepted", "refused", "offline", "wrong-id"]
)
def test_abnormal_child_exit_is_captured_automatically_without_ui(
    tmp_path, monkeypatch, outcome
):
    class ControlledRunner(GameRunner):
        def command(self, *args, **kwargs):
            return [
                sys.executable,
                "-c",
                "import sys; print('java.lang.TestException: controlled fixture'); sys.exit(1)",
            ]

    folder, release, session = fixture(tmp_path)
    older = capture_incident(
        tmp_path,
        folder,
        release,
        session,
        run_id=uuid4().hex,
        started_at=0,
        exit_code=1,
        memory_mb=6144,
        launcher="test",
    )
    future = time.time() + 60
    os.utime(older, (future, future))

    def respond(method, path, payload, token):
        if outcome == "refused":
            raise DraslError(403)
        if outcome == "offline":
            raise OSError("test API offline")
        return {
            "ok": True,
            "id": older.stem if outcome == "wrong-id" else payload["id"],
        }

    request = Mock(side_effect=respond)
    monkeypatch.setattr(
        "omk.observability.incident_delivery.DraslClient.request", request
    )
    runner = ControlledRunner(
        tmp_path, report_origin=None if outcome == "disabled" else "http://127.0.0.1:1"
    )
    result = runner.start(release, folder, session)
    assert result.diagnostics_done.wait(10)
    assert result.poll() == 1
    assert result.crash_report_received is (outcome == "accepted")
    assert older.exists()
    if outcome == "disabled":
        request.assert_not_called()
    else:
        assert request.call_count == 1
        method, path, payload, token = request.call_args.args
        assert (method, path, token) == (
            "POST",
            "/reports/client",
            session.access_token,
        )
        assert payload["id"] != older.stem
        assert "controlled fixture" in payload["detail"]
    current = sorted(path for path in older.parent.glob("*.json") if path != older)
    if outcome == "accepted":
        assert current == []
    else:
        assert len(current) == 1
        assert "controlled fixture" in json.loads(current[0].read_text())["detail"]


def test_new_silent_failure_never_uploads_previous_runs_stack(tmp_path):
    class SilentFailure(GameRunner):
        def command(self, *args, **kwargs):
            return [sys.executable, "-c", "import sys; sys.exit(1)"]

    folder, release, session = fixture(tmp_path)
    log = tmp_path / "userdata/logs/test-game.log"
    log.parent.mkdir(parents=True)
    log.write_text("java.lang.PreviousAccountException: do not upload\n")
    result = SilentFailure(tmp_path).start(release, folder, session)
    assert result.diagnostics_done.wait(10)
    report = next((tmp_path / "userdata/client-incidents").glob("*.json"))
    assert "PreviousAccountException" not in report.read_text()
    assert "PreviousAccountException" in (log.parent / "test-game.log.1").read_text()


def test_old_future_timestamp_crash_is_not_reported_after_clean_exit(tmp_path):
    class CleanExit(GameRunner):
        def command(self, *args, **kwargs):
            return [sys.executable, "-c", "pass"]

    folder, release, session = fixture(tmp_path)
    crash = folder / "crash-reports/crash-old.txt"
    crash.parent.mkdir()
    crash.write_text("Old crash from before a clock correction")
    os.utime(crash, (time.time() + 86400, time.time() + 86400))
    result = CleanExit(tmp_path).start(release, folder, session)
    assert result.diagnostics_done.wait(10)
    assert result.crash_report is None
    assert not (tmp_path / "userdata/client-incidents").exists()


@pytest.mark.parametrize("name", ["crash-reports/crash-client.txt", "hs_err_pid42.log"])
def test_new_crash_file_remains_visible_even_when_java_returns_zero(tmp_path, name):
    class ControlledCrash(GameRunner):
        def command(self, *args, **kwargs):
            return [
                sys.executable,
                "-c",
                (
                    "from pathlib import Path; import sys; "
                    "path = Path(sys.argv[1]); path.parent.mkdir(exist_ok=True); "
                    "path.write_text('A fatal error: controlled test')"
                ),
                name,
            ]

    folder, release, session = fixture(tmp_path)
    result = ControlledCrash(tmp_path).start(release, folder, session)
    assert result.diagnostics_done.wait(10)
    assert result.poll() == 0
    assert result.crash_report == folder / name


def test_clean_exit_after_recovery_keeps_report_without_marking_a_new_crash(tmp_path):
    class RecoveredGame(GameRunner):
        def command(self, *args, **kwargs):
            return [
                sys.executable,
                "-c",
                """from pathlib import Path
import sys
import time

directory = Path("crash-reports")
directory.mkdir()
(directory / "crash-recovered.txt").write_text("Controlled recovered crash")
deadline = time.monotonic() + 12
reports = Path(sys.argv[1])
while not any(reports.glob("*.json")) and time.monotonic() < deadline:
    time.sleep(0.1)
""",
                str(self.root / "userdata/client-incidents"),
            ]

    folder, release, session = fixture(tmp_path)
    result = RecoveredGame(tmp_path).start(release, folder, session)
    assert result.diagnostics_done.wait(15)
    assert result.poll() == 0
    assert result.crash_report is None
    assert len(list((tmp_path / "userdata/client-incidents").glob("*.json"))) == 1
