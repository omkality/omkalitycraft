import shutil
import threading
import zipfile
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest

from launcher.nbt import Tag
from omk import resource_reset_stage as stage
from omk.backup_store import BackupPolicy, BackupStore
from omk.stopped_world_backup import inventory
from tests.unit.test_resource_reset_inventory import (
    encoded,
    records as records,  # noqa: PLC0414 -- explicit shared pytest fixture export
    sample as sample,  # noqa: PLC0414 -- explicit shared pytest fixture export
)

LIMITS = BackupPolicy(32 * 1024**2, 3, 16 * 1024**2, 1)


def test_auto_stage_receives_frozen_owner_preflight_options(data, monkeypatch):
    request, source, storage, target, _ = data
    options = stage.resource_reset_preflight.settings({"OMK_RESET_LANDING_RADIUS": "7"})

    def preflight(*args, **kwargs):
        assert kwargs["options"] is not None
        return {
            "can_stage_data": True,
            "landing": {"position": [8, 100, 8]},
            "policy": dict(kwargs["options"]),
        }

    monkeypatch.setattr(stage.resource_reset_preflight, "preflight", preflight)
    request.update(action="plan", position="auto", preflight_options=options)
    expected = stage.execute(request, source, storage, target)
    assert expected["preflight"]["policy"]["landing_radius"] == 7
    changed = {
        **request,
        "action": "stage",
        "expected": expected,
        "preflight_options": {**options, "landing_radius": 8},
    }
    with pytest.raises(ValueError, match="changed"):
        stage.execute(changed, source, storage, target)
    assert not list(target.iterdir())


@pytest.mark.parametrize("bad", [{}, {"landing_radius": True}])
def test_invalid_preflight_options_are_refused_before_target_write(data, bad):
    request, source, storage, target, _ = data
    with pytest.raises(ValueError):
        stage.execute(
            {**request, "action": "plan", "position": "auto", "preflight_options": bad},
            source,
            storage,
            target,
        )
    assert not list(target.iterdir())


def test_auto_point_is_frozen_in_plan_and_changed_preflight_refuses_stage(
    data, monkeypatch
):
    request, source, storage, target, _ = data
    proof = {
        "can_stage_data": True,
        "landing": {"position": [12, 100, 15]},
        "policy": {"radius": 16},
    }
    monkeypatch.setattr(
        stage.resource_reset_preflight, "preflight", lambda *a, **k: proof.copy()
    )
    request.update(position="auto", action="plan")
    plan = stage.execute(request, source, storage, target)
    assert plan["position"] == [12, 100, 15] and plan["landing_geometry_verified"]
    assert not plan["landing_verified"] and not plan["ready_for_start"]
    proof["policy"] = {"radius": 8}
    with pytest.raises(ValueError, match="changed"):
        stage.execute(
            {**request, "action": "stage", "expected": plan}, source, storage, target
        )
    assert not list(target.iterdir())


def test_auto_stage_refuses_unknown_portals_or_no_safe_point_before_write(
    data, monkeypatch
):
    request, source, storage, target, _ = data
    monkeypatch.setattr(
        stage.resource_reset_preflight,
        "preflight",
        lambda *a, **k: {"can_stage_data": False},
    )
    with pytest.raises(ValueError, match="known mod links"):
        stage.execute(
            {**request, "position": "auto", "action": "plan"}, source, storage, target
        )
    assert not list(target.iterdir())


