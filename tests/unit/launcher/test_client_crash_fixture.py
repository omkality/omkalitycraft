import hashlib
from pathlib import Path
from unittest.mock import Mock
from zipfile import ZipFile

import pytest

from launcher.game import GameRunner
from omk.labs.accounts.operator_lab import _start_api
from omk.labs.launcher.client_crash_fixture import CrashLabRunner, build_crash_agent
from tests.fixtures.unit.launcher.game_runner import fixture


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
        )


def test_unpinned_compiler_is_rejected_before_any_java_execution(tmp_path, monkeypatch):
    compiler = tmp_path / "untrusted.jar"
    compiler.write_bytes(b"not the pinned compiler")
    execute = Mock()
    monkeypatch.setattr(
        "omk.labs.launcher.client_crash_fixture.subprocess.run", execute
    )
    with pytest.raises(ValueError, match="pinned ECJ"):
        build_crash_agent(tmp_path / "unused-java", compiler, tmp_path)
    execute.assert_not_called()
    assert not (tmp_path / "crash-fixture").exists()


def test_compiled_agent_entry_is_declared_in_jar_manifest(tmp_path, monkeypatch):
    compiler = tmp_path / "fixture-compiler.jar"
    data = b"synthetic compiler"
    compiler.write_bytes(data)
    monkeypatch.setattr(
        "omk.labs.launcher.client_crash_fixture.COMPILER_SHA256",
        hashlib.sha256(data).hexdigest(),
    )

    def compile_fixture(command, **kwargs):
        classes = Path(command[command.index("-d") + 1])
        entry = classes / "omk/lab/fixture/ClientCrashAgent.class"
        entry.parent.mkdir(parents=True)
        entry.write_bytes(b"synthetic class")
        return Mock(returncode=0)

    monkeypatch.setattr(
        "omk.labs.launcher.client_crash_fixture.subprocess.run", compile_fixture
    )
    with ZipFile(build_crash_agent(tmp_path / "java", compiler, tmp_path)) as jar:
        assert (
            b"Premain-Class: omk.lab.fixture.ClientCrashAgent"
            in jar.read("META-INF/MANIFEST.MF").splitlines()
        )
        assert "omk/lab/fixture/ClientCrashAgent.class" in jar.namelist()


@pytest.mark.parametrize("port", [True, "25555", 0, 65536])
def test_owned_api_restart_rejects_invalid_ports_before_launch(tmp_path, port):
    with pytest.raises(ValueError, match="port"):
        _start_api(tmp_path, tmp_path / "private", port=port)
