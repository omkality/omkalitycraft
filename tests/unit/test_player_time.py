import hashlib
import json
import os
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest

from omk import (
    player_time as owner,
    player_time_reader as reader,
)
from omk.admin import AdminError

PLAYER = "7d714b9e-996b-4d72-ab5a-f3e38b3ffb26"


@pytest.fixture
def source(tmp_path, monkeypatch):
    root = tmp_path / "server"
    (root / "world/stats").mkdir(parents=True)
    jar = b"only a unit runtime fixture"
    (root / "forge.jar").write_bytes(jar)
    monkeypatch.setattr(
        reader,
        "runtime_pin",
        lambda: {"path": "forge.jar", "sha256": hashlib.sha256(jar).hexdigest()},
    )
    return root


def request(**changes):
    return {"world": "world", "player": PLAYER, "limit_bytes": 4 * 1024**2, **changes}


def stats(source, raw):
    path = source / "world/stats" / (PLAYER + ".json")
    path.write_text(raw, encoding="utf-8")
    return path


def test_saved_ticks_are_nominal_game_time_not_wall_clock_or_lifetime(source):
    path = stats(source, json.dumps({"stat.playOneMinute": 72007, "stat.jump": 9}))
    before = path.read_bytes(), path.stat().st_mtime_ns
    result = reader.read_saved(request(), source)
    assert result["ticks"] == 72007 and result["nominal_seconds_at_20_tps"] == 3600.35
    assert result["wall_clock_seconds"] is None and not result["afk_excluded"]
    assert not result["live_unsaved_ticks_included"]
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before
    assert owner.validate_data(result, PLAYER) == result


def test_missing_and_unrecorded_statistics_are_not_zero(source):
    missing = reader.read_saved(request(), source)
    assert (
        not missing["available"]
        and missing["reason"] == "no_saved_statistics"
        and "ticks" not in missing
    )
    stats(source, '{"stat.jump": 5}')
    absent = reader.read_saved(request(), source)
    assert (
        not absent["available"]
        and absent["reason"] == "statistic_not_recorded"
        and "ticks" not in absent
    )
    stats(source, '{"stat.playOneMinute":0}')
    assert reader.read_saved(request(), source)["ticks"] == 0
    owner.validate_data(missing, PLAYER)
    owner.validate_data(absent, PLAYER)


@pytest.mark.parametrize(
    "raw",
    [
        "[]",
        "not json",
        '{"stat.playOneMinute":true}',
        '{"stat.playOneMinute":1.5}',
        '{"stat.playOneMinute":-1}',
        '{"stat.playOneMinute":2147483648}',
        '{"stat.playOneMinute":null}',
        '{"stat.playOneMinute":3,"stat.playOneMinute":5}',
    ],
)
def test_corrupt_overflowed_or_ambiguous_counter_is_refused(source, raw):
    stats(source, raw)
    with pytest.raises(ValueError):
        reader.read_saved(request(), source)


@pytest.mark.parametrize(
    "change",
    [
        {"world": "../secret"},
        {"player": "../secret"},
        {"player": PLAYER.replace("-", "")},
        {"limit_bytes": True},
        {"limit_bytes": 32 * 1024**2},
        {"limit_bytes": 1},
        {"extra": "secret"},
    ],
)
def test_paths_and_input_bounds_are_allowlisted(source, change):
    with pytest.raises(ValueError):
        reader.read_saved(request(**change), source)


def test_statistics_oversize_and_runtime_mismatch_fail_closed(source):
    stats(source, "x" * (1024**2 + 1))
    with pytest.raises(ValueError, match="oversized"):
        reader.read_saved(request(limit_bytes=1024**2), source)
    (source / "forge.jar").write_bytes(b"different runtime")
    with pytest.raises(ValueError, match="runtime mismatch"):
        reader.read_saved(request(), source)


