import json
import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from omk.labs.backup.cold_backup_lab import Lab
from omk.owner.owner_result import failure


def test_invalid_child_reply_still_reaps_all_owned_processes(tmp_path, monkeypatch):
    lab = Lab.__new__(Lab)
    lab.report = {"checks": []}
    first, second = Mock(), Mock()
    first.communicate.return_value = (b"invalid JSON", b"")
    first.poll.return_value = 1
    second.poll.return_value = None
    second.wait.side_effect = [subprocess.TimeoutExpired("owned fixture", 10), 0]
    popen = Mock(side_effect=[first, second])
    monkeypatch.setattr("omk.labs.backup.cold_backup_lab.subprocess.Popen", popen)
    with pytest.raises(ValidationError):
        lab.children(tmp_path / "operator.toml", "a" * 32, versioned=True)
    assert popen.call_count == 2
    first.wait.assert_called_once_with(timeout=10)
    second.terminate.assert_called_once()
    second.kill.assert_called_once()
    assert second.wait.call_count == 2


@pytest.mark.parametrize(
    "root", [r"C:\synthetic\private-owner", "/synthetic/private-owner"]
)
def test_contract_helper_rejects_private_paths_with_platform_json_escaping(
    tmp_path, monkeypatch, root
):
    lab = Lab.__new__(Lab)
    lab.root = Path(root)
    lab.report = {"checks": []}
    value = failure("backups.run", Mock(operation="a" * 32, server=None), "io_failure")
    value["error"]["message"] = str(lab.root)
    monkeypatch.setattr(
        "omk.labs.backup.cold_backup_lab.subprocess.run",
        Mock(return_value=Mock(returncode=1, stdout=json.dumps(value).encode())),
    )
    with pytest.raises(RuntimeError, match="contract_result_omits_private_root"):
        lab.contract_cli(tmp_path / "operator.toml", "run", "a" * 32, success=False)


def test_second_launch_failure_reaps_the_first_owned_process(tmp_path, monkeypatch):
    lab = Lab.__new__(Lab)
    lab.report = {"checks": []}
    first = Mock()
    first.poll.return_value = None
    monkeypatch.setattr(
        "omk.labs.backup.cold_backup_lab.subprocess.Popen",
        Mock(side_effect=[first, OSError("synthetic startup failure")]),
    )
    with pytest.raises(OSError, match="synthetic startup failure"):
        lab.children(tmp_path / "operator.toml", "a" * 32, versioned=True)
    first.terminate.assert_called_once()
    first.wait.assert_called_once_with(timeout=10)
