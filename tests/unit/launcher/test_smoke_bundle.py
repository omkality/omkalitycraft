"""Real TUF/HTTP/extraction; synthetic child startup never launches local Qt."""

import json
import subprocess
import zipfile
from pathlib import Path, PurePosixPath
from unittest.mock import Mock

import pytest

from launcher.releases import sha256_file
from launcher.updater import acknowledge_health
from launcher.version import VERSION
from scripts.release import smoke_bundle
from tests.fixtures.unit.launcher.smoke_bundle import ENTRYPOINT, bundle

__all__ = ["ENTRYPOINT", "bundle"]


def snapshot(folder: Path) -> dict:
    return {
        path.relative_to(folder).as_posix(): path.read_bytes()
        for path in folder.rglob("*")
        if path.is_file()
    }


def child_factory(started, *, healthy=True, wrong_nonce=False):
    def start(command, *, cwd, **kwargs):
        executable = Path(command[0])
        root = Path(command[command.index("--root") + 1])
        health = Path(command[command.index("--health-file") + 1])
        nonce = command[command.index("--health-nonce") + 1]
        assert cwd == root
        assert kwargs == {"shell": False}
        version_folder = executable.parents[len(PurePosixPath(ENTRYPOINT).parts) - 1]
        assert version_folder.parent == root / "app_versions"
        assert executable.read_bytes() == b"actual archived executable"
        assert (version_folder / "_internal/runtime.bin").read_bytes() == (
            b"runtime dependency"
        )
        process = Mock()
        process.poll.return_value = None if healthy else 1
        started.append((executable, root, process))
        if healthy:
            acknowledge_health(root, health, "0" * 48 if wrong_nonce else nonce)
        return process

    return start


@pytest.mark.parametrize("directory", [False, True])
def test_archive_delivered_by_tuf_and_real_handoff_activates_exact_zip(
    bundle, monkeypatch, capsys, directory
):
    root, archive, _ = bundle
    before = snapshot(root)
    started = []
    monkeypatch.setattr(smoke_bundle.subprocess, "Popen", child_factory(started))
    original_handoff = smoke_bundle._handoff

    def inspect_activation(updater, update):
        original_handoff(updater, update)
        state = json.loads(updater.state_file.read_text())
        assert state["active"]["digest"] == sha256_file(archive)
        assert state["highest_version"] == VERSION
        assert not list(updater.cache.glob("health-*.json"))

    monkeypatch.setattr(smoke_bundle, "_handoff", inspect_activation)
    smoke_bundle.smoke_archive(archive.parent if directory else archive)
    proof = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert proof["sha256"] == sha256_file(archive)
    assert proof["version"] == VERSION
    assert proof["health_handoff"] is True
    assert proof["tuf_http_requests"] >= 4
    assert len(started) == 1
    executable, portable, process = started[0]
    assert not executable.exists() and not portable.exists()
    process.terminate.assert_called_once()
    process.wait.assert_called_once_with(timeout=10)
    assert snapshot(root) == before


def test_incomplete_zip_cannot_borrow_runtime_from_build_directory(bundle, monkeypatch):
    root, archive, unpacked = bundle
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr(ENTRYPOINT, b"actual archived executable")
    before = snapshot(root)

    # The previous directory-only check can succeed despite this incomplete ZIP.
    def directory_start(command, *, cwd):
        assert Path(command[0]) == unpacked / ENTRYPOINT
        assert (unpacked / "_internal/runtime.bin").is_file()
        acknowledge_health(Path(cwd), Path(command[4]), command[6])
        process = Mock()
        process.poll.return_value = None
        return process

    monkeypatch.setattr(smoke_bundle.subprocess, "Popen", directory_start)
    smoke_bundle.smoke(unpacked)
    monkeypatch.setattr(smoke_bundle.subprocess, "Popen", child_factory([]))
    # Popen's OSError is converted to an unhealthy result by the real updater.
    with pytest.raises(RuntimeError, match="healthy startup"):
        smoke_bundle.smoke_archive(archive)
    assert (unpacked / "_internal/runtime.bin").is_file()
    assert snapshot(root) == before


@pytest.mark.parametrize("invalid", ["missing-entrypoint", "corrupt"])
def test_bad_archive_never_starts_child(bundle, monkeypatch, invalid):
    root, archive, _ = bundle
    if invalid == "corrupt":
        archive.write_bytes(b"invalid zip")
        error = zipfile.BadZipFile
    else:
        with zipfile.ZipFile(archive, "w") as zipped:
            zipped.writestr("_internal/runtime.bin", b"runtime dependency")
        error = ValueError
    before = snapshot(root)
    start = Mock(side_effect=AssertionError("Child must not start"))
    monkeypatch.setattr(smoke_bundle.subprocess, "Popen", start)
    with pytest.raises(error):
        smoke_bundle.smoke_archive(archive)
    start.assert_not_called()
    assert snapshot(root) == before


def test_unhealthy_archive_fails_without_changing_source_or_fixture(
    bundle, monkeypatch
):
    root, archive, _ = bundle
    before = snapshot(root)
    started = []
    monkeypatch.setattr(
        smoke_bundle.subprocess, "Popen", child_factory(started, healthy=False)
    )
    with pytest.raises(RuntimeError, match="healthy startup"):
        smoke_bundle.smoke_archive(archive)
    assert len(started) == 1
    assert not started[0][1].exists()
    started[0][2].wait.assert_called_once_with(timeout=10)
    assert snapshot(root) == before


def test_successful_child_is_reaped_even_if_terminate_times_out(bundle, monkeypatch):
    _, archive, _ = bundle
    started = []
    start = child_factory(started)

    def stubborn_child(*args, **kwargs):
        process = start(*args, **kwargs)
        process.wait.side_effect = [subprocess.TimeoutExpired("synthetic child", 10), 0]
        return process

    monkeypatch.setattr(smoke_bundle.subprocess, "Popen", stubborn_child)
    smoke_bundle.smoke_archive(archive)
    process = started[0][2]
    process.terminate.assert_called_once()
    process.kill.assert_called_once()
    assert process.wait.call_count == 2
    assert not started[0][1].exists()


def test_wrong_health_nonce_never_activates_archive(bundle, monkeypatch):
    _, archive, _ = bundle
    started = []
    monkeypatch.setattr(
        smoke_bundle.subprocess, "Popen", child_factory(started, wrong_nonce=True)
    )
    handoff = smoke_bundle.LauncherUpdater.handoff
    monkeypatch.setattr(
        smoke_bundle.LauncherUpdater,
        "handoff",
        lambda self, update, **kwargs: handoff(self, update, timeout=0.01),
    )
    with pytest.raises(RuntimeError, match="healthy startup"):
        smoke_bundle.smoke_archive(archive)
    assert len(started) == 1
    assert not started[0][1].exists()
