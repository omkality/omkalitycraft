import gzip
import json
from types import SimpleNamespace

import pytest

from launcher.nbt import Tag, write_nbt
from omk.backups import ftb_restore_authority as ftb
from omk.backups.offsite_process import OffsiteError
from omk.distribution import component_archive as archive
from omk.game import project_policy as policy
from omk.owner.storage import project_stage as raw
from omk.worlds.linux_restore_policy import RANKS
from tests.fixtures.unit.game.project_policy import (
    NEW_SECRET,
    OLD_SECRET,
    prepared,
    properties,
)

__all__ = ["NEW_SECRET", "OLD_SECRET", "prepared", "properties"]


def plan(p):
    return policy.plan(
        p.source, p.target, p.current, raw_expected=p.raw, adapter=policy.ADAPTER
    )


def test_old_progress_and_mods_keep_current_access_credentials_and_authority(prepared):
    p = prepared
    expected = plan(p)
    before = {x.name: archive.digest(x) for x in p.source.iterdir()}
    result = policy.stage(
        p.source, p.target, p.current, raw_expected=p.raw, expected=expected
    )
    game = p.target / raw.GAME
    assert (game / "mods/versioned.jar").read_bytes() == b"selected old mod"
    assert (game / "lab-world/progress.dat").read_bytes() == b"historical progress"
    assert (
        game / "lab-world/data/ftb_lib/teams/claimedchunks/base.dat"
    ).read_bytes() == b"historical claimed chunks"
    restored = ftb.read_staged(game, world_name="lab-world")
    assert not restored["teams/base.dat"]["Players"].value
    assert (
        restored["players/owner.dat"]["Data"].value["ftbutilities"].value["Homes"]
        == p.old["players/owner.dat"]["Data"].value["ftbutilities"].value["Homes"]
    )
    assert (game / "ops.json").read_text() == "[]"
    assert json.loads((game / "banned-players.json").read_bytes()) == [
        {"name": "guest"}
    ]
    assert (game / RANKS).read_bytes() == b"current ranks"
    props = (game / "server.properties").read_text()
    assert (
        NEW_SECRET in props
        and OLD_SECRET not in props
        and "white-list=true" in props
        and "motd=selected" in props
    )
    assert (
        result["current_policy_reconciled"]
        and not result["boot_allowed"]
        and not result["ready_for_players"]
    )
    assert policy.verify(
        p.source, p.target, p.current, raw_expected=p.raw, expected=expected
    )["verified"]
    assert before == {x.name: archive.digest(x) for x in p.source.iterdir()}
    assert (
        NEW_SECRET not in json.dumps(expected)
        and NEW_SECRET not in (p.target / policy.DONE).read_text()
    )
    with pytest.raises((ValueError, OffsiteError)):
        raw.verify(p.source, p.target, expected=p.raw)


@pytest.mark.parametrize("fault", ["op", "jar", "identity", "unknown_field", "props"])
def test_unreviewed_current_state_refuses_before_policy_writes(prepared, fault):
    p = prepared
    if fault == "op":
        (p.current / "ops.json").write_text('[{"name":"op"}]')
    elif fault == "jar":
        (p.current / "mods" / next(iter(ftb.PINS))).write_bytes(b"unknown version")
    elif fault in {"identity", "unknown_field"}:
        path = p.current / "lab-world/data/ftb_lib/teams/base.dat"
        r = ftb.nbt(path.read_bytes())
        r["UID" if fault == "identity" else "UnexpectedPermission"] = (
            Tag(2, 42) if fault == "identity" else Tag(1, 1)
        )
        path.write_bytes(gzip.compress(write_nbt("", r), mtime=0))
    else:
        (p.current / "server.properties").write_bytes(
            properties(NEW_SECRET) + b"online-mode=false\n"
        )
    with pytest.raises(ValueError):
        plan(p)
    assert not (p.target / policy.PLAN).exists()
    assert raw.verify(p.source, p.target, expected=p.raw)["verified"]


def test_current_change_after_plan_refuses_before_write(prepared):
    p = prepared
    expected = plan(p)
    (p.current / RANKS).write_bytes(b"changed current ranks")
    with pytest.raises(ValueError):
        policy.stage(
            p.source, p.target, p.current, raw_expected=p.raw, expected=expected
        )
    assert not (p.target / policy.PLAN).exists()


def test_partial_overlay_refuses_all_retry_and_raw_fallback(prepared, monkeypatch):
    p = prepared
    expected = plan(p)
    original = policy.shared.os.replace

    def interrupted(a, b):
        original(a, b)
        raise OSError("simulated interruption")

    monkeypatch.setattr(policy.shared.os, "replace", interrupted)
    with pytest.raises(OSError):
        policy.stage(
            p.source, p.target, p.current, raw_expected=p.raw, expected=expected
        )
    assert not (p.target / policy.DONE).exists()
    for action in (policy.stage, policy.verify):
        with pytest.raises(ValueError):
            action(p.source, p.target, p.current, raw_expected=p.raw, expected=expected)
    with pytest.raises((ValueError, OffsiteError)):
        raw.verify(p.source, p.target, expected=p.raw)


