import io
import os
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from launcher.game import GameRunner
from launcher.releases import Release, ReleaseError
from launcher.session import Session


def fixture(root: Path):
    folder = root / "instances/test"
    folder.mkdir(parents=True)
    release = Release(
        "test",
        "1.0",
        "1.12.2",
        "windows-x64",
        (),
        {
            "java": "runtime/bin/java",
            "agent": "agent.jar",
            "assets": "assets",
            "natives": "natives",
            "classpath": ["forge.jar"],
            "main_class": "net.minecraft.launchwrapper.Launch",
            "game_args": [
                "--username",
                "{username}",
                "--uuid",
                "{uuid}",
                "--accessToken",
                "{access_token}",
            ],
        },
        "test",
        {},
    )
    session = Session(
        "https://auth.example.com",
        "test_player",
        "12345678-1234-1234-1234-123456789abc",
        "test_player",
        "test-game-token",
        "test-client-token",
    )
    return folder, release, session


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
