import json
import os
import subprocess
from pathlib import Path
from unittest.mock import Mock

from omk import backup_safety_lab


def test_cleanup_never_removes_foreign_or_unknown_container(monkeypatch):
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        return Mock(returncode=0, stdout=json.dumps([{"Config": {"Labels": {}}}]))

    monkeypatch.setattr(subprocess, "run", run)
    assert not backup_safety_lab._cleanup("foreign", "expected")
    assert len(calls) == 1 and calls[0] == ["docker", "inspect", "foreign"]


def test_lab_mounts_only_allowlisted_code_and_bounded_disposable_filesystems(
    monkeypatch,
):
    calls = []
    run_id = None

    def run(args, **kwargs):
        nonlocal run_id
        calls.append(args)
        if args[:2] == ["docker", "run"]:
            label = args[args.index("--label") + 1]
            run_id = label.split("=", 1)[1]
            assert "--read-only" in args and "--network" in args and "none" in args
            assert args.count("--mount") == 1 and args.count("--tmpfs") == 3
            assert "--publish" not in args and "-p" not in args
            assert "--pull" in args and args[args.index("--pull") + 1] == "never"
            mount = args[args.index("--mount") + 1]
            assert mount.endswith("target=/code,readonly")
            folder = Path(
                mount.removeprefix("type=bind,source=").removesuffix(
                    ",target=/code,readonly"
                )
            )
            assert {p.name for p in (folder / "omk").iterdir()} == {
                "__init__.py",
                "backup_archive.py",
                "backup_store.py",
                "backup_safety_probe.py",
            }
            if os.name != "nt":
                assert folder.stat().st_mode & 0o777 == 0o755
                assert (folder / "omk").stat().st_mode & 0o777 == 0o755
                assert all(
                    p.stat().st_mode & 0o777 == 0o644
                    for p in (folder / "omk").iterdir()
                )
            return Mock(returncode=0, stdout='{"ok":true}')
        if args[:2] == ["docker", "inspect"]:
            return Mock(
                returncode=0,
                stdout=json.dumps(
                    [{"Config": {"Labels": {backup_safety_lab.LABEL: run_id}}}]
                ),
            )
        assert args[:3] == ["docker", "rm", "--force"]
        return Mock(returncode=0)

    monkeypatch.setattr(subprocess, "run", run)
    result = backup_safety_lab.run_backup_safety_lab()
    assert result["ok"] and result["container_removed"] and len(calls) == 3


def test_daemon_failure_is_not_reported_as_successful_cleanup(monkeypatch):
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: Mock(returncode=1, stdout="", stderr="unavailable"),
    )
    result = backup_safety_lab.run_backup_safety_lab()
    assert not result["ok"] and not result["container_removed"]


def test_timeout_still_attempts_owned_cleanup(monkeypatch):
    cleanup = Mock(return_value=True)
    monkeypatch.setattr(backup_safety_lab, "_cleanup", cleanup)
    monkeypatch.setattr(
        subprocess, "run", Mock(side_effect=subprocess.TimeoutExpired("docker", 120))
    )
    result = backup_safety_lab.run_backup_safety_lab()
    assert not result["ok"] and result["container_removed"]
    cleanup.assert_called_once()
