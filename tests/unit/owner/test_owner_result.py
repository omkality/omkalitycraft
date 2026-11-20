import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from omk.backups.backup_store import BackupStore
from omk.backups.stopped_world_backup import LAB_POLICY
from omk.cli import main
from omk.owner import (
    admin_backups as backups,
    owner_result as protocol,
)
from omk.owner.admin import AdminError, _write_private
from tests.fixtures.unit.backups import cold_backups as backup_cases
from tests.fixtures.unit.owner.operator_commands import config

backup_fixture = backup_cases.fixture
OPERATION = "a" * 32
SECRET = "synthetic-private-value-not-for-output"


def invoke(path, capsys, *action, versioned=True):
    prefix = ["admin", "--config", str(path)]
    if versioned:
        prefix += ["--result-version", "1"]
    exit_code = main([*prefix, *action])
    output = capsys.readouterr()
    value = json.loads(output.out)
    if versioned:
        assert (
            protocol.OwnerResult.model_validate_json(output.out).model_dump(mode="json")
            == value
        )
    return exit_code, value, output


def test_published_schema_matches_the_versioned_models():
    path = Path(__file__).parents[3] / "docs/contracts/owner-result-v1.schema.json"
    assert json.loads(path.read_text(encoding="utf-8")) == protocol.json_schema()
    assert len(protocol.SUPPORTED) == 15


@pytest.mark.parametrize("action", sorted(protocol.SUPPORTED))
def test_each_versioned_action_dispatches_existing_service_once(
    tmp_path, monkeypatch, capsys, action
):
    _, path = config(tmp_path)
    kind, verb = action.split(".")
    args = [kind, verb]
    if verb == "plan":
        args += ["--server", "dj2"]
        if kind == "restores":
            args += ["--snapshot", "synthetic-snapshot"]
    else:
        args += ["--operation", OPERATION]
    if action == "maintenance.start":
        args += ["--backup-operation", "b" * 32]
    phase = {
        "plan": "planned",
        "run": "complete",
        "finish": "complete",
        "cancel": "cancelled",
        "stop": "stopped",
        "start": "complete",
        "reconcile": "complete",
        "apply": "staged",
        "verify": "staged",
        "status": "planned",
    }[verb]
    service = Mock(
        return_value={
            "ok": True,
            "operation": OPERATION,
            "server": "dj2",
            "stage": phase,
        }
    )
    module, function = {
        "backups": ("omk.owner.admin_backups", "run_backups"),
        "maintenance": ("omk.owner.admin_maintenance", "run_maintenance"),
        "restores": ("omk.owner.admin_restores", "run_restores"),
    }[kind]
    monkeypatch.setattr(f"{module}.{function}", service)
    code, reply, _ = invoke(path, capsys, *args)
    assert code == 0 and reply["action"] == action
    assert reply["operation"]["id"] == OPERATION
    assert reply["operation"]["phase"] == phase
    service.assert_called_once()


@pytest.mark.parametrize(
    "value,expected",
    [
        (None, "invalid_service_result"),
        ([], "invalid_service_result"),
        ({"ok": False, "error": SECRET}, "operation_failed"),
    ],
)
def test_non_success_service_result_is_bounded_and_not_echoed(
    tmp_path, monkeypatch, capsys, value, expected
):
    _, path = config(tmp_path)
    service = Mock(return_value=value)
    monkeypatch.setattr(backups, "run_backups", service)
    code, reply, output = invoke(
        path, capsys, "backups", "run", "--operation", OPERATION
    )
    assert code == 1 and reply["error"]["code"] == expected
    assert SECRET not in output.out + output.err
    service.assert_called_once()


def test_published_examples_decode_with_all_semantic_checks():
    path = Path(__file__).parents[3] / "docs/contracts/owner-result-v1.examples.json"
    examples = json.loads(path.read_text(encoding="utf-8"))
    assert len(examples) == 7
    for value in examples.values():
        assert (
            protocol.OwnerResult.model_validate(value).model_dump(mode="json") == value
        )


def test_real_cli_process_reads_journal_as_single_versioned_json_without_docker(
    tmp_path,
):
    cfg, path = config(tmp_path)
    journal = backups.journal(cfg, OPERATION)
    _write_private(
        journal,
        cfg.private,
        {
            "schema": 1,
            "operation": OPERATION,
            "server": "dj2",
            "stage": "incomplete",
            "failure_reason": SECRET,
        },
    )
    before = journal.read_bytes()
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "omk",
            "admin",
            "--config",
            str(path),
            "--result-version",
            "1",
            "backups",
            "status",
            "--operation",
            OPERATION,
        ],
        cwd=Path(__file__).parents[3],
        env={**os.environ, "PYTHONUTF8": "1"},
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=15,
        check=False,
    )
    assert result.returncode == 0
    value = protocol.OwnerResult.model_validate_json(result.stdout)
    assert value.operation.phase == "incomplete" and value.operation.terminal is False
    assert SECRET not in result.stdout + result.stderr
    assert journal.read_bytes() == before


