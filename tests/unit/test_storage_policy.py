import json
from pathlib import Path

import pytest

from omk import journal_history, nightly_cycle, project_export, restic_transport
from omk.cli import main
from omk.storage_policy import storage_plan, storage_report


def test_default_budget_leaves_free_reserve_and_space_for_new_backup():
    result = storage_report({})
    assert result["ok"] and result["enforced"] is False
    assert result["budgets_gib"] == {
        "system": 16,
        "worlds": 32,
        "backups": 48,
        "logs": 4,
        "content": 24,
        "staging": 40,
        "reserve": 24,
    }
    assert sum(result["budgets_gib"].values()) + result["unallocated_gib"] == 200
    assert result["unallocated_gib"] == 12
    assert "ftb_backups_proposal" not in result
    assert "ignored_environment" not in result


def test_internal_plan_keeps_the_full_frozen_schema1_contract():
    path = Path(__file__).parents[1] / "fixtures/storage-plan-schema1.json"
    assert storage_plan({}) == json.loads(path.read_bytes())


def test_environment_overrides_work_without_writing_any_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = storage_report(
        {"OMK_STORAGE_DISK_GIB": "240", "OMK_STORAGE_BACKUPS_GIB": "60"}
    )
    assert result["ok"] and result["budgets_gib"]["backups"] == 60
    assert "ftb_backups_proposal" not in result
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "raw", ["", "-2", "0", "1.5", "NaN", "inf", "９", "secret-lab-value", "9" * 5000]
)
def test_bad_or_excessive_values_are_rejected_without_echoing_input(raw):
    result = storage_report({"OMK_STORAGE_BACKUPS_GIB": raw})
    assert not result["ok"] and "OMK_STORAGE_BACKUPS_GIB" in result["error"]
    assert "secret-lab-value" not in json.dumps(result)


def test_inconsistent_budget_and_insufficient_staging_are_rejected():
    assert not storage_report({"OMK_STORAGE_DISK_GIB": "100"})["ok"]
    assert not storage_report({"OMK_STORAGE_STAGING_GIB": "16"})["ok"]
    assert not storage_plan({"OMK_STORAGE_BACKUP_COUNT": "32001"})["ok"]


def test_owner_cli_reports_invalid_budget_with_failure_exit_code(monkeypatch, capsys):
    monkeypatch.setenv("OMK_STORAGE_BACKUPS_GIB", "0")
    assert main(["storage", "plan"]) == 1
    result = json.loads(capsys.readouterr().out)
    assert not result["ok"] and "OMK_STORAGE_BACKUPS_GIB" in result["error"]


@pytest.mark.parametrize(
    "key", ["OMK_STORAGE_BACKUP_COUNT", "OMK_STORAGE_BACKUP_INTERVAL_HOURS"]
)
@pytest.mark.parametrize("value", ["12", "2", "0", "", "private-marker", None, True])
def test_legacy_report_inputs_are_named_without_reading_or_applying_values(key, value):
    assert storage_report({key: value}) == {
        **storage_report({}),
        "ignored_environment": [key],
    }


def test_both_ignored_names_are_reported_without_echoing_either_value():
    result = storage_report(
        {
            "OMK_STORAGE_BACKUP_COUNT": "private-count-marker",
            "OMK_STORAGE_BACKUP_INTERVAL_HOURS": "private-interval-marker",
        }
    )
    assert result["ok"]
    assert result["ignored_environment"] == [
        "OMK_STORAGE_BACKUP_COUNT",
        "OMK_STORAGE_BACKUP_INTERVAL_HOURS",
    ]
    assert "private-" not in json.dumps(result)


def test_managed_backup_settings_remain_separate_from_project_budget():
    assert storage_report({"OMK_BACKUP_MAX_COUNT": "4"}) == storage_report({})


@pytest.mark.parametrize(
    "reader",
    [
        pytest.param(journal_history.policy, id="journal"),
        pytest.param(lambda env: nightly_cycle.policy(env)[0], id="one-shot-cycle"),
        pytest.param(project_export.policy, id="export"),
        pytest.param(restic_transport.policy, id="offsite"),
    ],
)
def test_internal_capacity_readers_keep_accepting_existing_legacy_environment(reader):
    assert reader(
        {"OMK_STORAGE_BACKUP_COUNT": "12", "OMK_STORAGE_BACKUP_INTERVAL_HOURS": "2"}
    ) == reader({})


def test_custom_legacy_snapshot_is_preserved_without_rebinding_managed_caps():
    env = {"OMK_STORAGE_BACKUP_COUNT": "7", "OMK_STORAGE_BACKUP_INTERVAL_HOURS": "4"}
    settings, effective = nightly_cycle.policy(env)
    assert settings["project"]["ftb_backups_proposal"] == {
        "backup_timer": 4,
        "backups_to_keep": 7,
        "max_total_size": "48 GB",
    }
    assert settings["backup"]["max_count"] == 12
    assert effective["OMK_STORAGE_BACKUP_COUNT"] == "7"
    assert storage_report(env)["ignored_environment"] == list(env)
