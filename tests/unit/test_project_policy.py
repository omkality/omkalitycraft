import copy
import gzip
import hashlib
import json
import shutil
import zipfile
from types import SimpleNamespace

import pytest

from launcher.nbt import Tag, write_nbt
from omk import (
    component_archive as archive,
    ftb_restore_authority as ftb,
    project_export,
    project_policy as policy,
    project_stage as raw,
)
from omk.linux_restore_policy import LISTS, RANKS
from omk.offsite_process import OffsiteError
from tests.unit.test_linux_restore_policy import records
from tests.unit.test_project_export import fixture as capture_fixture

OLD_SECRET = "old-rcon-fixture-password-123456"
NEW_SECRET = "current-rcon-fixture-password-654321"


def properties(secret, *, current=False):
    return (
        "level-name=lab-world\nonline-mode=true\nwhite-list="
        + ("true" if current else "false")
        + "\nserver-ip=\nserver-port=25576\nenable-rcon=true\nrcon.port=25575\nrcon.password="
        + secret
        + "\npvp=true\ndifficulty=3\nmax-players=20\nmotd="
        + ("current" if current else "selected")
        + "\n"
    ).encode()


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    base = capture_fixture.__wrapped__(tmp_path)
    game, world = base.args["game"], base.args["game"] / "lab-world"
    old = records("owner")
    for name, value in old.items():
        path = world / "data/ftb_lib" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(gzip.compress(write_nbt("", value), mtime=0))
    claims = world / "data/ftb_lib/teams/claimedchunks/base.dat"
    claims.parent.mkdir(parents=True, exist_ok=True)
    claims.write_bytes(b"historical claimed chunks")
    (world / "progress.dat").write_bytes(b"historical progress")
    (game / "mods").mkdir()
    pins = {n: hashlib.sha256(n.encode()).hexdigest() for n in ftb.PINS}
    for name in pins:
        (game / "mods" / name).write_bytes(name.encode())
    monkeypatch.setattr(ftb, "PINS", pins)
    (game / "mods/versioned.jar").write_bytes(b"selected old mod")
    for name in LISTS:
        (game / name).write_text("[]")
    (game / "ops.json").write_text('[{"name":"historical-op"}]')
    (game / RANKS).parent.mkdir(parents=True)
    (game / RANKS).write_bytes(b"old ranks")
    (game / "server.properties").write_bytes(properties(OLD_SECRET))
    current = tmp_path / "current"
    shutil.copytree(game, current)
    (current / "server.properties").write_bytes(properties(NEW_SECRET, current=True))
    (current / "ops.json").write_text("[]")
    (current / "banned-players.json").write_text('[{"name":"guest"}]')
    (current / RANKS).write_bytes(b"current ranks")
    (current / "mods/versioned.jar").write_bytes(b"newer mod being rolled back")
    now = copy.deepcopy(old)
    now["teams/base.dat"]["Players"].value.clear()
    now["players/owner.dat"]["Data"].value["ftbutilities"].value["Homes"].value.clear()
    for name, value in now.items():
        (current / "lab-world/data/ftb_lib" / name).write_bytes(
            gzip.compress(write_nbt("", value), mtime=0)
        )
    with zipfile.ZipFile(base.args["world_zip"], "w", zipfile.ZIP_DEFLATED) as z:
        for p in world.rglob("*"):
            if p.is_file():
                z.write(p, p.relative_to(game).as_posix())
    files = project_export.world_inventory(
        world, world_name="lab-world", path_policy="linux-server"
    )
    base.args["world_json"].unlink()
    archive.json_write(
        base.args["world_json"],
        {
            "schema": 1,
            "sequence": 1,
            "sha256": archive.digest(base.args["world_zip"]),
            "bytes": base.args["world_zip"].stat().st_size,
            "files": files,
        },
    )
    export = project_export.capture(
        base.out,
        release_context={
            "source_commit": "1" * 40,
            "client_manifests": {"windows-x64": "2" * 64},
            "declared_state_contract": "fixture-v1",
        },
        **base.args,
    )
    target = tmp_path / "candidate"
    target.mkdir(mode=0o700)
    expected = raw.plan(
        base.out,
        target,
        operation="d" * 32,
        world="lab-world",
        selection={
            "project_sha256": archive.digest(base.out / "project.json"),
            "release_identity": export["manifest"]["release_identity"],
        },
        settings=base.args["settings"],
    )
    raw.stage(base.out, target, expected=expected)
    return SimpleNamespace(
        source=base.out, target=target, current=current, raw=expected, old=old
    )


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