@pytest.fixture
def data(sample, tmp_path, monkeypatch):
    server, world, entity, player, _records = sample
    (server / "server.properties").write_text("level-name=world\n")
    (world / "DIM-18000/region").mkdir()
    (world / "DIM-18000/region/r.0.0.mca").write_bytes(b"old-resource")
    (world / "region").mkdir()
    (world / "region/r.0.0.mca").write_bytes(b"keep-main-base")
    (world / "betterquesting").mkdir()
    (world / "betterquesting/QuestProgress.json").write_bytes(
        b'{"keep":"quest-progress"}'
    )
    (world / "stats").mkdir()
    (world / "stats" / (player.stem + ".json")).write_bytes(
        b'{"stat.playOneMinute":72007,"stat.jump":9}'
    )
    entity["ForgeData"] = Tag(
        10,
        {
            "PlayerPersisted": Tag(
                10,
                {
                    "omkality_guide": Tag(
                        10,
                        {
                            "last_auto": Tag(4, 1794560000),
                            "last_help": Tag(4, 1794560001),
                        },
                    )
                },
            )
        },
    )
    encoded(player, entity)
    encoded(player.with_suffix(".dat_old"), entity)
    storage, target = tmp_path / "backup", tmp_path / "candidate"
    storage.mkdir()
    target.mkdir()
    store = BackupStore.create(storage / "store", LIMITS, path_policy="linux-server")
    files = inventory(world, world_name="world", path_policy="linux-server")
    archive = tmp_path / "fresh.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as out:
        for name in files:
            out.write(server / name, name)
    snapshot = store.publish(archive, files)
    request = {
        "schema": 1,
        "operation": uuid4().hex,
        "world": "world",
        "dimension": -18000,
        "position": [8, 100, 8],
        "snapshot": snapshot["id"],
        "world_max_bytes": 8 * 1024**2,
        "policy": vars(LIMITS),
    }
    monkeypatch.setattr(stage.sys, "platform", "linux")
    return request, server, storage, target, files


def planned(data):
    request, source, storage, target, files = data
    plan = stage.execute({**request, "action": "plan"}, source, storage, target)
    return {**request, "expected": plan}, source, storage, target, files


def test_fresh_backup_plan_stage_verify_preserve_source_and_all_other_world_files(data):
    request, source, storage, target, before = planned(data)
    assert not list(target.iterdir())
    assert request["expected"]["omitted_files"] == 3
    assert (
        not request["expected"]["ready_for_start"]
        and not request["expected"]["landing_verified"]
    )
    result = stage.execute({**request, "action": "stage"}, source, storage, target)
    assert result["staged"] and not result["promoted"] and not result["ready_for_start"]
    assert (
        stage.execute({**request, "action": "verify"}, source, storage, target)
        == result
    )
    assert (
        inventory(source / "world", world_name="world", path_policy="linux-server")
        == before
    )
    after = inventory(target / "world", world_name="world", path_policy="linux-server")
    assert not any(n.startswith("world/DIM-18000/") for n in after)
    stats = [name for name in before if name.startswith("world/stats/")]
    assert len(stats) == 1
    assert (target / stats[0]).read_bytes() == (source / stats[0]).read_bytes()
    assert "world/omk-resource-world.properties" not in after
    for name in (
        "world/level.dat",
        "world/region/r.0.0.mca",
        "world/betterquesting/QuestProgress.json",
    ):
        assert after[name] == before[name]
    for name in before:
        if name.endswith((".dat", ".dat_old")) and "/playerdata/" in name:
            nbt = stage.audit.ftb.nbt((target / name).read_bytes())
            assert nbt["Dimension"].value == 0
            guide = (
                nbt["ForgeData"].value["PlayerPersisted"].value["omkality_guide"].value
            )
            assert guide["last_auto"] == Tag(4, 1794560000)
            assert guide["last_help"] == Tag(4, 1794560001)
    with pytest.raises(ValueError, match="empty target"):
        stage.execute({**request, "action": "stage"}, source, storage, target)


@pytest.mark.parametrize(
    "change",
    ["world", "runtime", "position", "policy", "snapshot", "foreign", "target", "plan"],
)
def test_drift_is_refused_before_first_candidate_write(data, change):
    request, source, storage, target, _files = planned(data)
    if change == "world":
        (source / "world/region/r.0.0.mca").write_bytes(b"new-player-work")
    elif change == "runtime":
        (source / "server.properties").write_text("changed=true\n")
    elif change == "position":
        request["position"] = [9, 100, 8]
    elif change == "policy":
        request["policy"] = {**request["policy"], "max_count": 4}
    elif change == "snapshot":
        request["snapshot"] = "snapshot-" + "0" * 32
    elif change == "foreign":
        (storage / "incoming.zip").write_bytes(b"unfinished")
    elif change == "target":
        (target / "foreign.dat").write_bytes(b"keep")
    else:
        request["expected"] = {**request["expected"], "changed_files": -1}
    with pytest.raises((ValueError, OSError)):
        stage.execute({**request, "action": "stage"}, source, storage, target)
    assert not (target / stage.PLAN).exists()


