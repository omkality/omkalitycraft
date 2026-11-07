import copy
import gzip
import hashlib
import json
from uuid import UUID

import pytest

from launcher.nbt import Tag, write_nbt
from omk import resource_reset_inventory as audit
from omk.resource_policy import jed_dimension, resource_plan
from omk.stopped_world_backup import inventory
from tests.unit.test_ftb_restore_authority import (
    records as records,  # noqa: PLC0414 -- explicit shared pytest fixture export
)


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


def inspect(sample):
    return audit.inspect_resource(
        sample[0], "world", -18000, world_max_bytes=8 * 1024**2
    )


def test_native_shaped_references_are_readonly_and_not_an_apply_plan(sample):
    before = inventory(sample[1], world_name="world", path_policy="linux-server")
    result = inspect(sample)
    assert result["references"] == {
        "primary_player_records": 1,
        "primary_positions_in_resource": 1,
        "backup_positions_in_resource": 0,
        "player_spawn_references": 0,
        "opaque_player_files": 1,
        "mounted_player_records": 0,
        "ftb_homes": 1,
        "ftb_warps": 1,
        "ftb_legacy_back_death": 0,
        "resource_claimed_chunks": 1,
        "other_claimed_chunks": 1,
        "jed_player_dimensions": 0,
    }
    assert all(
        result[k] is False
        for k in ("world_changes", "backup_verified", "reset_plan", "can_apply")
    )
    assert inspect(sample) == result
    assert (
        inventory(sample[1], world_name="world", path_policy="linux-server") == before
    )


@pytest.mark.parametrize("dimension", [0, -1, 1, -9, -9999, -32001, True, "-18000"])
def test_reserved_or_invalid_dimension_never_becomes_a_reset_candidate(
    sample, dimension
):
    with pytest.raises(ValueError, match="allowlisted"):
        audit.inspect_resource(
            sample[0], "world", dimension, world_max_bytes=8 * 1024**2
        )


def test_other_negative_id_is_not_an_alias_for_the_configured_resource(sample):
    with pytest.raises(ValueError, match="identity"):
        audit.inspect_resource(sample[0], "world", -18001, world_max_bytes=8 * 1024**2)


def test_backup_player_beds_mount_and_legacy_ftb_jed_references_are_reported(sample):
    _server, world, entity, path, records = sample
    encoded(path.with_suffix(".dat_old"), entity)
    entity = copy.deepcopy(entity)
    entity.update(
        SpawnDimension=Tag(3, -18000),
        Spawns=Tag(
            9, (10, [Tag(10, {"Dim": Tag(3, -18000)}), Tag(10, {"Dim": Tag(3, 0)})])
        ),
        RootVehicle=Tag(10, {"opaque": Tag(1, 1)}),
    )
    encoded(path, entity)
    utilities = records["players/owner.dat"]["Data"].value["ftbutilities"].value
    utilities.update(
        LastDeath=Tag(11, [1, 2, 3, -18000]),
        teleportTracker=Tag(10, {"0": Tag(10, {"dimension": Tag(3, -18000)})}),
    )
    encoded(world / "data/ftb_lib/players/owner.dat", records["players/owner.dat"])
    encoded(
        world / "data/justenoughdimensions/data_tracker.dat",
        {
            "PlayerData": Tag(
                9,
                (
                    10,
                    [
                        Tag(10, {"Dimension": Tag(3, -18000)}),
                        Tag(10, {"Dimension": Tag(3, 0)}),
                    ],
                ),
            )
        },
    )
    refs = inspect(sample)["references"]
    assert refs["backup_positions_in_resource"] == 1
    assert refs["player_spawn_references"] == 2 and refs["mounted_player_records"] == 1
    assert refs["ftb_legacy_back_death"] == 2 and refs["jed_player_dimensions"] == 1


@pytest.mark.parametrize(
    "change",
    [
        "marker",
        "jed",
        "runtime",
        "duplicate-property",
        "bad-nbt",
        "uuid",
        "unknown-player",
        "duplicate-claim",
        "claim-overlap",
    ],
)
def test_unreviewed_or_inconsistent_source_is_refused_before_any_write(sample, change):
    server, world, entity, path, _records = sample
    if change == "marker":
        (world / "omk-resource-world.properties").write_text("schema=1\n")
    elif change == "jed":
        (server / "config/justenoughdimensions/dimensions.json").write_text("{}")
    elif change == "runtime":
        (server / "mods/ftb-library.jar").write_bytes(b"different")
    elif change == "duplicate-property":
        p = server / "config/omkalitycore-resource.properties"
        p.write_text(p.read_text() + "dimension=-18000\n")
    elif change == "bad-nbt":
        path.write_bytes(b"broken")
    elif change == "uuid":
        entity["UUIDMost"] = Tag(4, 0)
        encoded(path, entity)
    elif change == "unknown-player":
        path.with_name("ambiguous.dat").write_bytes(path.read_bytes())
    else:
        original = world / "data/ftb_lib/teams/claimedchunks/base.dat"
        if change == "claim-overlap":
            original.with_name("other.dat").write_bytes(original.read_bytes())
        else:
            root = audit.ftb.nbt(original.read_bytes())
            entries = root["ClaimedChunks"].value["-18000"].value[1]
            entries.append(copy.deepcopy(entries[0]))
            encoded(original, root)
    before = inventory(world, world_name="world", path_policy="linux-server")
    with pytest.raises(ValueError):
        inspect(sample)
    assert inventory(world, world_name="world", path_policy="linux-server") == before


def test_source_drift_is_not_reported_as_a_consistent_inspection(sample, monkeypatch):
    real = audit.inventory
    calls = 0

    def drifting(*args, **kwargs):
        nonlocal calls
        calls += 1
        value = real(*args, **kwargs)
        if calls == 2:
            value["world/level.dat"]["sha256"] = "0" * 64
        return value

    monkeypatch.setattr(audit, "inventory", drifting)
    with pytest.raises(ValueError, match="changed"):
        inspect(sample)


def test_configuration_drift_is_not_hidden_by_unchanged_world_files(
    sample, monkeypatch
):
    real = audit.inventory
    calls = 0

    def drifting(*args, **kwargs):
        nonlocal calls
        calls += 1
        value = real(*args, **kwargs)
        if calls == 2:
            path = sample[0] / "config/omkalitycore-resource.properties"
            path.write_text(path.read_text().replace("spawn_x=0", "spawn_x=1"))
        return value

    monkeypatch.setattr(audit, "inventory", drifting)
    with pytest.raises(ValueError, match="configuration changed"):
        inspect(sample)
