from copy import deepcopy

import pytest

from omk.admin_backups import settings
from omk.estate_budget import assess, declared_limits
from omk.storage_policy import storage_plan

GIB = 1024**3


@pytest.mark.parametrize(
    "count,environment,compatible",
    [
        (1, {}, True),
        (2, {}, False),
        (2, {"OMK_BACKUP_MAX_BYTES": str(24 * GIB)}, True),
        (3, {"OMK_BACKUP_MAX_BYTES": str(16 * GIB)}, False),
    ],
)
def test_declared_per_server_caps_cannot_silently_multiply_global_budget(
    count, environment, compatible
):
    result = declared_limits(storage_plan(environment), settings(environment), count)
    assert result["compatible"] is compatible
    assert result["sum_backup_caps_bytes"] == count * settings(environment)["max_bytes"]
    assert result["existing_store_policy_read"] is False


@pytest.fixture
def report():
    def resource(name, role, category, apparent, allocated=None):
        return {
            "id": name,
            "role": role,
            "categories": {
                category: {
                    "apparent_bytes": apparent,
                    "allocated_bytes": apparent if allocated is None else allocated,
                }
            },
        }

    return {
        "resources": [
            resource("dj2", "source", "active_world", 20 * GIB),
            resource("other", "source", "active_world", 10 * GIB),
            resource("old", "source", "retained_world_generations", 4 * GIB),
            resource("backups", "store", "store", 20 * GIB),
            resource("auth", "auth", "auth", GIB),
        ],
        "filesystems": [
            {
                "resources": ["dj2", "other", "old", "backups", "auth"],
                "total_bytes": 200 * GIB,
                "available_bytes": 100 * GIB,
            }
        ],
    }


def test_totals_are_project_wide_and_unaccounted_host_space_is_explicit(report):
    report["filesystems"][0]["available_bytes"] = 140 * GIB
    result = assess(report, storage_plan({}))
    assert result["categories"]["worlds"]["charged_bytes"] == 30 * GIB
    assert result["categories"]["staging"]["charged_bytes"] == 4 * GIB
    assert result["categories"]["system"]["charged_bytes"] == 6 * GIB
    assert result["filesystems"][0]["unattributed_or_reserved_bytes"] == 5 * GIB
    assert result["observed_within_limits"]
    assert (
        not result["enforced"]
        and not result["admission_approved"]
        and not result["host_disk_complete"]
    )


def test_unattributed_host_usage_is_charged_conservatively_not_ignored(report):
    result = assess(report, storage_plan({}))
    assert result["categories"]["system"]["unattributed_charge_bytes"] == 45 * GIB
    assert result["categories"]["system"]["charged_bytes"] == 46 * GIB
    assert result["categories"]["system"]["over_budget"]
    assert not result["observed_within_limits"]


@pytest.mark.parametrize("kind", ["category", "reserve", "capacity"])
def test_excess_and_smaller_real_disk_are_flagged_without_deleting(report, kind):
    if kind == "category":
        report["resources"][1]["categories"]["active_world"]["apparent_bytes"] = (
            13 * GIB
        )
    elif kind == "reserve":
        report["filesystems"][0]["available_bytes"] = 23 * GIB
    else:
        report["filesystems"][0]["total_bytes"] = 200 * 1000**3
    before = deepcopy(report)
    result = assess(report, storage_plan({}))
    assert not result["observed_within_limits"]
    assert report == before
    if kind == "capacity":
        assert result["planned_disk_exceeds_observed_filesystem"]


def test_sparse_and_allocation_overhead_use_the_larger_cost(report):
    report["resources"][0]["categories"]["active_world"].update(
        apparent_bytes=20 * GIB, allocated_bytes=GIB
    )
    report["resources"][1]["categories"]["active_world"].update(
        apparent_bytes=GIB, allocated_bytes=3 * GIB
    )
    assert (
        assess(report, storage_plan({}))["categories"]["worlds"]["charged_bytes"]
        == 23 * GIB
    )


def test_multiple_filesystems_do_not_claim_one_global_budget_is_valid(report):
    first = report["filesystems"][0]
    first["resources"].remove("auth")
    report["filesystems"].append(
        {"resources": ["auth"], "total_bytes": 200 * GIB, "available_bytes": 100 * GIB}
    )
    value = assess(report, storage_plan({}))
    assert not value["single_filesystem_budget_evaluable"]
    assert not value["observed_within_limits"]
    assert len(value["filesystems"]) == 2


@pytest.mark.parametrize(
    "kind", ["duplicate", "missing", "foreign", "negative", "boolean"]
)
def test_corrupt_accounting_cannot_be_accepted(report, kind):
    if kind == "duplicate":
        report["filesystems"][0]["resources"].append("auth")
    elif kind == "missing":
        report["filesystems"][0]["resources"].remove("auth")
    elif kind == "foreign":
        report["filesystems"][0]["resources"].append("foreign")
    else:
        report["resources"][0]["categories"]["active_world"]["apparent_bytes"] = (
            -1 if kind == "negative" else True
        )
    with pytest.raises(ValueError):
        assess(report, storage_plan({}))