@pytest.mark.parametrize("budget", ["reserve", "staging"])
def test_space_failure_never_initializes_candidate(data, monkeypatch, budget):
    request, source, storage, target, _files = data
    if budget == "staging":
        request["policy"] = {**request["policy"], "staging_bytes": 1}
    else:
        monkeypatch.setattr(
            stage.shutil, "disk_usage", lambda _: shutil._ntuple_diskusage(1000, 999, 1)
        )
    with pytest.raises((OSError, ValueError)):
        stage.execute({**request, "action": "plan"}, source, storage, target)
    assert not list(target.iterdir())


def test_partial_copy_cannot_be_retried_or_verified_as_complete(data, monkeypatch):
    request, source, storage, target, _files = planned(data)
    before = inventory(source / "world", world_name="world", path_policy="linux-server")
    original = stage._copy

    def fail(*args):
        original(*args)
        raise OSError("Injected ENOSPC")

    monkeypatch.setattr(stage, "_copy", fail)
    with pytest.raises(OSError, match="ENOSPC"):
        stage.execute({**request, "action": "stage"}, source, storage, target)
    assert (target / stage.PLAN).exists() and not (target / stage.DONE).exists()
    with pytest.raises(ValueError, match="empty target"):
        stage.execute({**request, "action": "stage"}, source, storage, target)
    with pytest.raises((ValueError, OSError)):
        stage.execute({**request, "action": "verify"}, source, storage, target)
    assert (
        inventory(source / "world", world_name="world", path_policy="linux-server")
        == before
    )


@pytest.mark.parametrize(
    "tamper", ["player", "base", "receipt", "foreign", "resource-directory"]
)
def test_receipt_never_substitutes_for_verifying_candidate_bytes(data, tamper):
    request, source, storage, target, _files = planned(data)
    stage.execute({**request, "action": "stage"}, source, storage, target)
    if tamper == "player":
        next((target / "world/playerdata").glob("*.dat")).write_bytes(b"tampered")
    elif tamper == "base":
        (target / "world/region/r.0.0.mca").write_bytes(b"tampered")
    elif tamper == "receipt":
        (target / stage.DONE).write_text("{}")
    elif tamper == "foreign":
        (target / "foreign.txt").write_bytes(b"keep")
    else:
        (target / "world/DIM-18000").mkdir()
    with pytest.raises((ValueError, OSError)):
        stage.execute({**request, "action": "verify"}, source, storage, target)


def test_nested_or_aliased_target_is_refused_before_recording_plan(data):
    request, source, storage, _target, _files = data
    target = source / "world/empty-target"
    target.mkdir()
    with pytest.raises(ValueError, match="alias"):
        stage.execute({**request, "action": "plan"}, source, storage, target)
    assert not list(target.iterdir())


def test_concurrent_stage_has_one_writer_and_complete_verified_candidate(
    data, monkeypatch
):
    request, source, storage, target, _files = planned(data)
    barrier = threading.Barrier(2, timeout=15)
    real = stage._json_write

    def synchronized(path, value):
        if path.name == stage.PLAN:
            barrier.wait()
        return real(path, value)

    monkeypatch.setattr(stage, "_json_write", synchronized)

    def execute(_):
        try:
            return stage.execute(
                {**request, "action": "stage"}, source, storage, target
            )
        except FileExistsError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(execute, range(2)))
    assert sum(v is not None for v in results) == 1
    assert (
        stage.execute({**request, "action": "verify"}, source, storage, target)
        in results
    )


@pytest.mark.parametrize("dimension", [0, -1, 7, -9, -18001, True])
def test_only_owned_configured_resource_id_can_reach_staging(data, dimension):
    request, source, storage, target, _files = data
    with pytest.raises(ValueError):
        stage.execute(
            {**request, "action": "plan", "dimension": dimension},
            source,
            storage,
            target,
        )
    assert not list(target.iterdir())
