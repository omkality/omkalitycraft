import copy
import gzip
import hashlib
import sys
import zipfile
from uuid import uuid4

import pytest

from launcher.nbt import Tag, write_nbt
from omk import (
    ftb_restore_authority as ftb,
    linux_restore_policy as policy,
    linux_world_restore as raw,
)
from omk.backup_store import BackupPolicy, BackupStore
from omk.stopped_world_backup import inventory

LIMITS = BackupPolicy(16 * 1024**2, 3, 8 * 1024**2, 1)


def records(owner):
    player = {
        "Name": Tag(8, owner),
        "UUID": Tag(8, "a" * 32),
        "TeamID": Tag(8, "base"),
        "Data": Tag(
            10,
            {
                "ftbutilities": Tag(
                    10, {"Homes": Tag(10, {"old": Tag(11, [0, 128, 241, 128])})}
                )
            },
        ),
    }
    guest = copy.deepcopy(player)
    guest.update(Name=Tag(8, "guest"), UUID=Tag(8, "b" * 32), TeamID=Tag(8, ""))
    team = {
        "ID": Tag(8, "base"),
        "UID": Tag(2, 12),
        "Type": Tag(8, "player"),
        "Owner": Tag(8, owner),
        "Players": Tag(10, {"guest": Tag(8, "ally")}),
        "FreeToJoin": Tag(1, 0),
        "FakePlayerStatus": Tag(8, "ally"),
        "Data": Tag(
            10,
            {
                "ftbutilities": Tag(
                    10,
                    {
                        k: Tag(1, 0) if k == "Explosions" else Tag(8, "ally")
                        for k in (
                            "Explosions",
                            "EditBlocks",
                            "InteractWithBlocks",
                            "AttackEntities",
                            "UseItems",
                        )
                    },
                )
            },
        ),
    }
    return {
        "players/" + owner.lower() + ".dat": player,
        "players/guest.dat": guest,
        "teams/base.dat": team,
        "universe.dat": {
            "UUID": Tag(8, "c" * 32),
            "FakePlayer": Tag(10, copy.deepcopy(player)),
            "FakeTeam": Tag(10, copy.deepcopy(team)),
        },
    }


@pytest.fixture
def setup(tmp_path, monkeypatch):
    return build(tmp_path, monkeypatch, "owner")


def build(tmp_path, monkeypatch, owner):
    source = tmp_path / "current"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()
    old = records(owner)
    current = copy.deepcopy(old)
    current["teams/base.dat"]["Players"].value.clear()
    current["players/" + owner.lower() + ".dat"]["Data"].value["ftbutilities"].value[
        "Homes"
    ].value.clear()
    archive = tmp_path / "old.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as out:
        out.writestr("world/level.dat", b"level")
        out.writestr("world/player-progress.dat", b"historical-inventory")
        out.writestr(
            "world/data/ftb_lib/teams/claimedchunks/base.dat", b"historical-claims"
        )
        for name, root in old.items():
            out.writestr(
                "world/data/ftb_lib/" + name, gzip.compress(write_nbt("", root))
            )
    for name, root in current.items():
        path = source / "world/data/ftb_lib" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(gzip.compress(write_nbt("", root)))
    (source / "world/level.dat").write_bytes(b"current-level")
    for root, value in ((source, b"current-ranks"), (target, b"default-ranks")):
        path = root / policy.RANKS
        path.parent.mkdir(parents=True)
        path.write_bytes(value)
    for name in policy.LISTS:
        (source / name).write_text("[]")
    (source / "banned-players.json").write_text(
        '[{"name":"guest","uuid":"bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"}]'
    )
    (source / "server.properties").write_text(
        "white-list=true\nrcon.password=source-fixture-secret\n"
    )
    (target / "server.properties").write_text(
        "white-list=false\nrcon.password=target-fixture-secret\n"
    )
    store = BackupStore.create(tmp_path / "store", LIMITS, path_policy="linux-server")
    files = {}
    with zipfile.ZipFile(archive) as z:
        files = {
            i.filename: {
                "bytes": i.file_size,
                "sha256": hashlib.sha256(z.read(i)).hexdigest(),
            }
            for i in z.infolist()
        }
    snapshot = store.publish(archive, files)
    req = {
        "operation": uuid4().hex,
        "world": "world",
        "snapshot": snapshot["id"],
        "archive_sha256": snapshot["sha256"],
        "world_max_bytes": 16 * 1024**2,
        "policy": vars(LIMITS),
    }
    monkeypatch.setattr(raw.sys, "platform", "linux")
    monkeypatch.setattr(ftb, "check_runtime", lambda _: None)
    raw.execute({**req, "action": "initialize"}, store.root, target)
    raw.execute({**req, "action": "stage"}, store.root, target)
    return source, target, store, req, old, files