@pytest.mark.parametrize("kind", ["backups", "maintenance", "restores"])
def test_operation_phase_and_terminal_status_for_every_existing_phase(kind):
    for phase in protocol.PHASES[kind]:
        action = f"{kind}.status"
        value = protocol.project(
            action,
            SimpleNamespace(operation=OPERATION),
            {
                "ok": True,
                "operation": OPERATION,
                "server": "dj2",
                "stage": phase,
                "target": {"password": SECRET},
                "api_token": SECRET,
            },
        )
        assert value["ok"] is True and value["status"] == "succeeded"
        assert value["operation"]["phase"] == phase
        assert value["operation"]["terminal"] == (phase in protocol.TERMINAL[kind])
        assert SECRET not in json.dumps(value)
        assert "ready_for_players" not in value


@pytest.mark.parametrize(
    "change",
    [
        "missing-version",
        "future-version",
        "boolean-version",
        "unknown-field",
        "wrong-phase",
        "wrong-terminal",
        "wrong-outcome",
    ],
)
def test_decoder_refuses_legacy_future_or_inconsistent_results(change):
    value = protocol.project(
        "backups.status",
        SimpleNamespace(operation=OPERATION),
        {
            "ok": True,
            "operation": OPERATION,
            "server": "dj2",
            "stage": "planned",
        },
    )
    if change == "missing-version":
        del value["schema_version"]
    elif change == "future-version":
        value["schema_version"] = 2
    elif change == "boolean-version":
        value["schema_version"] = True
    elif change == "unknown-field":
        value["unversioned_extension"] = True
    elif change == "wrong-phase":
        value["operation"]["phase"] = "staged"
    elif change == "wrong-terminal":
        value["operation"]["terminal"] = True
    else:
        value["ok"] = False
    with pytest.raises(ValidationError):
        protocol.OwnerResult.model_validate_json(json.dumps(value))


@pytest.mark.parametrize(
    "field,value",
    [("operation", "b" * 32), ("server", "other"), ("stage", SECRET), ("ok", 1)],
)
def test_malformed_or_mismatched_service_reply_is_unknown_and_not_repeated(
    tmp_path, monkeypatch, capsys, field, value
):
    _, path = config(tmp_path)
    result = {"ok": True, "operation": OPERATION, "server": "dj2", "stage": "planned"}
    result[field] = value
    service = Mock(return_value=result)
    monkeypatch.setattr(backups, "run_backups", service)
    code, reply, output = (
        invoke(path, capsys, "backups", "plan", "--server", "dj2")
        if field == "server"
        else invoke(path, capsys, "backups", "run", "--operation", OPERATION)
    )
    assert code == 1 and reply["status"] == "unknown"
    assert reply["error"]["code"] == "invalid_service_result"
    assert reply["error"]["effect"] == "unknown"
    assert reply["error"]["next_step"] == "inspect_operation"
    assert SECRET not in output.out + output.err
    service.assert_called_once()


@pytest.mark.parametrize(
    "error,expected,effect",
    [
        (backups.OwnerBusy(SECRET), "owner_busy", "none"),
        (AdminError(SECRET), "operation_rejected", "unknown"),
        (TimeoutError(SECRET), "io_failure", "unknown"),
        (RuntimeError(SECRET), "operation_failed", "unknown"),
    ],
)
def test_stable_error_codes_do_not_parse_or_echo_exception_messages(
    tmp_path, monkeypatch, capsys, error, expected, effect
):
    _, path = config(tmp_path)
    service = Mock(side_effect=error)
    monkeypatch.setattr(backups, "run_backups", service)
    code, reply, output = invoke(
        path, capsys, "backups", "run", "--operation", OPERATION
    )
    assert code == 1 and reply["error"]["code"] == expected
    assert reply["error"]["effect"] == effect
    assert (
        reply["operation"]["phase"] is None and reply["operation"]["terminal"] is None
    )
    assert SECRET not in output.out + output.err
    service.assert_called_once()


def test_missing_configuration_is_structured_and_never_enters_service(
    tmp_path, monkeypatch, capsys
):
    service = Mock(side_effect=AssertionError("must not enter operation"))
    monkeypatch.setattr(backups, "run_backups", service)
    code, reply, _ = invoke(
        tmp_path / ".omk-admin/operator.toml",
        capsys,
        "backups",
        "status",
        "--operation",
        OPERATION,
    )
    assert code == 1 and reply["error"]["code"] == "invalid_configuration"
    assert reply["error"]["effect"] == "none"
    service.assert_not_called()


