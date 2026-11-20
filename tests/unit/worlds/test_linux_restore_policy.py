import gzip
import sys

import pytest

from launcher.nbt import Tag, write_nbt
from omk.backups import ftb_restore_authority as ftb
from omk.backups.stopped_world_backup import inventory
from omk.worlds import (
    linux_restore_policy as policy,
    linux_world_restore as raw,
)
from tests.fixtures.unit.worlds.linux_restore_policy import (
    LIMITS,
    build,
    records,
    setup,
)

__all__ = ["LIMITS", "build", "records", "setup"]


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