def test_historical_progress_and_current_access_coexist(setup):
    source, target, store, req, old, _files = setup
    original = inventory(
        source / "world", world_name="world", path_policy="linux-server"
    )
    result = policy.execute(
        {**req, "action": "stage-policy"}, store.root, target, source
    )
    assert result["policy_staged"]
    assert policy.execute(
        {**req, "action": "verify-policy"}, store.root, target, source
    )["policy_verified"]
    actual = ftb.read_staged(target, world_name="world")
    assert not actual["teams/base.dat"]["Players"].value
    assert actual["players/owner.dat"]["Data"] == old["players/owner.dat"]["Data"]
    assert (
        target / "world/player-progress.dat"
    ).read_bytes() == b"historical-inventory"
    assert (
        target / "world/data/ftb_lib/teams/claimedchunks/base.dat"
    ).read_bytes() == b"historical-claims"
    for name in (*policy.LISTS, policy.RANKS):
        assert (source / name).read_bytes() == (target / name).read_bytes()
    assert b"white-list=true" in (target / "server.properties").read_bytes()
    assert b"target-fixture-secret" in (target / "server.properties").read_bytes()
    assert b"source-fixture-secret" not in (target / "server.properties").read_bytes()
    for name in (policy.PLAN, policy.DONE):
        assert "fixture-secret" not in (target / name).read_text()
    assert original == inventory(
        source / "world", world_name="world", path_policy="linux-server"
    )
    with pytest.raises(ValueError, match="full policy verifier"):
        raw.execute({**req, "action": "verify"}, store.root, target)


def test_real_linux_con_records_can_be_reconciled(tmp_path, monkeypatch):
    if sys.platform != "linux":
        pytest.skip("Reserved basename requires real Linux")
    source, target, store, req, _old, _files = build(tmp_path, monkeypatch, "CON")
    policy.stage(req, store.root, target, source)
    policy.verify(req, store.root, target, source)
    assert (target / "world/data/ftb_lib/players/con.dat").is_file()


@pytest.mark.parametrize(
    "change", ["ban", "rank", "progress", "receipt", "source", "archive"]
)
def test_prestart_rejects_tampering_or_a_new_source_state(setup, change):
    source, target, store, req, _old, _files = setup
    policy.stage(req, store.root, target, source)
    if change == "ban":
        (target / "banned-players.json").write_text("[]")
    elif change == "rank":
        (target / policy.RANKS).write_text("other-ranks")
    elif change == "progress":
        (target / "world/player-progress.dat").write_bytes(b"changed")
    elif change == "receipt":
        (target / policy.DONE).write_text('{"verified":true}')
    elif change == "source":
        (source / policy.RANKS).write_text("new-current-ranks")
    else:
        req["archive_sha256"] = "a" * 64
    with pytest.raises(ValueError):
        policy.verify(req, store.root, target, source)


def test_partial_policy_cannot_fall_back_to_raw_verification(setup, monkeypatch):
    source, target, store, req, _old, _files = setup
    original = policy.os.replace

    def fail(a, b):
        original(a, b)
        raise OSError("injected interruption after first replacement")

    monkeypatch.setattr(policy.os, "replace", fail)
    with pytest.raises(OSError):
        policy.stage(req, store.root, target, source)
    assert not (target / policy.DONE).exists()
    with pytest.raises(ValueError):
        policy.verify(req, store.root, target, source)
    with pytest.raises(ValueError, match="full policy verifier"):
        raw.execute({**req, "action": "verify"}, store.root, target)
    with pytest.raises(ValueError, match="already attempted"):
        policy.stage(req, store.root, target, source)


def test_unknown_authority_change_is_refused_before_plan(setup):
    source, target, store, req, _old, _files = setup
    path = source / "world/data/ftb_lib/teams/base.dat"
    root = ftb.nbt(path.read_bytes())
    root["UnknownPermission"] = Tag(1, 1)
    path.write_bytes(gzip.compress(write_nbt("", root)))
    with pytest.raises(ValueError, match="Unreviewed"):
        policy.stage(req, store.root, target, source)
    assert not (target / policy.PLAN).exists()


def test_source_target_alias_is_refused(setup):
    _source, target, store, req, _old, _files = setup
    with pytest.raises(ValueError, match="aliases"):
        policy.stage(req, store.root, target, target)
