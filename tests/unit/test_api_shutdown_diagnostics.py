from types import SimpleNamespace

import pytest

from scripts import diagnose_api_shutdown as probe


@pytest.mark.parametrize("labels", [None, {}, {probe.LABEL: "another-run"}])
def test_unowned_container_is_rejected_before_it_can_be_signalled_or_deleted(labels):
    with pytest.raises(ValueError, match="unowned"):
        probe.checked_state({"Config": {"Labels": labels}, "State": {}}, "this-run")


def test_cleanup_never_stops_or_removes_foreign_container_or_image(monkeypatch):
    calls = []

    def docker(*args, **kwargs):
        calls.append(args)
        return SimpleNamespace(
            returncode=0,
            stdout='[{"Config":{"Labels":{}},"State":{"Running":true}}]',
        )

    monkeypatch.setattr(probe, "docker", docker)
    assert not probe.cleanup(["foreign"], "this-run", "foreign-image")
    assert all("stop" not in call and "rm" not in call for call in calls)


@pytest.mark.parametrize("cycles", ["0", "25"])
def test_bad_cycle_budget_is_rejected_without_starting_docker(monkeypatch, cycles):
    def forbidden(*args, **kwargs):
        raise AssertionError("Docker must not run for an invalid cycle budget")

    monkeypatch.setattr(probe, "docker", forbidden)
    with pytest.raises(SystemExit) as error:
        probe.main(["--cycles", cycles])
    assert error.value.code == 2


def test_stack_collection_preserves_docker_kill_failure_and_stop_budget(monkeypatch):
    calls = []

    class SlowStop:
        attempts = 0

        def __init__(self, command, **kwargs):
            assert command == ["docker", "stop", "--time", "15", "fixture"]

        def communicate(self, timeout):
            self.attempts += 1
            if self.attempts == 1:
                raise probe.subprocess.TimeoutExpired("docker stop", timeout)
            return "fixture", ""

        def poll(self):
            return 0

    states = iter(
        [
            {"Running": True},
            {"Running": True},
            {"Running": False, "ExitCode": 137, "OOMKilled": False},
        ]
    )
    monkeypatch.setattr(probe, "state", lambda *_: next(states))
    monkeypatch.setattr(probe.subprocess, "Popen", SlowStop)
    monkeypatch.setattr(probe, "docker", lambda *args, **_: calls.append(args))

    result = probe.stop_with_stacks("fixture", "owned-run")

    assert result["exit_code"] == 137
    assert result["oom_killed"] is False
    assert result["stacks_requested"] is True
    assert len(calls) == 1
    assert calls[0][:3] == ("exec", "fixture", ".venv/bin/python")
    assert "SIGUSR1" in calls[0][-1]


def test_stacks_are_separate_and_bounded_with_visible_truncation(tmp_path):
    folder = tmp_path / "fixture-stacks"
    folder.mkdir()
    (folder / "stack-1.log").write_bytes(b"a" * 40000)
    (folder / "stack-2.log").write_bytes(b"b" * 40000)
    (folder / "stack-3.log").write_bytes(b"c" * 40000)
    (folder / "stack-4.log").write_bytes(b"")

    result = probe.collect_stacks(tmp_path, "fixture")

    assert result["limited"] is True
    assert set(result["processes"]) == {"stack-1.log", "stack-2.log"}
    assert result["processes"]["stack-1.log"] == {
        "tail": "a" * 32768,
        "truncated": True,
    }
    assert result["processes"]["stack-2.log"] == {
        "tail": "b" * 32768,
        "truncated": True,
    }
