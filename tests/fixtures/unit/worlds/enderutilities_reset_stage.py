"""Test dependencies for enderutilities reset stage."""

import copy
import gzip
import zipfile

import pytest

from launcher.nbt import read_nbt
from omk.backups.backup_store import BackupStore
from omk.backups.stopped_world_backup import inventory
from omk.worlds import enderutilities_reset as ender
from omk.worlds.reset import resource_reset_stage as stage
from tests.fixtures.unit.backups.ftb_restore_authority import records
from tests.fixtures.unit.worlds.enderutilities_reset import crystal, player, porter
from tests.fixtures.unit.worlds.resource_reset_inventory import encoded, sample
from tests.fixtures.unit.worlds.resource_reset_stage import (
    LIMITS,
    data,
)

__all__ = ["data", "records", "sample"]


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