@pytest.mark.parametrize(
    "relative", ["forge.jar", "world/stats", "world/stats/" + PLAYER + ".json"]
)
def test_linked_input_is_rejected(source, tmp_path, relative):
    if os.name == "nt":
        pytest.skip("Linux symlink controls")
    path = source / relative
    if path.is_dir():
        path.rmdir()
        outside = tmp_path / "outside-dir"
        outside.mkdir()
        path.symlink_to(outside, target_is_directory=True)
    else:
        path.unlink(missing_ok=True)
        outside = tmp_path / "outside"
        outside.write_bytes(b"external-secret")
        path.symlink_to(outside)
    with pytest.raises(ValueError):
        reader.read_saved(request(), source)


@pytest.mark.parametrize(
    "env",
    [
        {"OMK_PLAYTIME_INPUT_MIB": "0"},
        {"OMK_PLAYTIME_INPUT_MIB": "17"},
        {"OMK_PLAYTIME_TIMEOUT_SECONDS": "4"},
        {"OMK_PLAYTIME_TIMEOUT_SECONDS": "121"},
        {"OMK_PLAYTIME_INPUT_MIB": "secret-value"},
    ],
)
def test_invalid_owner_settings_do_not_echo_values(env):
    with pytest.raises(AdminError) as caught:
        owner.settings(env)
    assert "secret-value" not in str(caught.value)


def test_example_environment_matches_defaults():
    example = owner.PROJECT_ROOT / "deploy/player-time.example.env"
    env = dict(
        line.split("=", 1)
        for line in example.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
    )
    assert (
        owner.settings(env)
        == owner.settings({})
        == {
            "input_mib": 4,
            "timeout_seconds": 30,
        }
    )


@pytest.fixture
def controller(tmp_path, monkeypatch):
    cfg = SimpleNamespace(private=tmp_path)
    monkeypatch.setattr(owner.backups, "local_engine", lambda: None)
    monkeypatch.setattr(
        owner.backups, "target_for", lambda *a: {"release": "dj2-candidate"}
    )
    monkeypatch.setattr(owner.maintenance, "binding", lambda *a: {})
    state = {"running": True, "identity": "stable"}
    monkeypatch.setattr(owner.maintenance, "snapshot", lambda *a: dict(state))
    worker = Mock(
        return_value={
            "schema": 1,
            "player_uuid": PLAYER,
            "source": "forge112_saved_stat_play_one_minute",
            "available": False,
            "reason": "no_saved_statistics",
        }
    )
    monkeypatch.setattr(owner, "_worker", worker)
    return cfg, state, worker


def test_read_uses_existing_binding_without_auth_or_source_writes(controller):
    cfg, _, worker = controller
    result = owner.saved_playtime(cfg, "dj2", PLAYER, {})
    assert result["ok"] and not result["available"] and result["snapshot_dependent"]
    assert not result["account_lifetime"] and result["running"]
    assert worker.call_count == 1
    assert list(cfg.private.iterdir()) == [cfg.private / "backups.lock"]


def test_source_lifecycle_change_refuses_a_mixed_result(controller):
    cfg, state, worker = controller

    def changed(*args):
        state["identity"] = "new"
        return {"available": False}

    worker.side_effect = changed
    with pytest.raises(AdminError, match="changed"):
        owner.saved_playtime(cfg, "dj2", PLAYER, {})


def test_bad_player_uuid_never_enters_helper(controller):
    cfg, _, worker = controller
    with pytest.raises(AdminError):
        owner.saved_playtime(cfg, "dj2", "nickname-or-secret", {})
    worker.assert_not_called()


@pytest.mark.parametrize(
    "change",
    [
        {"player_uuid": str(uuid4())},
        {"available": 0},
        {"reason": "unknown"},
        {"ticks": 0},
        {"secret": "never forward"},
    ],
)
def test_worker_identity_and_unknown_fields_are_not_forwarded(change):
    data = {
        "schema": 1,
        "player_uuid": PLAYER,
        "source": "forge112_saved_stat_play_one_minute",
        "available": False,
        "reason": "no_saved_statistics",
        **change,
    }
    with pytest.raises(AdminError):
        owner.validate_data(data, PLAYER)


