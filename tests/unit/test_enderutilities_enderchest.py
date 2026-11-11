"""Synthetic EnderItems layout/admission controls; native access is a separate lab."""

import copy

import pytest

from launcher.nbt import Tag
from omk.enderutilities_reset import unbind_player_targets
from tests.unit.test_enderutilities_reset import crystal, player, porter


@pytest.mark.parametrize("slot", [0, 26])
@pytest.mark.parametrize("main_inventory", [False, True])
def test_ender_storage_clears_only_resource_target_even_without_main_inventory(
    slot, main_inventory
):
    root = player(crystal(-18000)) if main_inventory else {"XpLevel": Tag(3, 12)}
    root["EnderItems"] = Tag(9, (10, [Tag(10, crystal(-18000, slot))]))
    before = copy.deepcopy(root)
    result, paths = unbind_player_targets(root, -18000)
    assert root == before
    assert "/EnderItems/0/tag/Target/Dim" in paths
    expected = copy.deepcopy(root)
    expected["EnderItems"].value[1][0].value["tag"].value.pop("Target")
    if main_inventory:
        expected["Inventory"].value[1][0].value["tag"].value.pop("Target")
    assert result == expected
    assert unbind_player_targets(result, -18000) == (result, [])


def test_ender_porter_keeps_other_module_charge_and_selection():
    root = {"EnderItems": Tag(9, (10, [Tag(10, porter(26))]))}
    before = copy.deepcopy(root)
    result, paths = unbind_player_targets(root, -18000)
    expected = copy.deepcopy(root)
    expected["EnderItems"].value[1][0].value["tag"].value["Items"].value[1][1].value[
        "tag"
    ].value.pop("Target")
    assert result == expected and root == before
    assert paths == ["/EnderItems/0/tag/Items/1/tag/Target/Dim"]


@pytest.mark.parametrize("slot", [-106, -1, 27, 100])
def test_nonvanilla_ender_inventory_slots_refuse(slot):
    root = {"EnderItems": Tag(9, (10, [Tag(10, crystal(-18000, slot))]))}
    original = copy.deepcopy(root)
    with pytest.raises(ValueError, match="inventory slot"):
        unbind_player_targets(root, -18000)
    assert root == original


@pytest.mark.parametrize("data", [Tag(10, {}), Tag(9, (1, [Tag(1, 1)]))])
def test_unknown_ender_storage_layout_refuses(data):
    with pytest.raises(ValueError, match=r"item.list"):
        unbind_player_targets({"EnderItems": data}, -18000)


def test_duplicate_ender_slots_refuse_and_empty_or_other_world_is_preserved():
    with pytest.raises(ValueError, match="inventory slot"):
        unbind_player_targets(
            {
                "EnderItems": Tag(
                    9, (10, [Tag(10, crystal(-18000)), Tag(10, porter(0))])
                )
            },
            -18000,
        )
    for value in (Tag(9, (0, [])), Tag(9, (10, [Tag(10, crystal(0))]))):
        root = {"EnderItems": value}
        assert unbind_player_targets(root, -18000) == (root, [])
