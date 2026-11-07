import copy

import pytest

from launcher.nbt import Tag
from omk.ftb_dimension_references import ftb_record

DIMENSIONS = (0, -1, 1, 7, 17, 50, 66, 420, 425, -100, 14676, -18000, 314159)


def positions():
    return {str(d): Tag(11, [8, 70, -8, d]) for d in DIMENSIONS} | {
        "legacy_main": Tag(11, [3, 70, -3]),
        "empty": Tag(11, []),
    }


@pytest.mark.parametrize("dimension", DIMENSIONS)
def test_every_world_clears_its_homes_warps_claims_and_back_without_other_losses(
    dimension,
):
    homes = positions()
    utilities = {
        "Homes": Tag(10, homes),
        "LastDeath": Tag(11, [8, 70, -8, dimension]),
        "teleportTracker": Tag(
            10,
            {
                str(i): Tag(10, {"dimension": Tag(3, d), "opaque": Tag(8, "keep")})
                for i, d in enumerate(DIMENSIONS)
            },
        ),
        "permissions": Tag(8, "keep"),
    }
    player = {
        "Data": Tag(10, {"ftbutilities": Tag(10, utilities)}),
        "TeamID": Tag(8, "unchanged-team"),
    }
    universe = {
        "FakePlayer": Tag(10, copy.deepcopy(player)),
        "FakeTeam": Tag(10, {"rights": Tag(8, "unchanged")}),
        "Data": Tag(10, {"ftbutilities": Tag(10, {"Warps": Tag(10, positions())})}),
    }
    claims = {
        "ClaimedChunks": Tag(
            10,
            {
                str(d): Tag(
                    9,
                    (
                        10,
                        [
                            Tag(
                                10,
                                {"x": Tag(3, 4), "z": Tag(3, -2), "loaded": Tag(1, 1)},
                            )
                        ],
                    ),
                )
                for d in DIMENSIONS
            },
        ),
        "opaque": Tag(8, "keep"),
    }
    originals = copy.deepcopy((player, universe, claims))
    changed = ftb_record(player, dimension)
    changed_universe = ftb_record(universe, dimension, universe=True)
    changed_claims = ftb_record(claims, dimension, claims=True)
    expected_positions = {
        k: v
        for k, v in homes.items()
        if k != str(dimension) and not (dimension == 0 and k == "legacy_main")
    }
    for row in (changed, changed_universe["FakePlayer"].value):
        data = row["Data"].value["ftbutilities"].value
        assert data["Homes"].value == expected_positions
        assert data["LastDeath"] == Tag(11, [])
        assert data["teleportTracker"].value == {
            str(i): utilities["teleportTracker"].value[str(i)]
            for i, d in enumerate(DIMENSIONS)
            if d != dimension
        }
        assert (
            data["permissions"] == utilities["permissions"]
            and row["TeamID"] == player["TeamID"]
        )
    assert (
        changed_universe["Data"].value["ftbutilities"].value["Warps"].value
        == expected_positions
    )
    assert changed_universe["FakeTeam"] == universe["FakeTeam"]
    assert changed_claims["ClaimedChunks"].value == {
        k: v for k, v in claims["ClaimedChunks"].value.items() if k != str(dimension)
    }
    assert changed_claims["opaque"] == claims["opaque"]
    assert (player, universe, claims) == originals
    assert ftb_record(changed, dimension) == changed


@pytest.mark.parametrize("dimension", [True, "7", None, -(2**31) - 1, 2**31])
def test_dimension_type_and_range_are_validated_without_writes(dimension):
    root = {"ClaimedChunks": Tag(10, {})}
    with pytest.raises(ValueError, match="dimension"):
        ftb_record(root, dimension, claims=True)
    assert root == {"ClaimedChunks": Tag(10, {})}
