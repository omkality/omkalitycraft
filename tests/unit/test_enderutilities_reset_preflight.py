"""Synthetic profile/save controls; real item usage is a separate native lab."""

import hashlib
import json

import pytest

from launcher.nbt import Tag
from omk import (
    enderutilities_reset as ender,
    resource_reset_preflight as preflight,
)
from omk.stopped_world_backup import inventory
from tests.unit.test_enderutilities_reset import crystal, player, porter
from tests.unit.test_resource_reset_preflight import (
    compound_list,
    encoded,
    region_write,
    saved as saved,  # noqa: PLC0414 -- explicit shared pytest fixture export
)

PLAYER = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa.dat"


@pytest.fixture
def ready(saved, monkeypatch):
    server, world, _, chunk = saved
    data = b"explicit synthetic Ender Utilities artifact"
    digest = hashlib.sha256(data).hexdigest()
    (server / "mods" / ender.ARTIFACT).write_bytes(data)
    profile = json.loads(preflight.PROFILE.read_text())
    profile["artifacts"][ender.ARTIFACT] = digest
    preflight.PROFILE.write_text(json.dumps(profile))
    monkeypatch.setattr(ender, "SHA256", digest)
    root = player(crystal(-18000), porter())
    encoded(world / "playerdata" / PLAYER, root)
    return server, world, root, chunk


def test_only_exact_supported_paths_can_be_staged_and_source_is_read_only(ready):
    server, world, _, _ = ready
    before = inventory(world, world_name="world")
    result = preflight.preflight(server, "world", -18000)
    assert result["can_stage_data"]
    assert result["links"]["finding_count"] == 2
    assert result["links"]["handled_finding_count"] == 2
    assert result["links"]["unhandled_finding_count"] == 0
    assert result["adapters"][ender.ADAPTER]["handled_references"] == 2
    assert all(
        row["staging_adapter"] == ender.ADAPTER for row in result["links"]["examples"]
    )
    assert not result["ready_for_start"] and not result["portal_adapters_reviewed"]
    assert inventory(world, world_name="world") == before


@pytest.mark.parametrize(
    "storage",
    [
        "capability",
        "ender-bag",
        "bag",
        "region",
        "unknown-player-file",
        "tier",
        "ambiguous-key",
    ],
)
def test_unreviewed_storage_or_tier_remains_blocking(ready, storage):
    server, world, root, chunk = ready
    item = crystal(-18000, slot=2)
    if storage == "capability":
        root["ForgeCaps"] = Tag(10, {"bag": compound_list([item])})
    elif storage == "ender-bag":
        root["EnderItems"] = compound_list(
            [
                {
                    "id": Tag(8, "minecraft:chest"),
                    "Slot": Tag(1, 2),
                    "tag": Tag(10, {"Items": compound_list([item])}),
                }
            ]
        )
    elif storage == "bag":
        root["Inventory"].value[1].append(
            Tag(
                10,
                {
                    "id": Tag(8, "minecraft:chest"),
                    "Slot": Tag(1, 2),
                    "tag": Tag(10, {"Items": compound_list([item])}),
                },
            )
        )
    elif storage == "tier":
        item["Damage"] = Tag(2, 1)
        root["Inventory"].value[1].append(Tag(10, item))
    elif storage == "ambiguous-key":
        root["Inventory"].value[1][0].value["tag/Target"] = item["tag"].value["Target"]
    elif storage == "region":
        chunk["TileEntities"] = compound_list(
            [
                {
                    "id": Tag(8, "minecraft:chest"),
                    "x": Tag(3, 15),
                    "y": Tag(3, 70),
                    "z": Tag(3, 15),
                    "Items": compound_list([item]),
                }
            ]
        )
        region_write(world, chunk)
    else:
        encoded(world / "playerdata/unreviewed.dat", player(item))
    encoded(world / "playerdata" / PLAYER, root)
    result = preflight.preflight(server, "world", -18000)
    assert not result["can_stage_data"]
    assert result["links"]["handled_finding_count"] == 2
    assert result["links"]["unhandled_finding_count"] == 1


def test_missing_pin_disables_adapter_and_artifact_change_refuses(ready):
    server, _, _, _ = ready
    profile = json.loads(preflight.PROFILE.read_text())
    del profile["artifacts"][ender.ARTIFACT]
    preflight.PROFILE.write_text(json.dumps(profile))
    result = preflight.preflight(server, "world", -18000)
    assert not result["adapters"] and not result["can_stage_data"]
    assert result["links"]["unhandled_finding_count"] == 2
    profile["artifacts"][ender.ARTIFACT] = ender.SHA256
    preflight.PROFILE.write_text(json.dumps(profile))
    (server / "mods" / ender.ARTIFACT).write_bytes(b"changed")
    with pytest.raises(ValueError, match="artifact"):
        preflight.preflight(server, "world", -18000)


def test_both_native_player_inventory_roots_are_admitted_without_source_write(ready):
    server, world, root, _ = ready
    root["EnderItems"] = compound_list([crystal(-18000, 26), porter(0)])
    encoded(world / "playerdata" / PLAYER, root)
    before = inventory(world, world_name="world")
    result = preflight.preflight(server, "world", -18000)
    assert result["can_stage_data"] and result["links"]["handled_finding_count"] == 4
    assert result["links"]["unhandled_finding_count"] == 0
    assert (
        sum("/EnderItems/" in x["nbt_path"] for x in result["links"]["examples"]) == 2
    )
    assert not result["ready_for_start"]
    assert inventory(world, world_name="world") == before


def test_unknown_resource_target_schema_refuses_before_any_write(ready):
    server, world, root, _ = ready
    root["Inventory"].value[1][0].value["tag"].value["Target"].value["unknown"] = Tag(
        3, 42
    )
    encoded(world / "playerdata" / PLAYER, root)
    before = inventory(world, world_name="world")
    with pytest.raises(ValueError, match="schema"):
        preflight.preflight(server, "world", -18000)
    assert inventory(world, world_name="world") == before
