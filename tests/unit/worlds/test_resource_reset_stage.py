import shutil
import threading
import zipfile
from concurrent.futures import ThreadPoolExecutor

import pytest

from launcher.nbt import Tag
from omk.backups.backup_store import BackupStore
from omk.backups.stopped_world_backup import inventory
from omk.worlds.reset import (
    resource_reset_stage as stage,
    rftools_reset as rftools,
)
from tests.fixtures.unit.backups.ftb_restore_authority import records
from tests.fixtures.unit.worlds.resource_reset_inventory import (
    encoded,
    rftools_registry,
    sample,
)
from tests.fixtures.unit.worlds.resource_reset_stage import LIMITS, data, rftools_data

__all__ = ["LIMITS", "data", "records", "rftools_data", "rftools_registry", "sample"]


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


@pytest.mark.parametrize(
    ("landing_found", "unhandled_links", "opaque_records", "reason"),
    [
        (True, 1, 0, "world_links"),
        (True, 0, 1, "opaque_records"),
        (False, 0, 0, "no_landing"),
    ],
)
def test_auto_stage_reports_preflight_refusal_before_write(
    data, monkeypatch, landing_found, unhandled_links, opaque_records, reason
):
    request, source, storage, target, before = data
    monkeypatch.setattr(
        stage.resource_reset_preflight,
        "preflight",
        lambda *a, **k: {
            "can_stage_data": False,
            "landing": {"found": landing_found},
            "links": {
                "unhandled_finding_count": unhandled_links,
                "opaque_record_count": opaque_records,
            },
        },
    )
    with pytest.raises(ValueError) as rejected:
        stage.execute(
            {**request, "position": "auto", "action": "plan"}, source, storage, target
        )
    assert getattr(rejected.value, "reason", None) == reason
    assert not list(target.iterdir())
    assert (
        inventory(source / "world", world_name="world", path_policy="linux-server")
        == before
    )


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


@pytest.mark.parametrize("fresh", [True, False])
def test_main_world_reset_removes_all_progress_from_the_verified_backup(data, fresh):
    request, source, storage, target, before = data
    request.update(
        position="auto",
        dimension=0,
        reset=stage.dimension_reset.layout(0, all_worlds=True, fresh=fresh),
    )
    plan = stage.execute({**request, "action": "plan"}, source, storage, target)
    assert plan["retained_files"] == (0 if fresh else 1)
    expected = {**request, "expected": plan}
    written = stage.execute({**expected, "action": "stage"}, source, storage, target)
    assert (
        stage.execute({**expected, "action": "verify"}, source, storage, target)
        == written
    )
    after = inventory(
        target / "world",
        world_name="world",
        path_policy="linux-server",
        allow_empty=fresh,
    )
    assert after == ({} if fresh else {"world/level.dat": before["world/level.dat"]})
    assert (
        inventory(source / "world", world_name="world", path_policy="linux-server")
        == before
    )


def test_new_resource_seed_is_sealed_with_the_new_world_and_ownership(data):
    request, source, storage, target, _ = data
    world = source / "world"
    metadata = world / "DIM-18000/jed_level.dat"
    markers = [
        world / "omk-resource-world.properties",
        world / "DIM-18000/.omk-resource.properties",
    ]
    previous = int(
        next(
            line[5:]
            for line in markers[0].read_text().splitlines()
            if line.startswith("seed=")
        )
    )
    encoded(metadata, {"Data": Tag(10, {"RandomSeed": Tag(4, previous)})})
    before = inventory(world, world_name="world", path_policy="linux-server")
    archive = source.parent / "seed-reset.zip"
    with zipfile.ZipFile(archive, "w") as output:
        for name in before:
            output.write(source / name, name)
    store = BackupStore(storage / "store", LIMITS, path_policy="linux-server")
    request.update(snapshot=store.publish(archive, before)["id"], reroll_seed=True)
    expected = stage.execute({**request, "action": "plan"}, source, storage, target)
    request["expected"] = expected
    staged = stage.execute({**request, "action": "stage"}, source, storage, target)
    assert (
        stage.execute({**request, "action": "verify"}, source, storage, target)
        == staged
    )
    seed = (
        stage.audit.ftb.nbt((target / metadata.relative_to(source)).read_bytes())[
            "Data"
        ]
        .value["RandomSeed"]
        .value
    )
    assert seed != previous
    for path in markers:
        assert f"seed={seed}\n" in (target / path.relative_to(source)).read_text()
    assert not (target / "world/DIM-18000/region").exists()
    assert inventory(world, world_name="world", path_policy="linux-server") == before


