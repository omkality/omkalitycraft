"""Test dependencies for ftb restore authority."""

import copy

import pytest

from launcher.nbt import Tag


def player(name="owner", uid="a" * 32):
    return {
        "Name": Tag(8, name),
        "UUID": Tag(8, uid),
        "TeamID": Tag(8, "base"),
        "LastTimeSeen": Tag(4, 1),
        "HideTeamNotification": Tag(1, 0),
        "Data": Tag(10, {"ftbutilities": Tag(10, {"Homes": Tag(10, {})})}),
    }


@pytest.fixture
def records():
    team = {
        "ID": Tag(8, "base"),
        "Owner": Tag(8, "owner"),
        "Type": Tag(8, "player"),
        "Players": Tag(10, {"guest": Tag(8, "ally")}),
        "FakePlayerStatus": Tag(8, "ally"),
        "FreeToJoin": Tag(1, 0),
        "Data": Tag(10, {"ftbutilities": Tag(10, {"EditBlocks": Tag(8, "ally")})}),
    }
    return {
        "universe.dat": {
            "UUID": Tag(8, "b" * 32),
            "FakePlayer": Tag(10, player()),
            "FakeTeam": Tag(10, copy.deepcopy(team)),
        },
        "players/owner.dat": player(),
        "teams/base.dat": team,
    }
