"""A selected world cannot omit another world's files or shared player state."""

import json

import pytest

from omk.shared.nbt import Tag
from omk.worlds.border_policy import _borders, _dimension_info, _primer, border_plan
from omk.worlds.reset import (
    dimension_reset,
    resource_reset_stage,
    resource_reset_transform,
)


def test_exact_dj2_border_sizes_and_dynamic_default():
    plan = border_plan("dj2-world")
    assert len(plan["dimensions"]) == 30
    assert plan["dimensions"]["0"] == 32768
    assert plan["dimensions"]["-18000"] == plan["dimensions"]["1"] == 16384
    assert plan["dimensions"]["-1"] == plan["dimensions"]["7"] == 8192
    assert plan["default_width"] == 8192
    with pytest.raises(ValueError, match="ambiguous"):
        border_plan("DIM-1")


def test_worldborder_config_matches_forge_shutdown_serialization():
    plan = {"world": "world", "dimensions": {"-2": 16, "0": 16, "-10": 16}}
    block = " {\n    I:radiusX=8\n    I:radiusZ=8\n    B:wrapping=false\n    D:x=0.0\n    D:z=0.0\n}\n\n\n"
    assert _borders(plan) == "# Configuration file\n\n" + "".join(
        name + block for name in ("DIM-10", "DIM-2", "world")
    )


def test_border_only_dimensions_keep_the_provider_spawn_on_first_load():
    source = {
        "dimensions": [
            {"dim": 420, "jed": {"SpawnPointSearchType": {"type": "cavern"}}},
            {"dim": -18000, "worldinfo_onetime": {"RandomSeed": 31}},
        ]
    }
    result = json.loads(
        _dimension_info(json.dumps(source).encode(), border_plan("dj2"))
    )
    rows = {row["dim"]: row for row in result["dimensions"]}
    assert rows[14676]["jed"]["SpawnPointSearchType"] == {"type": "none"}
    assert rows[14676]["worldinfo"]["BorderSize"] == 8192
    assert rows[420]["jed"]["SpawnPointSearchType"] == {"type": "cavern"}
    assert rows[-18000]["worldinfo_onetime"] == {"RandomSeed": 31}
    assert "jed" not in rows[-18000] and "jed" not in rows[0]
    assert all(row["worldinfo"]["Difficulty"] == 3 for row in rows.values())


def test_existing_primer_policy_adds_hard_for_each_loaded_dimension():
    source = """Commands {
    S:dimensionLoadingCommands <
        jed worldborder {DIMENSION} set 8192
        worldprimer-dim-command 0 jed worldborder 0 set 32768
        worldprimer-dim-command 1 jed worldborder 1 set 16384
        worldprimer-dim-command -18000 jed worldborder -18000 set 16384
     >
    S:postWorldLoadingCommands <
        jed worldborder 0 set 32768
     >
}
Options {
    B:enableDimensionLoadingCommands=true
    B:enablePostWorldLoadingCommands=true
}
"""
    plan = border_plan("dj2")
    updated = _primer(source, plan)
    assert updated.replace("        jed difficulty {DIMENSION} hard\n", "") == source
    assert updated.count("jed difficulty {DIMENSION} hard") == 1
    assert _primer(updated, plan) == updated


def test_eden_reset_leaves_its_neighbors_and_resource_identity_byte_equivalent():
    files = {
        f"world/{path}": {"bytes": index, "sha256": str(index)}
        for index, path in enumerate(
            (
                "Eden/region/r.1.2.mca",
                "WildWood/region/r.1.2.mca",
                "Eden2/region/r.1.2.mca",
                "region/r.1.2.mca",
                "DIM-18000/region/r.1.2.mca",
                "omk-resource-world.properties",
            )
        )
    }
    actual = resource_reset_transform.result_inventory(
        files, {}, "world", 420, reset=dimension_reset.layout(420)
    )
    assert actual == {k: v for k, v in files.items() if not k.startswith("world/Eden/")}


def test_ambiguous_named_save_layout_is_refused(tmp_path):
    world = tmp_path / "world"
    (world / "Eden").mkdir(parents=True)
    (world / "DIM420").mkdir()
    with pytest.raises(ValueError, match="Ambiguous"):
        dimension_reset.verify_layout(
            world, 420, dimension_reset.layout(420), ["world/Eden/level.dat"]
        )


@pytest.mark.parametrize("identity", [None, "a" * 64])
def test_rftools_and_generic_save_folders_cannot_share_a_selected_id(
    tmp_path, identity
):
    world = tmp_path / "world"
    (world / "RFTOOLS6000").mkdir(parents=True)
    (world / "DIM6000").mkdir()
    layout = dimension_reset.layout(6000, rftools_identity=identity)
    with pytest.raises(ValueError, match="Ambiguous"):
        dimension_reset.verify_layout(
            world, 6000, layout, [f"world/{layout['folder']}/region/r.0.0.mca"]
        )


def test_overworld_omits_only_local_state_and_retains_player_data():
    paths = {
        "world/region/r.0.0.mca",
        "world/data/Stronghold.dat",
        "world/DIM-1/region/r.0.0.mca",
        "world/level.dat",
        "world/playerdata/uuid.dat",
        "world/betterquesting/QuestProgress.json",
        "world/data/TPDestinations.dat",
        "world/data/ftb_lib/universe.dat",
    }
    result = resource_reset_transform.result_inventory(
        {path: {} for path in paths}, {}, "world", 0, reset=dimension_reset.layout(0)
    )
    assert result.keys() == paths - {
        "world/region/r.0.0.mca",
        "world/data/Stronghold.dat",
    }


def test_overworld_relocates_only_overworld_players_and_keeps_inventory():
    inventory = Tag(9, (10, [Tag(10, {"id": Tag(8, "minecraft:diamond")})]))
    profile = {
        "Dimension": Tag(3, 0),
        "Inventory": inventory,
        "SpawnX": Tag(3, 15),
        "XpTotal": Tag(3, 101),
    }
    after = resource_reset_transform.player(
        profile, 0, (1.5, 70.0, 1.5), landing_dimension=-18000
    )
    assert after["Dimension"] == Tag(3, -18000)
    assert after["Inventory"] == inventory
    assert after["XpTotal"] == Tag(3, 101)
    assert "SpawnX" not in after and profile["SpawnX"] == Tag(3, 15)
    nether = {"Dimension": Tag(3, -1), "Inventory": inventory}
    assert (
        resource_reset_transform.player(nether, 0, (), landing_dimension=-18000)
        == nether
    )


def test_unreviewed_dimension_path_refused_before_any_read(monkeypatch):
    monkeypatch.setattr(resource_reset_stage.sys, "platform", "linux")
    request = {
        "schema": 1,
        "action": "plan",
        "operation": "a" * 32,
        "world": "world",
        "dimension": 420,
        "position": "auto",
        "snapshot": "snapshot-" + "a" * 32,
        "world_max_bytes": 1024**2,
        "policy": {},
        "reset": {"folder": "WildWood", "landing_dimension": 0},
    }
    with pytest.raises(ValueError, match="Invalid dimension reset"):
        resource_reset_stage.execute(request)
