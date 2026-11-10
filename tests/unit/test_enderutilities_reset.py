"""Reviewed player-inventory Target removal; these are synthetic NBT controls."""

import copy

import pytest

from launcher.nbt import Tag
from omk.enderutilities_reset import unbind_player_targets


def target(dimension):
    return Tag(
        10,
        {
            "posX": Tag(3, 640),
            "posY": Tag(3, 200),
            "posZ": Tag(3, 64),
            "Dim": Tag(3, dimension),
            "BlockFace": Tag(1, 1),
            "dPosX": Tag(6, 640.5),
            "dPosY": Tag(6, 200.0),
            "dPosZ": Tag(6, 64.5),
            "DimName": Tag(8, "fixture"),
            "BlockName": Tag(8, "minecraft:stone"),
            "BlockMeta": Tag(1, 0),
            "ItemMeta": Tag(2, 0),
            "Yaw": Tag(5, 23.0),
            "Pitch": Tag(5, 7.0),
        },
    )


def crystal(dimension, slot=0, damage=0):
    return {
        "id": Tag(8, "enderutilities:linkcrystal"),
        "Count": Tag(3, 1),
        "Damage": Tag(2, damage),
        "Slot": Tag(1, slot),
        "tag": Tag(
            10,
            {
                "Target": target(dimension),
                "Owner": Tag(10, {"custom": Tag(8, "keep")}),
                "custom": Tag(8, "keep"),
            },
        ),
    }


def porter(slot=1):
    return {
        "id": Tag(8, "enderutilities:enderporter"),
        "Count": Tag(1, 1),
        "Damage": Tag(2, 1),
        "Slot": Tag(1, slot),
        "tag": Tag(
            10,
            {
                "Selected_linkcrystal": Tag(1, 0),
                "custom": Tag(8, "keep"),
                "Items": Tag(
                    9,
                    (
                        10,
                        [
                            Tag(
                                10,
                                {
                                    "Slot": Tag(1, 0),
                                    "id": Tag(8, "enderutilities:endercapacitor"),
                                    "Count": Tag(1, 1),
                                    "Damage": Tag(2, 2),
                                    "tag": Tag(
                                        10, {"EnderChargeAmount": Tag(3, 75000)}
                                    ),
                                },
                            ),
                            Tag(10, crystal(-18000, 1)),
                            Tag(10, crystal(0, 2)),
                        ],
                    ),
                ),
            },
        ),
    }


def player(*items):
    return {
        "Dimension": Tag(3, 0),
        "Inventory": Tag(9, (10, [Tag(10, x) for x in items])),
        "XpLevel": Tag(3, 12),
        "ForgeCaps": Tag(10, {"unknown": Tag(8, "keep")}),
    }


def test_only_target_removed_from_loose_and_both_selected_unselected_modules():
    root = player(crystal(-18000), porter())
    original = copy.deepcopy(root)
    result, paths = unbind_player_targets(root, -18000)
    assert root == original
    assert paths == [
        "/Inventory/0/tag/Target/Dim",
        "/Inventory/1/tag/Items/1/tag/Target/Dim",
    ]
    expected = copy.deepcopy(root)
    expected["Inventory"].value[1][0].value["tag"].value.pop("Target")
    expected["Inventory"].value[1][1].value["tag"].value["Items"].value[1][1].value[
        "tag"
    ].value.pop("Target")
    assert result == expected
    again, cleared = unbind_player_targets(result, -18000)
    assert again == result and not cleared


@pytest.mark.parametrize("dimension", [0, -1, 7, -18000, 424])
@pytest.mark.parametrize("slot", [0, 35, 100, -106])
def test_dimension_and_inventory_slot_are_data(dimension, slot):
    root = player(crystal(dimension, slot))
    result, paths = unbind_player_targets(root, dimension)
    assert (
        len(paths) == 1
        and "Target" not in result["Inventory"].value[1][0].value["tag"].value
    )
    kept, paths = unbind_player_targets(root, dimension + 1)
    assert kept == root and not paths


def test_unselected_modules_are_cleared_without_changing_selection_or_charge():
    root = player(porter())
    root["Inventory"].value[1][0].value["tag"].value["Selected_linkcrystal"] = Tag(1, 1)
    result, paths = unbind_player_targets(root, -18000)
    assert len(paths) == 1
    assert result["Inventory"].value[1][0].value["tag"].value[
        "Selected_linkcrystal"
    ] == Tag(1, 1)
    assert root != result


@pytest.mark.parametrize("damage", [1, 2, 3])
def test_unreviewed_crystal_tiers_are_not_rewritten(damage):
    root = player(crystal(-18000, damage=damage))
    result, paths = unbind_player_targets(root, -18000)
    assert root == result and not paths


def test_unknown_containers_capabilities_and_end_inventory_are_not_traversed():
    nested = crystal(-18000)
    root = player(
        {
            "id": Tag(8, "minecraft:chest"),
            "Slot": Tag(1, 0),
            "Count": Tag(1, 1),
            "Damage": Tag(2, 0),
            "tag": Tag(10, {"Items": Tag(9, (10, [Tag(10, nested)]))}),
        }
    )
    root["EnderItems"] = Tag(9, (10, [Tag(10, nested)]))
    root["ForgeCaps"] = Tag(10, {"bag": Tag(9, (10, [Tag(10, nested)]))})
    result, paths = unbind_player_targets(root, -18000)
    assert root == result and not paths


@pytest.mark.parametrize(
    "change",
    [
        lambda x: x.update(Dim=Tag(8, "-18000")),
        lambda x: x.pop("posY"),
        lambda x: x.update(BlockFace=Tag(3, 1)),
        lambda x: x.update(unknown=Tag(8, "preserve rather than discard")),
        lambda x: x.update(dPosX=Tag(6, float("inf"))),
        lambda x: x.pop("Pitch"),
    ],
)
def test_unreviewed_target_schema_refuses_without_source_mutation(change):
    root = player(crystal(-18000))
    change(root["Inventory"].value[1][0].value["tag"].value["Target"].value)
    original = copy.deepcopy(root)
    with pytest.raises(ValueError):
        unbind_player_targets(root, -18000)
    assert root == original


def test_other_dimension_unknown_target_data_preserved():
    root = player(crystal(0))
    root["Inventory"].value[1][0].value["tag"].value["Target"].value["unknown"] = Tag(
        3, 99
    )
    assert unbind_player_targets(root, -18000) == (root, [])


def test_duplicate_slots_and_wrong_inventory_type_refuse():
    for root in (player(crystal(-18000), porter(0)), {"Inventory": Tag(10, {})}):
        with pytest.raises(ValueError):
            unbind_player_targets(root, -18000)