def test_response_loss_after_receipt_recovers_readonly(prepared, monkeypatch):
    p = prepared
    expected = plan(p)
    original = policy.write_record

    def interrupted(path, value):
        original(path, value)
        if path.name == policy.DONE:
            raise OSError("lost response")

    monkeypatch.setattr(policy, "write_record", interrupted)
    with pytest.raises(OSError):
        policy.stage(
            p.source, p.target, p.current, raw_expected=p.raw, expected=expected
        )
    assert policy.verify(
        p.source, p.target, p.current, raw_expected=p.raw, expected=expected
    )["verified"]


def test_low_space_prevents_any_policy_attempt(prepared, monkeypatch):
    p = prepared
    expected = plan(p)
    monkeypatch.setattr(policy.shutil, "disk_usage", lambda _: SimpleNamespace(free=0))
    with pytest.raises(OSError):
        policy.stage(
            p.source, p.target, p.current, raw_expected=p.raw, expected=expected
        )
    assert not (p.target / policy.PLAN).exists()


@pytest.mark.parametrize("fault", ["foreign_root", "dirty_staging", "current_changed"])
def test_changes_during_overlay_prevent_completion(prepared, monkeypatch, fault):
    p = prepared
    expected = plan(p)
    original = policy.shared.write_payload

    def changed(*args):
        original(*args)
        if fault == "foreign_root":
            (p.target / "foreign").write_bytes(b"keep")
        elif fault == "dirty_staging":
            (p.target / policy.WRITING / "foreign").write_bytes(b"keep")
        else:
            (p.current / RANKS).write_bytes(b"changed current authority")

    monkeypatch.setattr(policy.shared, "write_payload", changed)
    with pytest.raises(ValueError):
        policy.stage(
            p.source, p.target, p.current, raw_expected=p.raw, expected=expected
        )
    assert not (p.target / policy.DONE).exists()


@pytest.mark.parametrize(
    "fault", ["grant", "old_secret", "progress", "jar", "receipt", "current", "foreign"]
)
def test_late_changes_refuse_without_repair(prepared, fault):
    p = prepared
    expected = plan(p)
    policy.stage(p.source, p.target, p.current, raw_expected=p.raw, expected=expected)
    g = p.target / raw.GAME
    if fault == "grant":
        (g / "ops.json").write_text('[{"name":"op"}]')
    elif fault == "old_secret":
        (g / "server.properties").write_bytes(properties(OLD_SECRET))
    elif fault == "progress":
        (g / "lab-world/progress.dat").write_bytes(b"new progress")
    elif fault == "jar":
        (g / "mods/versioned.jar").write_bytes(b"different")
    elif fault == "receipt":
        (p.target / policy.DONE).write_text('{"ready_for_players":true}')
    elif fault == "current":
        (p.current / RANKS).write_bytes(b"later authority")
    else:
        (p.target / policy.WRITING / "foreign").write_bytes(b"foreign")
    with pytest.raises((ValueError, OffsiteError)):
        policy.verify(
            p.source, p.target, p.current, raw_expected=p.raw, expected=expected
        )


@pytest.mark.parametrize(
    "fault",
    [
        "duplicate",
        "escaped_key",
        "separator",
        "continuation",
        "offline",
        "rcon_off",
        "short_secret",
        "pvp_off",
        "easy",
        "world",
        "bad_port",
        "same_numeric_ports",
    ],
)
def test_canonical_protected_properties_fail_closed_without_echo(fault):
    current = properties(NEW_SECRET, current=True)
    historical = properties(OLD_SECRET)
    if fault == "duplicate":
        current += b"online-mode=true\n"
    elif fault == "escaped_key":
        current += b"online\\u002dmode=false\n"
    elif fault == "separator":
        current = current.replace(b"online-mode=true", b"online-mode:true")
    elif fault == "continuation":
        current += b"motd=continued\\\n"
    elif fault == "offline":
        current = current.replace(b"online-mode=true", b"online-mode=false")
    elif fault == "rcon_off":
        current = current.replace(b"enable-rcon=true", b"enable-rcon=false")
    elif fault == "short_secret":
        current = current.replace(NEW_SECRET.encode(), b"short")
    elif fault == "pvp_off":
        current = current.replace(b"pvp=true", b"pvp=false")
    elif fault == "easy":
        current = current.replace(b"difficulty=3", b"difficulty=1")
    elif fault == "world":
        current = current.replace(b"level-name=lab-world", b"level-name=other")
    elif fault == "bad_port":
        current = current.replace(b"rcon.port=25575", b"rcon.port=25576")
    else:
        current = current.replace(b"server-port=25576", b"server-port=02576").replace(
            b"rcon.port=25575", b"rcon.port=2576"
        )
    with pytest.raises(ValueError) as error:
        policy.protected_properties(current, historical, "lab-world")
    assert NEW_SECRET not in str(error.value)


def test_protected_properties_keep_selected_gameplay_config_and_current_network():
    current = properties(NEW_SECRET, current=True).replace(
        b"server-port=25576", b"server-port=25586"
    )
    result = policy.protected_properties(current, properties(OLD_SECRET), "lab-world")
    assert (
        b"motd=selected" in result
        and b"server-port=25586" in result
        and NEW_SECRET.encode() in result
    )
