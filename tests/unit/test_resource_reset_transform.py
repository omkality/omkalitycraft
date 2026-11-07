import copy

import pytest

from launcher.nbt import Tag
from omk import resource_reset_transform as edit


def player():
    return {
        "Dimension": Tag(3, -18000),
        "Pos": Tag(9, (6, [Tag(6, 0.0), Tag(6, 80.0), Tag(6, -2.0)])),
        "Motion": Tag(9, (6, [Tag(6, 2.0), Tag(6, -4.0), Tag(6, -1.0)])),
        "FallDistance": Tag(5, 60.0),
        "Health": Tag(5, 7.5),
        "XpLevel": Tag(3, 12),
        "Inventory": Tag(
            9, (10, [Tag(10, {"id": Tag(8, "minecraft:emerald"), "Count": Tag(1, 7)})])
        ),
        "ForgeCaps": Tag(10, {"unknown": Tag(11, [-18000, 12])}),
    }


def test_evacuated_player_preserves_progress_and_cannot_keep_fall_velocity():
    source = player()
    original = copy.deepcopy(source)
    changed = edit.player(source, -18000, edit.landing([8, 100, -8]))
    assert source == original
    assert changed["Dimension"] == Tag(3, 0)
    assert changed["Pos"] == Tag(9, (6, [Tag(6, 8.5), Tag(6, 100.0), Tag(6, -7.5)]))
    assert changed["Motion"] == Tag(9, (6, [Tag(6, 0.0)] * 3))
    assert changed["FallDistance"] == Tag(5, 0.0)
    assert changed["OnGround"] == Tag(1, 1)
    assert changed["PortalCooldown"] == Tag(3, 300)
    for key in ("Health", "XpLevel", "Inventory", "ForgeCaps"):
        assert changed[key] == original[key]


def test_unrelated_player_is_identical_and_only_resource_respawns_are_removed():
    source = player()
    source["Dimension"] = Tag(3, 7)
    assert edit.player(source, -18000, edit.landing([8, 100, 8])) == source
    source.update(
        SpawnDimension=Tag(3, -18000),
        HasSpawnDimensionSet=Tag(1, 1),
        SpawnX=Tag(3, 1),
        SpawnY=Tag(3, 70),
        SpawnZ=Tag(3, 2),
        SpawnForced=Tag(1, 1),
        Spawns=Tag(
            9,
            (
                10,
                [
                    Tag(10, {"Dim": Tag(3, -18000)}),
                    Tag(10, {"Dim": Tag(3, 7), "x": Tag(3, 5)}),
                ],
            ),
        ),
    )
    changed = edit.player(source, -18000, edit.landing([8, 100, 8]))
    assert "SpawnDimension" not in changed
    assert changed["HasSpawnDimensionSet"] == Tag(1, 0)
    # Forge keeps the Overworld bed in these vanilla fields, independently of
    # its selected respawn dimension. Only the resource entry in Spawns goes.
    for key in ("SpawnX", "SpawnY", "SpawnZ", "SpawnForced"):
        assert changed[key] == source[key]
    assert changed["Spawns"].value[1] == source["Spawns"].value[1][1:]
    assert (
        changed["Dimension"] == source["Dimension"] and changed["Pos"] == source["Pos"]
    )


@pytest.mark.parametrize("key", ["RootVehicle", "Riding"])
def test_mounted_resource_player_requires_explicit_adapter(key):
    source = player()
    source[key] = Tag(10, {"Entity": Tag(10, {"Inventory": Tag(8, "keep")})})
    with pytest.raises(ValueError, match="vehicle adapter"):
        edit.player(source, -18000, edit.landing([8, 100, 8]))
    source["Dimension"] = Tag(3, 0)
    assert edit.player(source, -18000, edit.landing([8, 100, 8])) == source


@pytest.mark.parametrize("flag", [Tag(1, 2), Tag(3, 1)])
def test_unreviewed_selected_respawn_flag_is_refused_without_mutating_source(flag):
    source = player()
    source["HasSpawnDimensionSet"] = flag
    original = copy.deepcopy(source)
    with pytest.raises(ValueError):
        edit.player(source, -18000, edit.landing([8, 100, 8]))
    assert source == original


