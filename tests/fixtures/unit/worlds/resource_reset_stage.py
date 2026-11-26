"""Test dependencies for resource reset stage."""

import zipfile
from uuid import uuid4

import pytest

from launcher.nbt import Tag
from omk.backups.backup_store import BackupPolicy, BackupStore
from omk.backups.stopped_world_backup import inventory
from omk.worlds.reset import (
    dimension_reset,
    resource_reset_inventory as audit,
    resource_reset_stage as stage,
)
from tests.fixtures.unit.backups.ftb_restore_authority import records
from tests.fixtures.unit.worlds.resource_reset_inventory import (
    encoded,
    rftools_destinations,
    rftools_registry,
    sample,
)

__all__ = ["records", "rftools_registry", "sample"]


LIMITS = BackupPolicy(32 * 1024**2, 3, 16 * 1024**2, 1)


@pytest.fixture
def data(sample, tmp_path, monkeypatch):
    server, world, entity, player, _records = sample
    (server / "server.properties").write_text("level-name=world\nlevel-seed=\n")
    (world / "DIM-18000/region").mkdir()
    (world / "DIM-18000/region/r.0.0.mca").write_bytes(b"old-resource")
    (world / "region").mkdir()
    (world / "region/r.0.0.mca").write_bytes(b"keep-main-base")
    (world / "betterquesting").mkdir()
    (world / "betterquesting/QuestProgress.json").write_bytes(
        b'{"keep":"quest-progress"}'
    )
    (world / "stats").mkdir()
    (world / "stats" / (player.stem + ".json")).write_bytes(
        b'{"stat.playOneMinute":72007,"stat.jump":9}'
    )
    entity["ForgeData"] = Tag(
        10,
        {
            "PlayerPersisted": Tag(
                10,
                {
                    "omkality_guide": Tag(
                        10,
                        {
                            "last_auto": Tag(4, 1794560000),
                            "last_help": Tag(4, 1794560001),
                        },
                    )
                },
            )
        },
    )
    encoded(player, entity)
    encoded(player.with_suffix(".dat_old"), entity)
    storage, target = tmp_path / "backup", tmp_path / "candidate"
    storage.mkdir()
    target.mkdir()
    store = BackupStore.create(storage / "store", LIMITS, path_policy="linux-server")
    files = inventory(world, world_name="world", path_policy="linux-server")
    archive = tmp_path / "fresh.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as out:
        for name in files:
            out.write(server / name, name)
    snapshot = store.publish(archive, files)
    request = {
        "schema": 1,
        "operation": uuid4().hex,
        "world": "world",
        "dimension": -18000,
        "position": [8, 100, 8],
        "snapshot": snapshot["id"],
        "world_max_bytes": 8 * 1024**2,
        "policy": vars(LIMITS),
    }
    monkeypatch.setattr(stage.sys, "platform", "linux")
    return request, server, storage, target, files


@pytest.fixture
def rftools_data(data, rftools_registry, tmp_path):
    request, server, storage, target, _old_files = data
    world = server / request["world"]
    _, _, save = rftools_registry
    save([(6200, "Лаборатория"), (6201, "Соседний мир")])
    rftools_destinations(
        world / audit.RFTOOLS_DESTINATIONS,
        (7, 6200, "Лаборатория", 7),
        (8, 6201, "Соседний мир", 7),
        (9, 6200, "Второй приёмник", 11),
    )
    for dimension in (6200, 6201):
        terrain = world / f"RFTOOLS{dimension}/region"
        terrain.mkdir(parents=True)
        (terrain / "r.0.0.mca").write_bytes(f"terrain of {dimension}".encode())
    root = world / "playerdata"
    selected = next(root.glob("*.dat"))
    player = audit.ftb.nbt(selected.read_bytes())
    player["Dimension"] = Tag(3, 6200)
    player["XpTotal"] = Tag(3, 177)
    player["Inventory"] = Tag(
        9,
        (
            10,
            [
                Tag(
                    10,
                    {
                        "id": Tag(8, "minecraft:diamond"),
                        "Count": Tag(1, 7),
                        "Slot": Tag(1, 8),
                    },
                ),
                Tag(
                    10,
                    {
                        "id": Tag(8, "rftools:advanced_charged_porter"),
                        "Count": Tag(1, 1),
                        "Slot": Tag(1, 1),
                        "Damage": Tag(2, 0),
                        "tag": Tag(
                            10,
                            {
                                "Energy": Tag(3, 650000),
                                "target": Tag(3, 9),
                                "target0": Tag(3, 9),
                                "target1": Tag(3, 8),
                                "tpTimer": Tag(3, 36),
                            },
                        ),
                    },
                ),
            ],
        ),
    )
    encoded(selected, player)
    encoded(selected.with_suffix(".dat_old"), player)
    other = root / "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb.dat"
    half = int("b" * 16, 16) - 2**64
    encoded(
        other,
        {
            **player,
            "Inventory": Tag(9, (10, player["Inventory"].value[1][:1])),
            "Dimension": Tag(3, 0),
            "UUIDMost": Tag(4, half),
            "UUIDLeast": Tag(4, half),
        },
    )
    files = inventory(world, world_name=world.name, path_policy="linux-server")
    archive = tmp_path / "rftools-current.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as output:
        for name in files:
            output.write(server / name, name)
    store = BackupStore(storage / "store", LIMITS, path_policy="linux-server")
    backup = store.publish(archive, files)
    _label, _root, rows = audit._rftools_registry(server, world.name)
    request.update(
        dimension=6200,
        position="auto",
        snapshot=backup["id"],
        reset=dimension_reset.layout(
            6200, rftools_identity=audit.rftools_identity(rows[6200])
        ),
        reroll_seed=True,
        operation=(2686033).to_bytes(8, "big").hex() + "0" * 16,
    )
    return request, server, storage, target, files, selected
