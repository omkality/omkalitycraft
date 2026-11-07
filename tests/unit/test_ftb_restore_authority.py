import copy
import gzip
import json
import zipfile
from types import SimpleNamespace

import pytest

from launcher.nbt import MAX_BYTES, Tag, write_nbt
from omk import ftb_restore_authority as gate
from omk.recovery_lab import RecoveryRuntime


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


@pytest.mark.parametrize(
    "change",
    [
        "ally",
        "owner",
        "open",
        "fake",
        "protection",
        "invite",
        "player-team",
        "new-player",
        "unknown",
    ],
)
def test_authority_change_is_never_silently_restored(records, change):
    current = copy.deepcopy(records)
    team = current["teams/base.dat"]
    if change == "ally":
        team["Players"].value.clear()
    elif change == "owner":
        team["Owner"].value = "other"
    elif change == "open":
        team["FreeToJoin"].value = 1
    elif change == "fake":
        team["FakePlayerStatus"].value = "none"
    elif change == "protection":
        team["Data"].value["ftbutilities"].value["EditBlocks"].value = "member"
    elif change == "invite":
        team["Invited"] = Tag(9, (8, [Tag(8, "guest")]))
    elif change == "player-team":
        current["players/owner.dat"]["TeamID"].value = ""
    elif change == "new-player":
        current["players/guest.dat"] = player("guest", "c" * 32)
    else:
        team["UnknownSecuritySetting"] = Tag(1, 1)
    result = gate.compare(current, records)
    assert not result["compatible"] and result["changed_records"]
    assert result["current_sha256"] != result["historical_sha256"]


def test_progress_fields_can_rollback_without_changing_authority(records):
    current = copy.deepcopy(records)
    root = current["players/owner.dat"]
    root["LastTimeSeen"].value = 200
    root["HideTeamNotification"].value = 1
    root["Data"].value["ftbutilities"].value["Homes"].value["base"] = Tag(
        11, [0, 1, 2, 3]
    )
    original = copy.deepcopy(current)
    assert gate.compare(current, records)["compatible"]
    assert current == original  # Comparing must not mutate either snapshot.


def test_ownerless_server_team_matches_native_ftb_and_keeps_authority(records):
    team = records["teams/base.dat"]
    team["Type"] = Tag(8, "server")
    del team["Owner"]
    original = copy.deepcopy(records)
    assert gate.compare(records, original)["compatible"]
    assert records == original
    changed = copy.deepcopy(records)
    changed["teams/base.dat"]["Owner"] = Tag(8, "owner")
    assert not gate.compare(changed, records)["compatible"]
    changed = copy.deepcopy(records)
    changed["teams/base.dat"]["FakePlayerStatus"] = Tag(8, "none")
    assert not gate.compare(changed, records)["compatible"]


def test_player_team_still_requires_owner_and_server_owner_must_be_text(records):
    del records["teams/base.dat"]["Owner"]
    with pytest.raises(ValueError, match="identity field"):
        gate.projection(records)
    records["teams/base.dat"]["Type"] = Tag(8, "server")
    records["teams/base.dat"]["Owner"] = Tag(3, 1)
    with pytest.raises(ValueError, match="identity field"):
        gate.projection(records)


@pytest.mark.parametrize(
    "change", ["duplicate", "missing-team", "wrong-id", "bad-type", "missing-universe"]
)
def test_ambiguous_or_incomplete_authority_is_refused(records, change):
    if change == "duplicate":
        records["players/guest.dat"] = player("guest")
    elif change == "missing-team":
        del records["teams/base.dat"]
    elif change == "wrong-id":
        records["teams/base.dat"]["ID"].value = "other"
    elif change == "bad-type":
        records["players/owner.dat"]["TeamID"] = Tag(3, 1)
    else:
        del records["universe.dat"]
    with pytest.raises(ValueError):
        gate.projection(records)


@pytest.mark.parametrize(
    "raw",
    [
        gzip.compress(b"x" * (MAX_BYTES + 1)),
        gzip.compress(write_nbt("", {})) + b"extra",
        b"bad-nbt",
    ],
)
def test_bounded_nbt_rejects_bombs_trailing_and_invalid_data(raw):
    with pytest.raises(ValueError):
        gate.nbt(raw)


