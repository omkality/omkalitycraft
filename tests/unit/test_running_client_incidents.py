import json
from unittest.mock import Mock
from uuid import uuid4

import pytest

from omk.incidents import (
    RunningCrashWatcher,
    _write_queued_report,
    capture_incident,
    validate_report,
)
from tests.unit.test_client_incidents import report
from tests.unit.test_game_runner import fixture


def watcher_fixture(root):
    folder, release, session = fixture(root)
    notify = Mock()
    watcher = RunningCrashWatcher(
        root,
        folder,
        release,
        session,
        baseline={},
        run_id=uuid4().hex,
        memory_mb=6144,
        launcher="lab",
        notify=notify,
    )
    crash = folder / "crash-reports/crash-live.txt"
    crash.parent.mkdir()
    return watcher, crash, notify


def test_running_crash_waits_for_stable_file_and_excludes_secrets(tmp_path):
    watcher, crash, notify = watcher_fixture(tmp_path)
    crash.write_text(
        "java.lang.TestException test-game-token\n at test.Client.main(Client.java:5)\n"
        "-- System Details --\nprivate-system-data"
    )
    assert watcher.poll() is None
    assert not (tmp_path / "userdata/client-incidents").exists()
    path = watcher.poll()
    value = json.loads(path.read_text())
    assert value["schema"] == 2 and value["exit_code"] is None
    assert value["process_state"] == "running" and value["run_id"] == watcher.run_id
    assert (
        "test-game-token" not in value["detail"]
        and "private-system-data" not in value["detail"]
    )
    assert "test.Client.main" in value["detail"]
    notify.assert_called_once()
    assert watcher.poll() is None
    assert len(list(path.parent.glob("*.json"))) == 1
    handled = watcher.stop()
    assert (
        capture_incident(
            tmp_path,
            watcher.folder,
            watcher.release,
            watcher.session,
            run_id=watcher.run_id,
            started_at=0,
            exit_code=0,
            memory_mb=6144,
            launcher="lab",
            baseline=handled,
        )
        is None
    )


def test_growing_crash_is_deferred_until_two_equal_observations(tmp_path):
    watcher, crash, notify = watcher_fixture(tmp_path)
    crash.write_text("java.lang.TestException\n")
    assert watcher.poll() is None
    crash.write_text(
        "java.lang.TestException\n at test.CompleteFrame.main(Test.java:5)\n"
    )
    assert watcher.poll() is None
    path = watcher.poll()
    assert "CompleteFrame" in json.loads(path.read_text())["detail"]
    notify.assert_called_once()


def test_two_recoverable_crashes_have_distinct_ids_and_one_game_run(tmp_path):
    watcher, crash, notify = watcher_fixture(tmp_path)
    crash.write_text("java.lang.FirstException\n")
    watcher.poll()
    first = json.loads(watcher.poll().read_text())
    other = crash.with_name("crash-second.txt")
    other.write_text("java.lang.SecondException\n")
    watcher.poll()
    second = json.loads(watcher.poll().read_text())
    assert first["id"] != second["id"]
    assert first["run_id"] == second["run_id"] == watcher.run_id
    assert notify.call_count == 2


def test_queue_write_failure_does_not_mark_crash_as_handled(tmp_path, monkeypatch):
    watcher, crash, notify = watcher_fixture(tmp_path)
    crash.write_text("java.lang.TestException\n")
    watcher.poll()
    original = capture_incident
    monkeypatch.setattr(
        "omk.incidents.capture_incident", Mock(side_effect=OSError("lab disk failure"))
    )
    with pytest.raises(OSError):
        watcher.poll()
    assert watcher.baseline == {}
    notify.assert_not_called()
    monkeypatch.setattr("omk.incidents.capture_incident", original)
    assert watcher.poll() is not None


@pytest.mark.parametrize(
    "updates",
    [
        {"exit_code": 0},
        {"exit_code": False},
        {"kind": "abnormal_exit"},
        {"process_state": "unknown"},
        {"process_state": []},
        {"run_id": "bad"},
        {"process_state": "exited", "exit_code": None},
    ],
)
def test_schema_two_rejects_inconsistent_running_process_metadata(updates):
    value = report(
        schema=2, run_id=uuid4().hex, process_state="running", exit_code=None
    )
    with pytest.raises(ValueError):
        validate_report({**value, **updates})


def test_legacy_report_remains_accepted_and_exited_schema_two_keeps_real_code():
    assert validate_report(report())["schema"] == 1
    value = report(schema=2, run_id=uuid4().hex, process_state="exited", exit_code=255)
    assert validate_report(value)["exit_code"] == 255


def test_queue_publication_is_atomic_and_preserves_existing_report(
    tmp_path, monkeypatch
):
    path = tmp_path / "report.json"
    original = type(path).replace

    def before_commit(source, destination):
        assert not path.exists()
        assert json.loads(source.read_text()) == {"safe": "complete"}
        return original(source, destination)

    monkeypatch.setattr(type(path), "replace", before_commit)
    _write_queued_report(path, {"safe": "complete"})
    with pytest.raises(FileExistsError):
        _write_queued_report(path, {"safe": "different"})
    assert json.loads(path.read_text()) == {"safe": "complete"}
    assert not path.with_suffix(".json.tmp").exists()


def test_failed_queue_commit_leaves_no_partial_or_temporary_report(
    tmp_path, monkeypatch
):
    path = tmp_path / "report.json"
    monkeypatch.setattr(
        type(path), "replace", Mock(side_effect=OSError("lab disk failure"))
    )
    with pytest.raises(OSError):
        _write_queued_report(path, {"safe": "complete"})
    assert not path.exists() and not path.with_suffix(".json.tmp").exists()
