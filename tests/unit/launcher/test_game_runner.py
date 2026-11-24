import io
import os
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import Mock, patch

import psutil
import pytest

from launcher.game import GameRunner
from launcher.releases import ReleaseError
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


def test_game_refuses_external_instance(tmp_path: Path):
    folder, release, session = fixture(tmp_path / "outside")
    with pytest.raises(ReleaseError):
        GameRunner(tmp_path / "portable").command(release, folder, session)


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


def test_selected_heap_reaches_java_arguments(tmp_path: Path):
    folder, release, session = fixture(tmp_path)
    command = GameRunner(tmp_path).command(release, folder, session, memory_mb=5120)
    assert [argument for argument in command if argument.startswith("-Xmx")] == [
        "-Xmx5120M"
    ]
    with pytest.raises(ReleaseError):
        GameRunner(tmp_path).command(release, folder, session, memory_mb=100000)


def test_abnormal_child_exit_is_captured_automatically_without_ui(tmp_path):
    class ControlledRunner(GameRunner):
        def command(self, *args, **kwargs):
            return [
                sys.executable,
                "-c",
                "import sys; print('java.lang.TestException: controlled fixture'); sys.exit(1)",
            ]

    folder, release, session = fixture(tmp_path)
    result = ControlledRunner(tmp_path).start(release, folder, session)
    assert result.diagnostics_done.wait(10)
    assert result.poll() == 1
    reports = list((tmp_path / "userdata/client-incidents").glob("*.json"))
    assert len(reports) == 1
    assert "controlled fixture" in reports[0].read_text()


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
    assert not (tmp_path / "userdata/client-incidents").exists()
