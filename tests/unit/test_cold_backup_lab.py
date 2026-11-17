import subprocess
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from omk.cold_backup_lab import Lab


def test_invalid_child_reply_still_reaps_all_owned_processes(tmp_path, monkeypatch):
    lab = Lab.__new__(Lab)
    lab.report = {"checks": []}
    first, second = Mock(), Mock()
    first.communicate.return_value = (b"invalid JSON", b"")
    first.poll.return_value = 1
    second.poll.return_value = None
    second.wait.side_effect = [subprocess.TimeoutExpired("owned fixture", 10), 0]
    popen = Mock(side_effect=[first, second])
    monkeypatch.setattr("omk.cold_backup_lab.subprocess.Popen", popen)
    with pytest.raises(ValidationError):
        lab.children(tmp_path / "operator.toml", "a" * 32, versioned=True)
    assert popen.call_count == 2
    first.wait.assert_called_once_with(timeout=10)
    second.terminate.assert_called_once()
    second.kill.assert_called_once()
    assert second.wait.call_count == 2


def test_second_launch_failure_reaps_the_first_owned_process(tmp_path, monkeypatch):
    lab = Lab.__new__(Lab)
    lab.report = {"checks": []}
    first = Mock()
    first.poll.return_value = None
    monkeypatch.setattr(
        "omk.cold_backup_lab.subprocess.Popen",
        Mock(side_effect=[first, OSError("synthetic startup failure")]),
    )
    with pytest.raises(OSError, match="synthetic startup failure"):
        lab.children(tmp_path / "operator.toml", "a" * 32, versioned=True)
    first.terminate.assert_called_once()
    first.wait.assert_called_once_with(timeout=10)