def test_unsupported_action_cannot_prompt_or_execute_as_legacy_fallback(
    tmp_path, monkeypatch, capsys
):
    load = Mock(side_effect=AssertionError("must not read private config"))
    prompt = Mock(side_effect=AssertionError("must not prompt"))
    monkeypatch.setattr("omk.owner.admin.load_operator_config", load)
    monkeypatch.setattr("omk.owner.admin.getpass.getpass", prompt)
    code, reply, _ = invoke(
        tmp_path / ".omk-admin/operator.toml", capsys, "login", "--username", "admin"
    )
    assert code == 1 and reply["error"]["code"] == "unsupported_action"
    assert reply["error"]["effect"] == "none"
    load.assert_not_called()
    prompt.assert_not_called()


def test_unknown_version_fails_argument_parsing_before_dispatch(
    tmp_path, monkeypatch, capsys
):
    dispatch = Mock(side_effect=AssertionError("must not dispatch"))
    monkeypatch.setattr("omk.owner.admin._execute_admin", dispatch)
    with pytest.raises(SystemExit) as error:
        main(
            [
                "admin",
                "--config",
                str(tmp_path),
                "--result-version",
                "2",
                "backups",
                "status",
                "--operation",
                OPERATION,
            ]
        )
    assert error.value.code == 2
    assert capsys.readouterr().out == ""
    dispatch.assert_not_called()


def test_status_projects_private_record_without_copying_it(
    tmp_path, monkeypatch, capsys
):
    cfg, path = config(tmp_path)
    record = {
        "schema": 1,
        "operation": OPERATION,
        "server": "dj2",
        "stage": "incomplete",
        "target": {"password": SECRET},
    }
    # Use the real status reader, injecting only a validated record for this projection control.
    read = Mock(return_value=record)
    monkeypatch.setattr(backups, "read_record", read)
    before = dict(record)
    code, reply, output = invoke(
        path, capsys, "backups", "status", "--operation", OPERATION
    )
    assert code == 0 and reply["operation"]["phase"] == "incomplete"
    assert reply["operation"]["terminal"] is False
    assert SECRET not in output.out + output.err
    assert record == before
    assert '"operation": "backups:status"' in (cfg.private / "audit.jsonl").read_text()


def test_real_backup_publication_lost_reply_status_and_finish_keep_one_snapshot(
    backup_fixture, tmp_path, monkeypatch, capsys
):
    cfg, path, root, storage, _ = backup_cases.controller(
        backup_fixture, tmp_path, monkeypatch
    )
    source_before = {
        str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()
    }
    code, planned, _ = invoke(path, capsys, "backups", "plan", "--server", "dj2")
    assert code == 0 and planned["operation"]["phase"] == "planned"
    identity = planned["operation"]["id"]
    save = backups.save

    def lose_ack(config, record, stage):
        if stage == "published":
            raise OSError(SECRET)
        save(config, record, stage)

    monkeypatch.setattr(backups, "save", lose_ack)
    code, failed, output = invoke(
        path, capsys, "backups", "run", "--operation", identity
    )
    assert code == 1 and failed["error"]["effect"] == "unknown"
    assert SECRET not in output.out + output.err
    code, status, _ = invoke(path, capsys, "backups", "status", "--operation", identity)
    assert code == 0 and status["operation"]["phase"] == "publishing"
    assert status["operation"]["terminal"] is False
    monkeypatch.setattr(backups, "save", save)
    code, finished, _ = invoke(
        path, capsys, "backups", "finish", "--operation", identity
    )
    assert code == 0 and finished["operation"]["phase"] == "complete"
    assert finished["operation"]["terminal"] is True
    for _ in range(2):
        assert (
            invoke(path, capsys, "backups", "status", "--operation", identity)[1]
            == invoke(path, capsys, "backups", "status", "--operation", identity)[1]
        )
    assert (
        len(
            BackupStore(
                storage / "store", LAB_POLICY, path_policy="linux-server"
            ).inspect()
        )
        == 1
    )
    assert {
        str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()
    } == source_before
    assert backups.read_record(cfg, identity)["stage"] == "complete"


def test_legacy_result_and_errors_keep_the_existing_shape(
    tmp_path, monkeypatch, capsys
):
    _, path = config(tmp_path)
    native = {
        "ok": True,
        "operation": OPERATION,
        "stage": "complete",
        "snapshot": {"sequence": 7},
    }
    service = Mock(return_value=native)
    monkeypatch.setattr(backups, "run_backups", service)
    assert (
        invoke(
            path, capsys, "backups", "run", "--operation", OPERATION, versioned=False
        )[1]
        == native
    )
    service.side_effect = AdminError("fixture business refusal")
    assert invoke(
        path, capsys, "backups", "run", "--operation", OPERATION, versioned=False
    )[1] == {
        "ok": False,
        "error": "fixture business refusal",
        "error_type": "AdminError",
    }
