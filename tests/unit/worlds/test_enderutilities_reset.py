"""Reviewed player-inventory Target removal; these are synthetic NBT controls."""

import copy

import pytest

from launcher.nbt import Tag
from omk.worlds.enderutilities_reset import unbind_player_targets
from tests.fixtures.unit.worlds.enderutilities_reset import (
    crystal,
    player,
    porter,
    target,
)

__all__ = ["crystal", "player", "porter", "target"]


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


def test_unknown_containers_and_capabilities_are_not_traversed():
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
