"""Test dependencies for resource reset inventory."""

import gzip
import hashlib
import json
from uuid import UUID

import pytest

from launcher.nbt import Tag, write_nbt
from omk.worlds.reset import resource_reset_inventory as audit
from omk.worlds.resource_policy import jed_dimension, resource_plan
from tests.fixtures.unit.backups.ftb_restore_authority import records

__all__ = ["records"]


def encoded(path, root):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(gzip.compress(write_nbt("", root), mtime=0))


@pytest.fixture
def sample(tmp_path, monkeypatch, records):
    server = tmp_path / "server"
    world = server / "world"
    world.mkdir(parents=True)
    (world / "level.dat").write_bytes(b"synthetic-level-marker")
    profile = json.loads(audit.PROFILE.read_bytes())
    payload = b"synthetic-jar"
    profile["artifact"]["sha256"] = hashlib.sha256(payload).hexdigest()
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(json.dumps(profile))
    monkeypatch.setattr(audit, "PROFILE", profile_path)
    (server / "mods").mkdir()
    (server / "mods" / profile["artifact"]["filename"]).write_bytes(payload)
    monkeypatch.setattr(
        audit.ftb,
        "PINS",
        {
            "ftb-library.jar": hashlib.sha256(payload).hexdigest(),
            "ftb-utilities.jar": hashlib.sha256(payload).hexdigest(),
        },
    )
    for name in audit.ftb.PINS:
        (server / "mods" / name).write_bytes(payload)
    config = server / "config"
    (config / "justenoughdimensions").mkdir(parents=True)
    jed = json.dumps(jed_dimension(resource_plan({}))).encode()
    (config / "justenoughdimensions/dimensions.json").write_bytes(jed)
    values = {
        "schema": "1",
        "dimension": "-18000",
        "identity": profile["identity"],
        "seed": "0",
        "command": "resource",
        "jed_config_sha256": hashlib.sha256(jed).hexdigest(),
        "spawn_x": "0",
        "spawn_z": "0",
        "search_radius": "64",
        "search_step": "8",
        "chunk_loads": "64",
    }
    (config / "omkalitycore-resource.properties").write_text(
        "".join(f"{k}={v}\n" for k, v in values.items())
    )
    marker = "".join(
        f"{k}={values[k]}\n" for k in ("schema", "identity", "dimension", "seed")
    )
    (world / "DIM-18000").mkdir()
    for name in ["omk-resource-world.properties", "DIM-18000/.omk-resource.properties"]:
        (world / name).write_text(marker)
    uid = UUID("a" * 32)
    half = int("a" * 16, 16) - 2**64
    entity = {
        "UUIDMost": Tag(4, half),
        "UUIDLeast": Tag(4, half),
        "Dimension": Tag(3, -18000),
        "Inventory": Tag(9, (10, [])),
        "ModData": Tag(10, {"keep": Tag(8, "opaque-state")}),
    }
    player_path = world / "playerdata" / (str(uid) + ".dat")
    encoded(player_path, entity)
    player_path.with_suffix(".astral").write_bytes(b"opaque-knowledge")
    homes = (
        records["players/owner.dat"]["Data"].value["ftbutilities"].value["Homes"].value
    )
    homes.update(
        {"resource": Tag(11, [1, 70, 2, -18000]), "main": Tag(11, [8, 100, 8])}
    )
    records["universe.dat"]["Data"] = Tag(
        10,
        {
            "ftbutilities": Tag(
                10, {"Warps": Tag(10, {"resource": Tag(11, [1, 70, 2, -18000])})}
            )
        },
    )
    for name, root in records.items():
        encoded(world / "data/ftb_lib" / name, root)
    claims = {
        "ClaimedChunks": Tag(
            10,
            {
                "-18000": Tag(9, (10, [Tag(10, {"x": Tag(3, 10), "z": Tag(3, -2)})])),
                "0": Tag(9, (10, [Tag(10, {"x": Tag(3, 0), "z": Tag(3, 0)})])),
            },
        )
    }
    encoded(world / "data/ftb_lib/teams/claimedchunks/base.dat", claims)
    return server, world, entity, player_path, records