def zip_world(path, records):
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("lab-world/level.dat", b"fixture")
        for name, root in records.items():
            archive.writestr(gate.PREFIX + name, gzip.compress(write_nbt("", root)))
        archive.writestr(gate.PREFIX + "teams/claimedchunks/base.dat", b"progress")


def staged(tmp_path, records):
    lab = tmp_path / "recovery-lab-gate"
    dest = lab / "recovery-lab-return/server"
    dest.mkdir(parents=True)
    (lab / "backups").mkdir()
    archive = lab / "backups/before-full-return.zip"
    zip_world(archive, records)
    (lab / "full-return-staged.json").write_text("{}")
    for name, root in records.items():
        path = dest / gate.PREFIX / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(gzip.compress(write_nbt("", root)))
    return lab, dest, archive


def test_zip_and_staged_projection_match_but_claim_progress_is_excluded(
    tmp_path, records
):
    _lab, dest, archive = staged(tmp_path, records)
    assert gate.compare(gate.read_zip(archive), gate.read_staged(dest))["compatible"]
    with zipfile.ZipFile(archive, "a") as file:
        file.writestr(gate.PREFIX + "unknown.dat", b"unknown")
    with pytest.raises(ValueError, match="Unreviewed"):
        gate.read_zip(archive)


def test_start_rechecks_actual_data_instead_of_trusting_a_marker(
    tmp_path, records, monkeypatch
):
    lab, dest, archive = staged(tmp_path, records)
    monkeypatch.setattr(gate, "check_runtime", lambda _: None)
    gate.stage_gate(archive, dest, lab=lab)
    gate.verify_gate(archive, dest, lab=lab)
    path = dest / gate.PREFIX / "teams/base.dat"
    changed = copy.deepcopy(records["teams/base.dat"])
    changed["Players"].value.clear()
    path.write_bytes(gzip.compress(write_nbt("", changed)))
    with pytest.raises(ValueError, match="start blocked"):
        gate.verify_gate(archive, dest, lab=lab)
    # Even a forged compatible marker does not turn a mismatched world into a match.
    (lab / "ftb-authority-comparison.json").write_text(json.dumps({"compatible": True}))
    with pytest.raises(ValueError, match="start blocked"):
        gate.verify_gate(archive, dest, lab=lab)


def test_conflict_has_a_report_but_cannot_authorize_start(
    tmp_path, records, monkeypatch
):
    lab, dest, archive = staged(tmp_path, records)
    monkeypatch.setattr(gate, "check_runtime", lambda _: None)
    old = copy.deepcopy(records)
    old["teams/base.dat"]["Players"].value.clear()
    zip_world(archive, old)
    with pytest.raises(ValueError, match="start blocked"):
        gate.stage_gate(archive, dest, lab=lab)
    assert not json.loads((lab / "ftb-authority-comparison.json").read_text())[
        "compatible"
    ]
    runtime = RecoveryRuntime(
        SimpleNamespace(ftb_authority_policy=True), lab, None, None, {}, None, None
    )
    runtime.linux = SimpleNamespace()
    runtime.server = SimpleNamespace(poll=lambda: 0)
    with pytest.raises(ValueError, match="start blocked"):
        runtime.start(dest)
    assert runtime.source_linux is None  # No replacement prepare/start occurred.


def test_unreviewed_mod_pin_is_refused(tmp_path):
    (tmp_path / "mods").mkdir()
    for name in gate.PINS:
        (tmp_path / "mods" / name).write_bytes(b"different")
    with pytest.raises(ValueError, match="runtime"):
        gate.check_runtime(tmp_path)


def test_aggregate_limit_counts_expanded_nbt_not_compressed_bytes(
    tmp_path, records, monkeypatch
):
    _lab, dest, archive = staged(tmp_path, records)
    monkeypatch.setattr(gate, "MAX_TOTAL", 100)
    with pytest.raises(ValueError, match="exceeds limit"):
        gate.read_zip(archive)
    with pytest.raises(ValueError, match="exceeds limit"):
        gate.read_staged(dest)


def test_linked_ftb_file_is_refused(tmp_path, records):
    _lab, dest, _archive = staged(tmp_path, records)
    target = dest / gate.PREFIX / "players/owner.dat"
    other = tmp_path / "other.dat"
    other.write_bytes(target.read_bytes())
    target.unlink()
    try:
        target.symlink_to(other)
    except OSError:
        pytest.skip("symlink unavailable")
    with pytest.raises(ValueError, match="Linked"):
        gate.read_staged(dest)
