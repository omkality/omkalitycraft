"""Filesystem staging contract with a mocked native/geometry preflight."""

import copy
import gzip
import zipfile

import pytest

from launcher.nbt import read_nbt
from omk import (
    enderutilities_reset as ender,
    resource_reset_stage as stage,
)
from omk.backup_store import BackupStore
from omk.stopped_world_backup import inventory
from tests.unit.test_enderutilities_reset import crystal, player, porter
from tests.unit.test_resource_reset_stage import (
    LIMITS,
    data as data,  # noqa: PLC0414 -- explicit shared pytest fixture export
    encoded,
    records as records,  # noqa: PLC0414 -- transitive pytest fixture export
    sample as sample,  # noqa: PLC0414 -- transitive pytest fixture export
)


def unpack(path):
    return read_nbt(gzip.decompress(path.read_bytes()))[1]


@pytest.fixture
def bound(data, tmp_path, monkeypatch):
    request, source, storage, target, _ = data
    primary = next((source / "world/playerdata").glob("*.dat"))
    root = unpack(primary)
    root["Inventory"] = player(crystal(-18000), porter())["Inventory"]
    root["EnderItems"] = player(crystal(-18000, 26), porter(0))["Inventory"]
    encoded(primary, root)
    encoded(primary.with_suffix(".dat_old"), root)
    files = inventory(source / "world", world_name="world", path_policy="linux-server")
    archive = tmp_path / "current.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as out:
        for name in files:
            out.write(source / name, name)
    store = BackupStore(storage / "store", LIMITS, path_policy="linux-server")
    request.update(snapshot=store.publish(archive, files)["id"], position="auto")
    proof = {
        "can_stage_data": True,
        "landing": {"position": [8, 100, 8]},
        "adapters": {
            ender.ADAPTER: {"artifact_sha256": ender.SHA256, "handled_references": 8}
        },
    }
    monkeypatch.setattr(
        stage.resource_reset_preflight,
        "preflight",
        lambda *a, **k: copy.deepcopy(proof),
    )
    return request, source, storage, target, files, primary, proof


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
