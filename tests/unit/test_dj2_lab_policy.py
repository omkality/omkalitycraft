import json
from unittest.mock import Mock

import pytest

from omk.dj2_lab import _cleanup, approved_mods


def test_approved_mods_accept_legacy_empty_version_and_normal_r_suffix(tmp_path):
    path = tmp_path / "mods.json"
    path.write_text(json.dumps({"micdoodlecore": "", "example": "r1-preview"}))
    assert approved_mods(path) == {"micdoodlecore": "", "example": "r1-preview"}


@pytest.mark.parametrize("value", ["one\nother=mod", "one\rother=mod", "back\\slash"])
def test_approved_mods_reject_properties_injection(tmp_path, value):
    path = tmp_path / "mods.json"
    path.write_text(json.dumps({"example": value}))
    with pytest.raises(ValueError):
        approved_mods(path)


def test_owned_auth_cleanup_is_attempted_even_if_game_server_stop_fails(monkeypatch):
    def failed_stop(_server):
        raise OSError("test failure")

    monkeypatch.setattr("omk.dj2_lab._stop_server", failed_stop)
    run = Mock(return_value=Mock(returncode=0))
    monkeypatch.setattr("omk.dj2_lab.subprocess.run", run)
    report = {"ok": True}
    compose = ["docker", "compose", "--project-name", "omk-forge-lab-test-only"]
    _cleanup(None, None, compose, report)
    assert run.call_args.args[0] == [*compose, "down", "--timeout", "5"]
    assert not report["ok"] and report["temporary_auth_removed"]
