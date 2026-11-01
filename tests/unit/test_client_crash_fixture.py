from unittest.mock import Mock

import pytest

from launcher.game import GameRunner
from omk.client_crash_fixture import CrashLabRunner, build_crash_agent
from omk.operator_lab import _start_api
from tests.unit.test_game_runner import fixture


def test_lab_agent_does_not_enter_the_default_game_command(tmp_path):
    lab = tmp_path / "client-crash-lab-test"
    folder, release, session = fixture(lab / "client")
    agent = lab / "crash-fixture/test-agent.jar"
    agent.parent.mkdir()
    agent.write_bytes(b"synthetic fixture")
    normal = GameRunner(lab / "client").command(release, folder, session)
    runner = CrashLabRunner(
        lab / "client",
        fixture=agent,
        marker=lab / "request-client-crash",
        reports_url=None,
    )
    controlled = runner.command(release, folder, session)
    assert all("test-agent.jar" not in arg for arg in normal)
    assert len([arg for arg in controlled if "test-agent.jar" in arg]) == 1
    assert controlled[0] == normal[0]
    assert controlled[2:] == normal[1:]


def test_lab_runner_rejects_fixture_outside_its_isolated_run(tmp_path):
    lab = tmp_path / "client-crash-lab-test"
    with pytest.raises(ValueError, match="isolated"):
        CrashLabRunner(
            lab,
            fixture=tmp_path / "outside.jar",
            marker=lab / "request-client-crash",
            reports_url=None,
        )


def test_unpinned_compiler_is_rejected_before_any_java_execution(tmp_path, monkeypatch):
    compiler = tmp_path / "untrusted.jar"
    compiler.write_bytes(b"not the pinned compiler")
    execute = Mock()
    monkeypatch.setattr("omk.client_crash_fixture.subprocess.run", execute)
    with pytest.raises(ValueError, match="pinned ECJ"):
        build_crash_agent(tmp_path / "unused-java", compiler, tmp_path)
    execute.assert_not_called()
    assert not (tmp_path / "crash-fixture").exists()


@pytest.mark.parametrize("port", [True, "25555", 0, 65536])
def test_owned_api_restart_rejects_invalid_ports_before_launch(tmp_path, port):
    with pytest.raises(ValueError, match="port"):
        _start_api(tmp_path, tmp_path / "private", port=port)
