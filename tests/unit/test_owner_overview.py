import json
from pathlib import Path

import pytest

from omk import owner_overview as view
from omk.admin import _write_private
from omk.cli import main
from tests.unit.test_operator_commands import config


def record(settings, identity="a", **changes):
    value = {
        "schema": 1,
        "operation": identity * 32,
        "server": "dj2",
        "stage": "incomplete",
        "source": {"private": "never-copy-this"},
    }
    value.update(changes)
    path = settings.private / "backups" / (identity * 32 + ".json")
    _write_private(path, settings.private, value)
    return path


def test_real_cli_is_read_only_bounded_and_redacted(tmp_path, capsys):
    settings, path = config(tmp_path)
    record(settings)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert main(["admin", "--config", str(path), "overview"]) == 0
    output = capsys.readouterr().out
    result = view.Overview.model_validate_json(output)
    assert result.ok and result.server_ids == ["dj2"]
    assert result.operations[0].phase == "incomplete"
    assert result.operations[0].terminal is False
    assert "never-copy-this" not in output and str(tmp_path) not in output
    assert before == {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}


def test_empty_is_an_empty_inventory_not_a_healthy_server(tmp_path):
    settings, _ = config(tmp_path)
    result = view.sample(settings)
    assert result["ok"] and result["operations"] == []
    assert result["metrics_status"] == "disabled"
    assert all(row["value"] is None for row in result["metrics"])


@pytest.mark.parametrize(
    "change",
    [
        {"stage": "secret-invalid-phase"},
        {"server": "removed"},
        {"server": "\x1b[2J"},
        {"operation": "b" * 32},
    ],
)
def test_bad_or_unbound_records_are_counted_not_displayed(tmp_path, change):
    settings, _ = config(tmp_path)
    record(settings, **change)
    result = view.sample(settings)
    assert result["skipped"] == 1 and result["operations"] == []


def test_corrupt_record_does_not_hide_good_records(tmp_path):
    settings, _ = config(tmp_path)
    record(settings)
    record(settings, "b").write_bytes(b"bad-private-json")
    result = view.sample(settings)
    assert result["skipped"] == 1 and len(result["operations"]) == 1


def test_limit_is_visible_and_scan_does_not_run_services(tmp_path, monkeypatch):
    settings, _ = config(tmp_path)
    record(settings)
    record(settings, "b")
    monkeypatch.setattr(view, "MAX_OPERATIONS", 1)
    result = view.sample(settings)
    assert len(result["operations"]) == 1 and result["truncated"]
    monkeypatch.setattr(view, "MAX_CANDIDATES", 1)
    assert view.sample(settings)["truncated"]


def test_missing_config_is_versioned_without_private_details(tmp_path, capsys):
    assert main(["admin", "--config", str(tmp_path / "secret"), "overview"]) == 1
    output = capsys.readouterr().out
    assert view.Overview.model_validate_json(output).error == "invalid_configuration"
    assert str(tmp_path) not in output


def test_result_v1_does_not_silently_change_contract(tmp_path, capsys):
    assert (
        main(
            [
                "admin",
                "--config",
                str(tmp_path / "missing"),
                "--result-version",
                "1",
                "overview",
            ]
        )
        == 1
    )
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "unsupported_action"


def test_schema_is_current():
    path = Path(__file__).parents[2] / "docs/contracts/owner-overview-v1.schema.json"
    assert (
        json.loads(path.read_text(encoding="utf-8"))
        == view.Overview.model_json_schema()
    )
