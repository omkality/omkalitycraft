"""Test dependencies for ftb restore reconcile."""

import copy
import gzip
import json
import zipfile

import pytest

from launcher.nbt import Tag, write_nbt
from omk.backups import (
    ftb_restore_authority as gate,
    ftb_restore_reconcile as merge,
)


def player(name, uid):
    return {
        "Name": Tag(8, name),
        "UUID": Tag(8, uid),
        "TeamID": Tag(8, "base"),
        "Data": Tag(
            10,
            {
                "ftbutilities": Tag(
                    10, {"Homes": Tag(10, {"old": Tag(11, [0, 1, 2, 3])})}
                )
            },
        ),
    }


@pytest.fixture
def snapshots():
    rules = {
        key: Tag(1, 0) if key == "Explosions" else Tag(8, "ally") for key in merge.RULES
    }
    team = {
        "ID": Tag(8, "base"),
        "UID": Tag(2, 10),
        "Type": Tag(8, "player"),
        "Owner": Tag(8, "owner"),
        "Players": Tag(10, {"guest": Tag(8, "ally")}),
        "FakePlayerStatus": Tag(8, "ally"),
        "FreeToJoin": Tag(1, 0),
        "RequestingInvite": Tag(9, (0, [])),
        "Data": Tag(10, {"ftbutilities": Tag(10, rules)}),
    }
    historical = {
        "players/owner.dat": player("owner", "a" * 32),
        "players/guest.dat": player("guest", "c" * 32),
        "teams/base.dat": team,
        "universe.dat": {
            "UUID": Tag(8, "b" * 32),
            "FakePlayer": Tag(10, player("fake", "d" * 32)),
            "FakeTeam": Tag(10, copy.deepcopy(team)),
        },
    }
    current = copy.deepcopy(historical)
    current["teams/base.dat"]["Players"].value.clear()
    current["players/owner.dat"]["Data"].value["ftbutilities"].value[
        "Homes"
    ].value.clear()
    return current, historical


def archive(path, records, claims=b"old-claims"):
    with zipfile.ZipFile(path, "w") as file:
        file.writestr("lab-world/level.dat", b"fixture")
        for name, root in records.items():
            file.writestr(gate.PREFIX + name, gzip.compress(write_nbt("", root)))
        file.writestr(gate.PREFIX + "teams/claimedchunks/base.dat", claims)


@pytest.fixture
def staged(tmp_path, snapshots, monkeypatch):
    current, historical = snapshots
    lab = tmp_path / "recovery-lab-merge"
    dest = lab / "recovery-lab-return/server"
    dest.mkdir(parents=True)
    (lab / "backups").mkdir()
    old, now = lab / "backups/before-grief.zip", lab / "backups/before-full-return.zip"
    archive(old, historical)
    archive(now, current, b"new-claims")
    for name, root in historical.items():
        path = dest / gate.PREFIX / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(gzip.compress(write_nbt("", root)))
    claims = dest / gate.PREFIX / "teams/claimedchunks/base.dat"
    claims.parent.mkdir(parents=True)
    claims.write_bytes(b"old-claims")
    for marker in ("full-return-staged.json", "current-ranks-staged.json"):
        (lab / marker).write_text("{}")
    (lab / "full-return-plan.json").write_text(
        json.dumps({"source": old.name, "source_sha256": merge.sha(old)})
    )
    monkeypatch.setattr(gate, "check_runtime", lambda _: None)
    return lab, dest, now, old
