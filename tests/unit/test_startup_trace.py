import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from omk.dj2_linux_lab import JAVA_IMAGE, LinuxServer, container_outcome
from omk.startup_trace_fixture import build_startup_agent
from omk.startup_trace_lab import (
    TraceServer,
    evidence_volume,
    inspect_trace,
    run_startup_trace_lab,
)


def command_server(tmp_path, cls=TraceServer):
    lab = tmp_path / "startup-trace-lab-test"
    lab.mkdir()
    server = cls(lab, "0123456789", "isolated-network")
    server.classpath = "/srv/fixture.jar"
    server.prefetched = "synthetic-public-key-metadata"
    return server


@pytest.mark.parametrize("mode", ["full", "exclusions", "console"])
def test_agent_only_enters_explicit_trace_server_command(tmp_path, mode):
    server = command_server(tmp_path)
    server.new_trace(1)
    server.trace_mode = mode
    normal = LinuxServer.command(server)
    traced = server.command()
    assert all("startup-trace-agent" not in argument for argument in normal)
    assert traced.count("-javaagent:/srv/.omk/startup-trace-agent.jar=/trace") == 1
    assert ("-Domkality.lab.traceMode=exclusions" in traced) == (mode == "exclusions")
    mount = f"type=bind,source={server.trace.resolve()},target=/trace"
    assert mount in traced and traced.index(mount) < traced.index(JAVA_IMAGE)
    assert "127.0.0.1:25576:25576" in traced
    assert traced[traced.index("--memory") + 1] == "6g"
    assert traced[traced.index("--cpus") + 1] == "4" and "-Xmx4G" in traced


def test_trace_folder_must_belong_to_new_lab(tmp_path):
    server = command_server(tmp_path)
    server.trace = tmp_path / "outside"
    server.trace.mkdir()
    with pytest.raises(ValueError, match="isolated"):
        server.command()


def test_unpinned_compiler_is_rejected_before_output_or_execution(
    tmp_path, monkeypatch
):
    compiler = tmp_path / "untrusted.jar"
    compiler.write_bytes(b"untrusted")
    execute = Mock()
    monkeypatch.setattr("omk.startup_trace_fixture.subprocess.run", execute)
    with pytest.raises(ValueError, match="Unpinned"):
        build_startup_agent(tmp_path / "java", compiler, tmp_path, tmp_path)
    execute.assert_not_called()
    assert not (tmp_path / "trace-fixture").exists()


@pytest.mark.parametrize(
    "run_id", ["", "../outside", "A" * 10, "a" * 11, "omk-dj2-linux-1234567890-data"]
)
def test_evidence_id_cannot_select_arbitrary_docker_resources(run_id, monkeypatch):
    inspect = Mock()
    monkeypatch.setattr("omk.startup_trace_lab.inspect_owned", inspect)
    with pytest.raises(ValueError, match="run ID"):
        evidence_volume(run_id)
    inspect.assert_not_called()


def test_running_evidence_is_not_stopped_or_copied(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "omk.startup_trace_lab.inspect_owned",
        lambda kind, *a: (
            {"Name": "owned"} if kind == "volume" else {"State": {"Running": True}}
        ),
    )

    def docker(*args):
        calls.append(args)
        return SimpleNamespace(stdout="owned-container\n")

    monkeypatch.setattr("omk.startup_trace_lab.docker", docker)
    with pytest.raises(ValueError, match="running server"):
        evidence_volume("0123456789")
    assert len(calls) == 1 and calls[0][:2] == ("ps", "-a")


def test_missing_evidence_volume_is_rejected_before_any_copy(monkeypatch):
    monkeypatch.setattr("omk.startup_trace_lab.inspect_owned", lambda *a: None)
    docker = Mock()
    monkeypatch.setattr("omk.startup_trace_lab.docker", docker)
    with pytest.raises(ValueError, match="Missing"):
        evidence_volume("0123456789")
    docker.assert_not_called()