def test_rftools_candidate_reseeds_only_the_selected_dimension_and_preserves_progress(
    rftools_data, monkeypatch
):
    request, source, storage, target, before, player = rftools_data
    monkeypatch.setattr(
        stage.resource_reset_preflight,
        "preflight",
        lambda *a, **k: {
            "can_stage_data": True,
            "landing": {"position": [8, 100, 8]},
            "adapters": {rftools.ADAPTER: {"artifact_sha256": rftools.SHA256}},
        },
    )
    plan = stage.execute({**request, "action": "plan"}, source, storage, target)
    sealed = {**request, "expected": plan}
    staged = stage.execute({**sealed, "action": "stage"}, source, storage, target)
    assert (
        stage.execute({**sealed, "action": "verify"}, source, storage, target) == staged
    )
    assert not (target / "world/RFTOOLS6200").exists()
    world = source / "world"
    assert inventory(world, world_name="world", path_policy="linux-server") == before

    _, _, original = stage.audit._rftools_registry(source, "world")
    registry_name = "world/" + stage.audit.RFTOOLS_REGISTRY
    candidate = stage.audit.ftb.nbt((target / registry_name).read_bytes())
    rows = {
        v["id"].value: v
        for v in stage.audit._list(candidate["data"].value, "dimensions", 10)
    }
    assert rows[6201] == original[6201]
    expected = {**original[6200], "forcedSeed": Tag(4, 2686034)}
    del expected["spawnPoint"]
    assert rows[6200] == expected

    receiver_name = "world/" + stage.audit.RFTOOLS_DESTINATIONS
    old_receivers = stage.audit.ftb.nbt((source / receiver_name).read_bytes())["data"]
    new_receivers = stage.audit.ftb.nbt((target / receiver_name).read_bytes())["data"]
    assert new_receivers.value["lastId"] == old_receivers.value["lastId"]
    assert (
        new_receivers.value["destinations"].value[1]
        == old_receivers.value["destinations"].value[1][1:2]
    )

    staged_player = stage.audit.ftb.nbt(
        (target / player.relative_to(source)).read_bytes()
    )
    original_player = stage.audit.ftb.nbt(player.read_bytes())
    assert staged_player["Dimension"] == Tag(3, 0)
    new_stacks = staged_player["Inventory"].value[1]
    old_stacks = original_player["Inventory"].value[1]
    assert new_stacks[0] == old_stacks[0]
    assert new_stacks[1].value == {
        **old_stacks[1].value,
        "tag": Tag(10, {"Energy": Tag(3, 650000), "target1": Tag(3, 8)}),
    }
    alt_player = stage.audit.ftb.nbt(
        (target / player.with_suffix(".dat_old").relative_to(source)).read_bytes()
    )
    assert alt_player == staged_player
    assert staged_player["XpTotal"] == original_player["XpTotal"]
    changed = {
        registry_name,
        receiver_name,
        player.relative_to(source).as_posix(),
        player.with_suffix(".dat_old").relative_to(source).as_posix(),
    }
    after = inventory(target / "world", world_name="world", path_policy="linux-server")
    assert changed <= after.keys() and changed <= before.keys()
    assert {key: value for key, value in after.items() if key not in changed} == {
        key: value
        for key, value in before.items()
        if key not in changed and not key.startswith("world/RFTOOLS6200/")
    }


def test_rftools_candidate_refuses_a_stale_selection_before_writing(rftools_data):
    request, source, storage, target, _files, _player = rftools_data
    request["reset"]["rftools_identity"] = "b" * 64
    with pytest.raises(ValueError, match="selected RFTools dimension changed"):
        stage.execute({**request, "action": "plan"}, source, storage, target)
    assert not list(target.iterdir())


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
