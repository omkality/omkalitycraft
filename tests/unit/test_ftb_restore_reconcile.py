import copy
import gzip
import json
import threading
import zipfile
from concurrent.futures import ThreadPoolExecutor

import pytest

from launcher.nbt import Tag, write_nbt
from omk import (
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


def test_current_revocation_and_historical_homes_are_both_preserved(snapshots):
    current, historical = snapshots
    original = copy.deepcopy(snapshots)
    result = merge.merged_records(current, historical)
    assert not result["teams/base.dat"]["Players"].value
    assert (
        result["players/owner.dat"]["Data"] == historical["players/owner.dat"]["Data"]
    )
    assert gate.compare(current, result)["compatible"]
    assert snapshots == original


def test_ownerless_server_team_transfers_current_rules_without_old_owner(snapshots):
    current, historical = snapshots
    for snapshot in snapshots:
        snapshot["teams/base.dat"]["Type"] = Tag(8, "server")
    del current["teams/base.dat"]["Owner"]
    current["teams/base.dat"]["Data"].value["ftbutilities"].value["EditBlocks"] = Tag(
        8, "none"
    )
    original = copy.deepcopy(snapshots)
    result = merge.merged_records(current, historical)
    assert "Owner" not in result["teams/base.dat"]
    assert not result["teams/base.dat"]["Players"].value
    assert result["teams/base.dat"]["Data"].value["ftbutilities"].value[
        "EditBlocks"
    ] == Tag(8, "none")
    assert gate.compare(current, result)["compatible"]
    assert snapshots == original


@pytest.mark.parametrize(
    "change", ["member", "owner", "mod", "invite", "open", "fake", "rule", "fake-team"]
)
def test_reviewed_current_permissions_transfer_without_guessing_identities(
    snapshots, change
):
    current, historical = snapshots
    team = current["teams/base.dat"]
    if change == "member":
        current["players/guest.dat"]["TeamID"].value = ""
    elif change == "owner":
        team["Owner"].value = "guest"
    elif change == "mod":
        team["Players"].value["guest"] = Tag(8, "mod")
    elif change == "invite":
        team["Invited"] = Tag(9, (8, [Tag(8, "guest")]))
    elif change == "open":
        team["FreeToJoin"].value = 1
    elif change == "fake":
        team["FakePlayerStatus"].value = "none"
    elif change == "rule":
        team["Data"].value["ftbutilities"].value["EditBlocks"].value = "member"
    else:
        current["universe.dat"]["FakeTeam"].value["FakePlayerStatus"].value = "none"
    assert gate.compare(current, merge.merged_records(current, historical))[
        "compatible"
    ]


@pytest.mark.parametrize(
    "change",
    [
        "new-player",
        "removed-team",
        "uuid",
        "team-uid",
        "world",
        "unknown",
        "bad-status",
        "unknown-name",
    ],
)
def test_unknown_or_ambiguous_changes_refuse_before_writing(snapshots, change):
    current, historical = snapshots
    if change == "new-player":
        current["players/new.dat"] = player("new", "e" * 32)
    elif change == "removed-team":
        del current["teams/base.dat"]
    elif change == "uuid":
        current["players/guest.dat"]["UUID"].value = "e" * 32
    elif change == "team-uid":
        current["teams/base.dat"]["UID"].value = 11
    elif change == "world":
        current["universe.dat"]["UUID"].value = "e" * 32
    elif change == "unknown":
        current["teams/base.dat"]["UnknownAuthority"] = Tag(1, 1)
    elif change == "bad-status":
        current["teams/base.dat"]["Players"].value["guest"] = Tag(8, "owner")
    else:
        current["teams/base.dat"]["Owner"].value = "unknown"
    with pytest.raises(ValueError):
        merge.merged_records(current, historical)


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


def test_transaction_preserves_source_archives_claims_and_historical_progress(
    staged, snapshots
):
    lab, dest, now, old = staged
    before = (merge.sha(now), merge.sha(old))
    result = merge.transfer(now, dest, lab=lab)
    assert result["verified"] and result["changed_records"] == ["teams/base.dat"]
    merge.verify_transfer(now, dest, lab=lab)
    gate.stage_gate(now, dest, lab=lab)
    gate.verify_gate(now, dest, lab=lab)
    assert before == (merge.sha(now), merge.sha(old))
    assert (
        dest / gate.PREFIX / "teams/claimedchunks/base.dat"
    ).read_bytes() == b"old-claims"
    assert gate.read_staged(dest) == merge.merged_records(*snapshots)
    with pytest.raises(ValueError, match="already attempted"):
        merge.transfer(now, dest, lab=lab)


@pytest.mark.parametrize("change", ["progress", "authority", "journal", "backup"])
def test_start_refuses_edits_even_when_authority_comparison_alone_might_match(
    staged, snapshots, change
):
    lab, dest, now, _old = staged
    merge.transfer(now, dest, lab=lab)
    if change in {"progress", "authority"}:
        name = "players/owner.dat" if change == "progress" else "teams/base.dat"
        path = dest / gate.PREFIX / name
        root = gate.nbt(path.read_bytes())
        if change == "progress":
            root["Data"].value["ftbutilities"].value["Homes"].value.clear()
        else:
            root["Players"].value["guest"] = Tag(8, "ally")
        path.write_bytes(gzip.compress(write_nbt("", root)))
    elif change == "journal":
        (lab / merge.DONE).write_text('{"verified":true}')
    else:
        archive(now, snapshots[0], b"changed-current-backup")
    with pytest.raises(ValueError):
        merge.verify_transfer(now, dest, lab=lab)


def test_partial_write_keeps_start_blocked_and_cannot_be_repeated(
    staged, snapshots, monkeypatch
):
    lab, dest, now, old = staged
    snapshots[0]["players/guest.dat"]["TeamID"].value = ""
    archive(now, snapshots[0])
    originals = (merge.sha(now), merge.sha(old))
    replace = merge.os.replace
    calls = []

    def fail(source, target):
        calls.append(str(target))
        if len(calls) == 2:
            raise OSError("injected interrupted copy")
        replace(source, target)

    monkeypatch.setattr(merge.os, "replace", fail)
    with pytest.raises(OSError):
        merge.transfer(now, dest, lab=lab)
    assert len(calls) == 2 and not (lab / merge.DONE).exists()
    with pytest.raises(ValueError):
        merge.verify_transfer(now, dest, lab=lab)
    with pytest.raises(ValueError, match="already attempted"):
        merge.transfer(now, dest, lab=lab)
    assert originals == (merge.sha(now), merge.sha(old))


def test_competing_transfers_have_one_writer(staged, monkeypatch):
    lab, dest, now, _old = staged
    barrier = threading.Barrier(2)
    original = merge._write_json

    def write(path, value):
        if path.name == merge.PLAN:
            barrier.wait(timeout=5)
        return original(path, value)

    monkeypatch.setattr(merge, "_write_json", write)

    def run():
        try:
            return merge.transfer(now, dest, lab=lab)["verified"]
        except ValueError, FileExistsError:
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: run(), range(2)))
    assert sorted(results) == [False, True]
    merge.verify_transfer(now, dest, lab=lab)


def test_existing_comparison_cannot_authorize_a_new_transfer(staged):
    lab, dest, now, _old = staged
    (lab / "ftb-authority-comparison.json").write_text('{"compatible":true}')
    with pytest.raises(ValueError, match="already attempted"):
        merge.transfer(now, dest, lab=lab)
    assert not (lab / merge.PLAN).exists()
