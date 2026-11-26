"""Fixtures for incident staging with a stopped Forge save."""

import hashlib
import shutil
import struct
import zipfile
import zlib
from uuid import uuid4

import pytest

from omk.backups.backup_store import BackupPolicy, BackupStore
from omk.backups.stopped_world_backup import inventory
from omk.shared.nbt import Tag, write_nbt
from omk.worlds import (
    incident_objects as objects,
    incident_recovery as stage,
)
from tests.fixtures.unit.worlds.resource_reset_inventory import encoded, records, sample

__all__ = ["records", "sample"]

LIMITS = BackupPolicy(32 * 1024**2, 3, 16 * 1024**2, 1)
POSITION = [-89, 100, -86]
CHUNK = [-6, -6]
DROP = "00000000-0000-0011-0000-000000000022"


def compounds(*rows):
    return Tag(9, (10, [Tag(10, row) for row in rows]))


def vector(*values):
    return Tag(9, (6, [Tag(6, float(value)) for value in values]))


def stack(slot, item="minecraft:diamond"):
    return {
        "Slot": Tag(1, slot),
        "id": Tag(8, item),
        "Count": Tag(3, 200) if slot == 4 else Tag(1, 7),
        "Damage": Tag(2, 0),
        "tag": Tag(10, {"Data": Tag(8, "☃\0")}),
        "ForgeCaps": Tag(10, {"fixture": Tag(11, [1, 2, 3])}),
    }


def section(chest=False):
    blocks = bytearray(4096)
    blocks[3 * 256 : 4 * 256] = b"\x01" * 256
    add, add2 = bytearray(2048), bytearray(2048)
    blocks[1276] = 0x3F
    add[638], add2[638] = 1, 5
    if chest:
        x, y, z = POSITION
        blocks[(y & 15) * 256 + (z & 15) * 16 + (x & 15)] = 54
    return {
        "Y": Tag(1, 6),
        "Blocks": Tag(7, bytes(blocks)),
        "Data": Tag(7, bytes(2048)),
        "Add": Tag(7, bytes(add)),
        "Add2": Tag(7, bytes(add2)),
    }


def chunk(x, z, *, chest=False):
    tile = {
        **dict(zip("xyz", (Tag(3, v) for v in POSITION), strict=True)),
        "id": Tag(8, "minecraft:chest"),
        "Items": compounds(stack(4), stack(5, "minecraft:apple")),
    }
    drop = {
        "id": Tag(8, "minecraft:item"),
        "UUIDMost": Tag(4, 17),
        "UUIDLeast": Tag(4, 34),
        "Pos": vector(-92.5, 100, -92.5),
        "Item": Tag(10, stack(0, "minecraft:iron_ingot")),
    }
    return {
        "xPos": Tag(3, x),
        "zPos": Tag(3, z),
        "TerrainPopulated": Tag(1, 1),
        "LightPopulated": Tag(1, 1),
        "Sections": compounds(section(chest)),
        "TileEntities": compounds(*([tile] if chest else [])),
        "Entities": compounds(*([drop] if chest else [])),
    }


def region(path, *chunks):
    path.parent.mkdir(parents=True)
    header, sectors = bytearray(8192), []
    for offset, chunk in enumerate(chunks, start=2):
        x, z = chunk["xPos"].value, chunk["zPos"].value
        index = x % 32 + 32 * (z % 32)
        struct.pack_into(">I", header, index * 4, (offset << 8) | 1)
        data = zlib.compress(
            write_nbt("", {"DataVersion": Tag(3, 1343), "Level": Tag(10, chunk)})
        )
        sectors.append((struct.pack(">IB", len(data) + 1, 2) + data).ljust(4096, b"\0"))
    path.write_bytes(header + b"".join(sectors))


@pytest.fixture
def incident(tmp_path, sample, monkeypatch):
    source, world, actor, player_path, ftb = sample
    actor.update(
        DataVersion=Tag(3, 1343),
        Health=Tag(5, 20),
        XpTotal=Tag(3, 177),
        Dimension=Tag(3, -1),
        Pos=vector(-87.5, 100, -87.5),
        Inventory=compounds(stack(1), stack(2)),
    )
    encoded(player_path, actor)
    old_ftb = ftb["players/owner.dat"]
    old_ftb["UUID"] = Tag(8, player_path.stem)
    old_ftb["Data"].value["ftbutilities"].value["teleportTracker"] = Tag(
        10, {"0": Tag(10, {"dimension": Tag(3, -1)})}
    )
    encoded(world / "data/ftb_lib/players/owner.dat", old_ftb)
    registry = compounds(
        *(
            {"V": Tag(3, key), "K": Tag(8, name)}
            for key, name in {
                0: "minecraft:air",
                1: "minecraft:stone",
                54: "minecraft:chest",
                0x513F: "fixture:extended",
            }.items()
        )
    )
    encoded(
        world / "level.dat",
        {
            "Data": Tag(
                10,
                {
                    "DataVersion": Tag(3, 1343),
                    "BorderCenterX": Tag(6, 0.0),
                    "BorderCenterZ": Tag(6, 0.0),
                    "BorderSize": Tag(6, 1024.0),
                    "SpawnX": Tag(3, 0),
                    "SpawnY": Tag(3, 100),
                    "SpawnZ": Tag(3, 0),
                },
            ),
            "FML": Tag(
                10,
                {
                    "Registries": Tag(
                        10, {"minecraft:blocks": Tag(10, {"ids": registry})}
                    )
                },
            ),
        },
    )
    region(world / "region/r.0.0.mca", chunk(0, 0))
    region(world / "DIM-1/region/r.-1.-1.mca", chunk(*CHUNK, chest=True), chunk(-5, -6))
    ne = source / "mods/neid-test.jar"
    ne.write_bytes(b"pinned Anvil fixture")
    monkeypatch.setattr(
        objects, "NEID", (ne.name, hashlib.sha256(ne.read_bytes()).hexdigest())
    )
    monkeypatch.setattr(stage.raw.sys, "platform", "linux")
    (source / "server.properties").write_text("level-name=world\nview-distance=8\n")
    backup, target = [tmp_path / name for name in ("backup", "target")]

    backup.mkdir()
    shutil.copytree(source, target, ignore=shutil.ignore_patterns(world.name))
    store = BackupStore.create(backup / "store", LIMITS, path_policy="linux-server")
    files = inventory(world, world_name=world.name, path_policy="linux-server")
    archive = tmp_path / "checkpoint.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as out:
        for name in files:
            out.write(source / name, name)
    snapshot = store.publish(archive, files)
    request = {
        "schema": 1,
        "operation": uuid4().hex,
        "world": world.name,
        "snapshot": snapshot["id"],
        "policy": vars(LIMITS),
        "world_max_bytes": 8 * 1024**2,
        "incident": {
            "rescue": {
                "player": player_path.stem,
                "danger": [-1, -88, -88],
                "landing": [8, 100, 8],
            }
        },
    }
    return request, (backup, target, source), player_path


def selection(kind, player):
    if kind == "inventory":
        details = {"player": player, "slot": 1, "id": "minecraft:diamond"}
    elif kind == "dropped":
        details = {
            "dimension": -1,
            "chunk": CHUNK,
            "entity": DROP,
            "id": "minecraft:iron_ingot",
        }
    else:
        details = {"dimension": -1, "position": POSITION, "id": "minecraft:chest"}
        if kind == "chest":
            details.update(slot=4, id="minecraft:diamond")
    return {"kind": kind, **details}