@pytest.mark.parametrize("boots", [0, 13, True, "3"])
def test_invalid_boot_count_does_not_create_a_lab(boots, monkeypatch):
    docker = Mock()
    monkeypatch.setattr("omk.startup_trace_lab.docker", docker)
    with pytest.raises(ValueError, match=r"1\.\.12"):
        run_startup_trace_lab(SimpleNamespace(boots=boots))
    docker.assert_not_called()


def test_metadata_trace_distinguishes_excluded_deobfuscator_and_raw_holder(tmp_path):
    path = tmp_path / "trace.txt"
    path.write_text(
        "\n".join(
            [
                *(
                    name + "-hook-armed"
                    for name in (
                        "launchclassloader",
                        "mixin-legacy",
                        "mixin-service",
                        "reentry-lock",
                    )
                ),
                "DEOBF-EXCLUDED metadata=synthetic",
                "90 IN depth=0 net.minecraftforge.fml.common.asm.transformers."
                "ItemBlockTransformer class=ahb fields=[a:Laow;]",
                "90 ERROR net.minecraftforge.fml.common.asm.transformers."
                "ItemBlockTransformer java.lang.RuntimeException no holder field declared",
            ]
        )
    )
    data = inspect_trace(path)
    assert data["hooks_armed"] and data["deobfuscator_excluded"]
    assert data["unmapped_metadata_holder"] and data["holder_failure_captured"]
    assert not data["instrumentation_error"]
    path.write_text(
        "trace-mode=exclusions\nmixin-service-hook-armed\nDEOBF-EXCLUDED metadata=test\n"
    )
    data = inspect_trace(path)
    assert data["hooks_armed"] and data["mode"] == "exclusions"
    assert data["deobfuscator_excluded"] and not data["holder_failure_captured"]


def test_trace_does_not_claim_success_when_hook_failed_or_log_oversized(tmp_path):
    path = tmp_path / "trace.txt"
    path.write_text("instrumentation-failed java.lang.IllegalStateException\n")
    assert not inspect_trace(path)["hooks_armed"]
    assert inspect_trace(path)["instrumentation_error"]
    path.write_bytes(bytes(2 * 1024**2 + 1))
    with pytest.raises(ValueError, match="large"):
        inspect_trace(path)


def test_console_trace_requires_actual_game_output_and_reads_heap_snapshot(tmp_path):
    path = tmp_path / "trace.txt"
    path.write_text("trace-mode=console\nconsole-hook-armed\n")
    assert not inspect_trace(path)["hooks_armed"]
    path.write_text(
        "trace-mode=console\nconsole-hook-armed\nconsole-game-log-observed\n"
        "DEOBF-EXCLUDED console-stack\nHEAP 1000 2000 4000\n"
    )
    data = inspect_trace(path)
    assert data["hooks_armed"] and data["deobfuscator_excluded"]
    assert data["heap_at_exclusion"] == {
        "free_bytes": 1000,
        "committed_bytes": 2000,
        "max_bytes": 4000,
    }


@pytest.mark.parametrize("oom,exit_code", [(False, 1), (True, 137), (False, 0)])
def test_resource_report_preserves_oom_evidence_without_environment_or_arguments(
    oom, exit_code
):
    source = {
        "State": {"Running": False, "OOMKilled": oom, "ExitCode": exit_code},
        "HostConfig": {"Memory": 6 * 1024**3, "NanoCpus": 4 * 10**9},
        "Config": {
            "Env": ["SECRET=must-not-appear"],
            "Cmd": ["java", "private-argument"],
        },
    }
    data = container_outcome(source)
    assert data["oom_killed"] is oom and data["exit_code"] == exit_code
    assert data["memory_limit_bytes"] == 6 * 1024**3
    assert "SECRET" not in json.dumps(data) and "private-argument" not in json.dumps(
        data
    )