@pytest.mark.parametrize(
    "value",
    [
        [0, 0, 0],
        [0, 254, 0],
        [True, 70, 0],
        [1.5, 70, 0],
        [0, 70],
        [30000000, 70, 0],
        "0 70 0",
    ],
)
def test_invalid_landing_is_never_silently_normalized(value):
    with pytest.raises(ValueError, match="landing"):
        edit.landing(value)


def utilities():
    return {
        "Homes": Tag(
            10,
            {
                "resource": Tag(11, [1, 70, 2, -18000]),
                "main": Tag(11, [1, 70, 2]),
                "end": Tag(11, [1, 70, 2, 1]),
            },
        ),
        "LastDeath": Tag(11, [1, 70, 2, -18000]),
        "teleportTracker": Tag(
            10,
            {
                "0": Tag(10, {"dimension": Tag(3, -18000)}),
                "1": Tag(10, {"dimension": Tag(3, 7), "opaque": Tag(8, "keep")}),
            },
        ),
        "UnknownPermission": Tag(8, "preserve"),
    }


def test_ftb_homes_back_and_warps_are_filtered_by_dimension_only():
    data = utilities()
    source = {
        "Data": Tag(10, {"ftbutilities": Tag(10, copy.deepcopy(data))}),
        "TeamID": Tag(8, "base"),
    }
    result = edit.ftb_record(source, -18000)
    changed = result["Data"].value["ftbutilities"].value
    assert set(changed["Homes"].value) == {"main", "end"}
    assert changed["LastDeath"] == Tag(11, [])
    assert changed["teleportTracker"].value == {"1": data["teleportTracker"].value["1"]}
    assert (
        changed["UnknownPermission"] == data["UnknownPermission"]
        and result["TeamID"] == source["TeamID"]
    )
    assert source["Data"].value["ftbutilities"].value == data
    universe = {
        "FakePlayer": Tag(10, source),
        "Data": Tag(10, {"ftbutilities": Tag(10, {"Warps": data["Homes"]})}),
        "FakeTeam": Tag(10, {"permissions": Tag(8, "keep")}),
    }
    output = edit.ftb_record(universe, -18000, universe=True)
    assert set(output["Data"].value["ftbutilities"].value["Warps"].value) == {
        "main",
        "end",
    }
    assert output["FakeTeam"] == universe["FakeTeam"]


def test_claims_preserve_other_dimensions_forced_loading_and_unknown_fields():
    source = {
        "ClaimedChunks": Tag(
            10,
            {
                "-18000": Tag(9, (10, [])),
                "7": Tag(
                    9,
                    (
                        10,
                        [
                            Tag(
                                10,
                                {
                                    "x": Tag(3, -5),
                                    "z": Tag(3, 2),
                                    "loaded": Tag(1, 1),
                                    "opaque": Tag(8, "keep"),
                                },
                            )
                        ],
                    ),
                ),
            },
        ),
        "opaque": Tag(8, "keep"),
    }
    expected = copy.deepcopy(source)
    del expected["ClaimedChunks"].value["-18000"]
    assert edit.ftb_record(source, -18000, claims=True) == expected


@pytest.mark.parametrize("key", ["PlayerData", "PlayerDimensions"])
def test_jed_current_and_legacy_tracker_keep_game_modes_and_hardcore_state(key):
    row = {
        "UUIDM": Tag(4, 1),
        "UUIDL": Tag(4, 2),
        "Dimension": Tag(3, -18000),
        "HardcoreDead": Tag(1, 1),
        "GameMode": Tag(1, 0),
    }
    other = copy.deepcopy(row)
    other.update(UUIDL=Tag(4, 3), Dimension=Tag(3, 7))
    source = {
        key: Tag(9, (10, [Tag(10, row), Tag(10, other)])),
        "opaque": Tag(8, "keep"),
    }
    expected = copy.deepcopy(source)
    expected[key].value[1][0].value["Dimension"] = Tag(3, 0)
    assert edit.jed_record(source, -18000) == expected
    duplicated = copy.deepcopy(source)
    duplicated[key].value[1].append(copy.deepcopy(source[key].value[1][0]))
    with pytest.raises(ValueError, match="Duplicate"):
        edit.jed_record(duplicated, -18000)
    source["PlayerDimensions" if key == "PlayerData" else "PlayerData"] = source[key]
    with pytest.raises(ValueError, match="Mixed"):
        edit.jed_record(source, -18000)
