import json

import pytest

from omk.cli import main
from omk.storage_policy import storage_plan


def test_default_budget_leaves_free_reserve_and_space_for_new_backup():
    result = storage_plan({})
    assert result["ok"] and result["enforced"] is False
    budgets = result["budgets_gib"]
    assert sum(budgets.values()) + result["unallocated_gib"] == result["disk_gib"]
    assert budgets["staging"] >= budgets["worlds"] and budgets["reserve"] == 24


def test_environment_overrides_work_without_writing_any_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = storage_plan(
        {"OMK_STORAGE_DISK_GIB": "240", "OMK_STORAGE_BACKUPS_GIB": "60"}
    )
    assert result["ok"] and result["ftb_backups_proposal"]["max_total_size"] == "60 GB"
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "raw", ["", "-2", "0", "1.5", "NaN", "inf", "９", "secret-lab-value", "9" * 5000]
)
def test_bad_or_excessive_values_are_rejected_without_echoing_input(raw):
    result = storage_plan({"OMK_STORAGE_BACKUPS_GIB": raw})
    assert not result["ok"] and "OMK_STORAGE_BACKUPS_GIB" in result["error"]
    assert "secret-lab-value" not in json.dumps(result)


def test_inconsistent_budget_and_insufficient_staging_are_rejected():
    assert not storage_plan({"OMK_STORAGE_DISK_GIB": "100"})["ok"]
    assert not storage_plan({"OMK_STORAGE_STAGING_GIB": "16"})["ok"]
    assert not storage_plan({"OMK_STORAGE_BACKUP_COUNT": "32001"})["ok"]


def test_owner_cli_reports_invalid_policy_with_failure_exit_code(monkeypatch, capsys):
    monkeypatch.setenv("OMK_STORAGE_BACKUP_COUNT", "1")
    assert main(["storage", "plan"]) == 1
    result = json.loads(capsys.readouterr().out)
    assert not result["ok"] and "OMK_STORAGE_BACKUP_COUNT" in result["error"]