def test_read_detects_a_file_change_without_modifying_it(source, monkeypatch):
    path = stats(source, '{"stat.playOneMinute":100}')
    before = path.read_bytes()
    actual = reader.os.fstat
    calls = 0

    def changing(fd):
        nonlocal calls
        result = actual(fd)
        calls += 1
        return SimpleNamespace(
            st_dev=result.st_dev,
            st_ino=result.st_ino,
            st_size=result.st_size,
            st_mtime_ns=result.st_mtime_ns + (calls > 1),
        )

    monkeypatch.setattr(reader.os, "fstat", changing)
    with pytest.raises(ValueError, match="changed"):
        reader.read_saved(request(), source)
    assert path.read_bytes() == before


@pytest.fixture
def transport(monkeypatch):
    calls = []
    state = {}
    data = {
        "schema": 1,
        "player_uuid": PLAYER,
        "source": "forge112_saved_stat_play_one_minute",
        "available": False,
        "reason": "no_saved_statistics",
    }

    def docker(*args, **kwargs):
        calls.append((args, kwargs))
        if args[0] == "run":
            label = args[args.index("--label") + 1]
            state["operation"] = label.split("=", 1)[1]
            if state.get("timeout"):
                raise AdminError("helper timeout")
            return state.get("response", json.dumps({"ok": True, "data": data}))
        if args[0] == "inspect":
            return json.dumps(
                [
                    {
                        "Id": "a" * 64,
                        "Config": {
                            "Image": owner.backups.IMAGE,
                            "Labels": {
                                owner.LABEL: state.get("owner", state["operation"])
                            },
                        },
                    }
                ]
            )
        return ""

    monkeypatch.setattr(owner.backups, "docker", docker)
    return calls, state, data


def test_helper_has_only_readonly_source_and_code_mounts_and_is_removed(transport):
    calls, _, data = transport
    assert (
        owner._worker(
            {"world": "world", "data_volume": "owned-data"},
            PLAYER,
            owner.settings({}),
            {"helper_memory_mib": 128, "helper_cpus": 1},
        )
        == data
    )
    args, kwargs = calls[0]
    assert args[args.index("--network") + 1] == "none"
    assert "--read-only" in args and "ALL" in args and "no-new-privileges:true" in args
    mounts = [args[i + 1] for i, a in enumerate(args) if a == "--mount"]
    assert len(mounts) == 3 and all(m.endswith(",readonly") for m in mounts)
    assert "target=/server,readonly" in mounts[0]
    assert json.loads(kwargs["stdin"]) == request()
    assert calls[-1][0] == ("rm", "--force", "a" * 64)


def test_timeout_still_removes_only_the_owned_helper(transport):
    calls, state, _ = transport
    state["timeout"] = True
    with pytest.raises(AdminError, match="timeout"):
        owner._worker(
            {"world": "world", "data_volume": "owned-data"},
            PLAYER,
            owner.settings({}),
            {"helper_memory_mib": 128, "helper_cpus": 1},
        )
    assert calls[-1][0] == ("rm", "--force", "a" * 64)


def test_cleanup_never_removes_a_foreign_helper(transport):
    calls, state, _ = transport
    state["owner"] = "foreign"
    with pytest.raises(AdminError, match="ownership"):
        owner._worker(
            {"world": "world", "data_volume": "owned-data"},
            PLAYER,
            owner.settings({}),
            {"helper_memory_mib": 128, "helper_cpus": 1},
        )
    assert not any(args[0] == "rm" for args, _ in calls)


@pytest.mark.parametrize(
    "response", ["x" * 16385, "[]", '{"ok":false,"error_type":"private secret"}']
)
def test_bad_or_oversized_worker_reply_is_not_forwarded_and_is_cleaned(
    transport, response
):
    calls, state, _ = transport
    state["response"] = response
    with pytest.raises(AdminError) as caught:
        owner._worker(
            {"world": "world", "data_volume": "owned-data"},
            PLAYER,
            owner.settings({}),
            {"helper_memory_mib": 128, "helper_cpus": 1},
        )
    assert "private secret" not in str(caught.value)
    assert calls[-1][0] == ("rm", "--force", "a" * 64)
