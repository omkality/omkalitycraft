"""Filesystem staging contract with a mocked native/geometry preflight."""

import copy

import pytest

from omk.backups.stopped_world_backup import inventory
from omk.worlds import enderutilities_reset as ender
from omk.worlds.reset import resource_reset_stage as stage
from tests.fixtures.unit.backups.ftb_restore_authority import records
from tests.fixtures.unit.worlds.enderutilities_reset_stage import bound, unpack
from tests.fixtures.unit.worlds.resource_reset_inventory import sample
from tests.fixtures.unit.worlds.resource_reset_stage import data

__all__ = ["bound", "data", "records", "sample", "unpack"]


def test_auto_stage_clears_only_reviewed_targets_in_primary_and_old_copy(bound):
    request, source, storage, target, before, primary, _ = bound
    original = unpack(primary)["Inventory"]
    old_ender = unpack(primary)["EnderItems"]
    plan = stage.execute({**request, "action": "plan"}, source, storage, target)
    result = stage.execute(
        {**request, "action": "stage", "expected": plan}, source, storage, target
    )
    assert result == stage.execute(
        {**request, "action": "verify", "expected": plan}, source, storage, target
    )
    assert not result["ready_for_start"] and not result["portal_adapters_reviewed"]
    expected = copy.deepcopy(original)
    expected.value[1][0].value["tag"].value.pop("Target")
    expected.value[1][1].value["tag"].value["Items"].value[1][1].value["tag"].value.pop(
        "Target"
    )
    expected_ender = copy.deepcopy(old_ender)
    expected_ender.value[1][0].value["tag"].value.pop("Target")
    expected_ender.value[1][1].value["tag"].value["Items"].value[1][1].value[
        "tag"
    ].value.pop("Target")
    for path in (primary, primary.with_suffix(".dat_old")):
        after = unpack(target / path.relative_to(source))
        assert after["Dimension"].value == 0 and after["Inventory"] == expected
        assert after["EnderItems"] == expected_ender
        assert unpack(path)["Inventory"] == original
        assert unpack(path)["EnderItems"] == old_ender
    assert (
        inventory(source / "world", world_name="world", path_policy="linux-server")
        == before
    )


@pytest.mark.parametrize("admission", ["missing", "v1"])
def test_adapter_admission_change_or_old_plan_cannot_write_candidate(bound, admission):
    request, source, storage, target, before, _, proof = bound
    plan = stage.execute({**request, "action": "plan"}, source, storage, target)
    proof["adapters"] = (
        {}
        if admission == "missing"
        else {
            "enderutilities-0.7.15-player-location-target-v1": {
                "artifact_sha256": ender.SHA256,
                "handled_references": 4,
            }
        }
    )
    with pytest.raises(ValueError, match="changed"):
        stage.execute(
            {**request, "action": "stage", "expected": plan}, source, storage, target
        )
    assert not list(target.iterdir())
    assert (
        inventory(source / "world", world_name="world", path_policy="linux-server")
        == before
    )


def test_manual_data_only_mode_does_not_enable_unbinding_without_preflight(bound):
    request, source, storage, target, _, primary, _ = bound
    request["position"] = [8, 100, 8]
    plan = stage.execute({**request, "action": "plan"}, source, storage, target)
    result = stage.execute(
        {**request, "action": "stage", "expected": plan}, source, storage, target
    )
    assert not result["ready_for_start"]
    assert (
        unpack(target / primary.relative_to(source))["Inventory"]
        == unpack(primary)["Inventory"]
    )
    assert (
        unpack(target / primary.relative_to(source))["EnderItems"]
        == unpack(primary)["EnderItems"]
    )
