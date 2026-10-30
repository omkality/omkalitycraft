import json
import os
import time
from unittest.mock import Mock
from uuid import uuid4

import pytest

from launcher.session import Session
from omk.incidents import _prune, capture_incident, submit_pending, validate_report
from tests.unit.test_game_runner import fixture


def report(player=None, **updates):
    return {
        "schema": 1,
        "id": uuid4().hex,
        "player": player or uuid4().hex,
        "occurred_at": "2026-10-30T12:00:00+00:00",
        "pack": "dj2",
        "pack_version": "test",
        "minecraft": "1.12.2",
        "platform": "windows-x64",
        "launcher": "test",
        "memory_mb": 6144,
        "exit_code": 1,
        "kind": "minecraft_crash",
        "detail": "java.lang.TestException\n at example.main(Test.java:12)",
        **updates,
    }


def capture(root, *, code=1, since=0):
    folder, release, session = fixture(root)
    value = capture_incident(
        root,
        folder,
        release,
        session,
        run_id=uuid4().hex,
        started_at=since,
        exit_code=code,
        memory_mb=6144,
        launcher="test",
    )
    return value


def test_clean_exit_does_not_create_incident(tmp_path):
    assert capture(tmp_path, code=0) is None
    assert not (tmp_path / "userdata/client-incidents").exists()


def test_capture_reads_only_new_crash_and_excludes_system_dump_and_tokens(tmp_path):
    folder, release, session = fixture(tmp_path)
    (folder / "crash-reports").mkdir()
    text = (
        f"Crash java.lang.TestException test-game-token\n at {folder}/Example.java:1\n"
        "-- System Details --\nprivate-system-sentinel"
    )
    (folder / "crash-reports/crash-new.txt").write_text(text, encoding="utf-8")
    path = capture_incident(
        tmp_path,
        folder,
        release,
        session,
        run_id=uuid4().hex,
        started_at=0,
        exit_code=0,
        memory_mb=6144,
        launcher="test",
    )
    raw = path.read_text(encoding="utf-8")
    assert "TestException" in raw and "test-game-token" not in raw
    assert str(folder) not in raw and "private-system-sentinel" not in raw
    assert json.loads(raw)["kind"] == "minecraft_crash"


def test_old_crash_does_not_turn_clean_exit_into_new_crash(tmp_path):
    folder, release, session = fixture(tmp_path)
    (folder / "crash-reports").mkdir()
    path = folder / "crash-reports/crash-old.txt"
    path.write_text("old crash")
    os.utime(path, (100, 100))
    assert (
        capture_incident(
            tmp_path,
            folder,
            release,
            session,
            run_id=uuid4().hex,
            started_at=time.time(),
            exit_code=0,
            memory_mb=6144,
            launcher="test",
        )
        is None
    )


def test_fallback_excludes_chat_and_unrelated_output(tmp_path):
    (tmp_path / "userdata/logs").mkdir(parents=True)
    (tmp_path / "userdata/logs/test-game.log").write_text(
        "[CHAT] private chat TestException\nnormal output\n"
        "java.lang.TestException: failure\n at fixture.main(x.java:1)\n"
    )
    value = json.loads(capture(tmp_path).read_text())
    assert "fixture.main" in value["detail"]
    assert (
        "private chat" not in value["detail"] and "normal output" not in value["detail"]
    )


def test_jvm_summary_does_not_include_environment_or_command_line(tmp_path):
    folder, release, session = fixture(tmp_path)
    (folder / "hs_err_pid1.log").write_text(
        "# A fatal error has been detected\n# Problematic frame:\n# C  driver.dll\n"
        "Command Line: private-command\nEnvironment Variables:\nAWS_SECRET=private-env\n"
    )
    path = capture_incident(
        tmp_path,
        folder,
        release,
        session,
        run_id=uuid4().hex,
        started_at=0,
        exit_code=1,
        memory_mb=6144,
        launcher="test",
    )
    value = json.loads(path.read_text())
    assert value["kind"] == "jvm_crash" and "driver.dll" in value["detail"]
    assert (
        "private-command" not in value["detail"]
        and "private-env" not in value["detail"]
    )


def test_queue_retries_without_ui_and_deletes_only_acknowledged_report(
    tmp_path, monkeypatch
):
    path = capture(tmp_path)
    session = Session.deserialize(
        json.dumps(
            {
                "schema": 1,
                "origin": "http://127.0.0.1:1",
                "username": "test_player",
                "player_name": "test_player",
                "player_uuid": json.loads(path.read_text())["player"],
                "access_token": "fixture_valid_token",
                "client_token": "fixture_client_token",
            }
        )
    )
    request = Mock(side_effect=OSError("private-token-should-not-be-logged"))
    monkeypatch.setattr("omk.incidents.DraslClient.request", request)
    submit_pending(tmp_path, "http://127.0.0.1:1", session)
    assert path.exists()
    assert (
        "private-token-should-not-be-logged"
        not in (tmp_path / "userdata/logs/launcher.jsonl").read_text()
    )
    request.side_effect = None
    request.return_value = {"ok": True, "id": json.loads(path.read_text())["id"]}
    submit_pending(tmp_path, "http://127.0.0.1:1", session)
    assert not path.exists() and request.call_count == 2


@pytest.mark.parametrize(
    "updates",
    [
        {"player": "../outside"},
        {"kind": []},
        {"detail": "x" * 32769},
        {"memory_mb": True},
    ],
)
def test_report_schema_rejects_untrusted_shapes(updates):
    with pytest.raises(ValueError):
        validate_report(report(**updates))


def test_queue_expiry_and_count_are_bounded_without_touching_other_files(tmp_path):
    folder = tmp_path / "userdata/client-incidents"
    folder.mkdir(parents=True)
    now = time.time()
    for index in range(25):
        path = folder / (uuid4().hex + ".json")
        path.write_text(json.dumps(report()))
        os.utime(path, (now - index, now - index))
    expired = folder / (uuid4().hex + ".json")
    expired.write_text(json.dumps(report()))
    os.utime(expired, (now - 15 * 86400, now - 15 * 86400))
    notes = folder / "my-notes.txt"
    notes.write_text("keep")
    _prune(tmp_path, folder)
    assert len(list(folder.glob("*.json"))) == 20
    assert not expired.exists() and notes.read_text() == "keep"


def test_another_players_pending_report_is_never_sent(tmp_path, monkeypatch):
    path = capture(tmp_path)
    session = Session(
        "http://127.0.0.1:1",
        "other",
        uuid4().hex,
        "other",
        "fixture-game-token",
        "fixture-client-token",
    )
    request = Mock()
    monkeypatch.setattr("omk.incidents.DraslClient.request", request)
    submit_pending(tmp_path, "http://127.0.0.1:1", session)
    assert path.exists() and not request.called
