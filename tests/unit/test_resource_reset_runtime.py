import copy
import json
import os
import shutil
import sys

import pytest

from omk import (
    resource_reset_runtime as runtime,
    resource_reset_stage as stage,
)
from omk.stopped_world_backup import inventory
from tests.unit.test_resource_reset_inventory import (
    records as records,  # noqa: PLC0414
    sample as sample,  # noqa: PLC0414
)
from tests.unit.test_resource_reset_stage import data as data  # noqa: PLC0414


@pytest.fixture
def prepared(data):
    request, source, storage, target, _ = data
    (source / "server.properties").write_text(
        "level-name=world\nwhite-list=true\nrcon.password=fixture-only\n"
    )
    (source / "eula.txt").write_text("# Already accepted in source\neula=true\n")
    for name in runtime.LISTS:
        (source / name).write_text(
            "[]\n" if name == "ops.json" else '[{"uuid":"fixture"}]\n'
        )
    for name in (
        ".omk/authlib-injector.jar",
        ".omk/log4j2.xml",
        "libraries/logging.jar",
        "local/ftbutilities/ranks.txt",
    ):
        p = source / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"fixture-payload")
    (source / "logs").mkdir()
    (source / "logs/private.log").write_bytes(b"never-copy")
    plan = stage.execute({**request, "action": "plan"}, source, storage, target)
    request = {**request, "expected": plan}
    stage.execute({**request, "action": "stage"}, source, storage, target)
    expected = runtime.execute(
        {**request, "action": "runtime-plan"}, source, storage, target
    )
    return {**request, "runtime_expected": expected}, source, storage, target


def execute(prepared, action):
    request, *paths = prepared
    return runtime.execute({**request, "action": action}, *paths)


def test_full_runtime_exact_access_and_data_are_preserved_without_start(prepared):
    request, source, storage, target = prepared
    source_before = {
        p.relative_to(source).as_posix(): p.read_bytes()
        for p in source.rglob("*")
        if p.is_file()
    }
    world_before = inventory(
        target / "world", world_name="world", path_policy="linux-server"
    )
    receipt = execute(prepared, "runtime-stage")
    assert receipt == execute(prepared, "runtime-verify")
    assert receipt["runtime_prepared"] and not receipt["promoted"]
    assert not receipt["ready_for_start"] and not receipt["ready_for_players"]
    assert source_before == {
        p.relative_to(source).as_posix(): p.read_bytes()
        for p in source.rglob("*")
        if p.is_file()
    }
    assert world_before == inventory(
        target / "world", world_name="world", path_policy="linux-server"
    )
    assert not (target / "logs").exists()
    for name in runtime.files(source, "world"):
        assert (target / name).read_bytes() == (source / name).read_bytes()
    assert json.loads((target / "ops.json").read_bytes()) == []
    assert (target / ".omk/tmp").is_dir() and not list((target / ".omk/tmp").iterdir())
    assert "fixture-only" not in json.dumps(request["runtime_expected"]) + json.dumps(
        receipt
    )
    for action in ("runtime-stage", "runtime-plan"):
        with pytest.raises(ValueError, match="already attempted"):
            runtime.execute(
                {
                    k: v
                    for k, v in {**request, "action": action}.items()
                    if k != "runtime_expected" or action != "runtime-plan"
                },
                source,
                storage,
                target,
            )
    with pytest.raises(ValueError, match="Foreign"):
        stage.execute(
            {
                **{k: v for k, v in request.items() if k != "runtime_expected"},
                "action": "verify",
            },
            source,
            storage,
            target,
        )


@pytest.mark.parametrize(
    "name",
    [
        "mods/ftblib.jar",
        "server.properties",
        "whitelist.json",
        "banned-players.json",
        "eula.txt",
    ],
)
def test_source_runtime_or_policy_drift_refused_before_target_write(prepared, name):
    _, source, _, target = prepared
    # Use an actual pinned runtime entry for the mod drift control.
    if name == "mods/ftblib.jar":
        name = next(
            iter(p.relative_to(source).as_posix() for p in (source / "mods").iterdir())
        )
    with (source / name).open("ab") as stream:
        stream.write(b"\n ")
    before = {
        p.relative_to(target).as_posix(): p.read_bytes()
        for p in target.rglob("*")
        if p.is_file()
    }
    with pytest.raises(ValueError):
        execute(prepared, "runtime-stage")
    assert before == {
        p.relative_to(target).as_posix(): p.read_bytes()
        for p in target.rglob("*")
        if p.is_file()
    }


@pytest.mark.parametrize(
    "name,value",
    [
        ("eula.txt", b"eula=false\n"),
        ("ops.json", b'[{"name":"unexpected"}]'),
        ("whitelist.json", b"{}"),
        ("server.properties", b"level-name=other\nwhite-list=false\n"),
    ],
)
def test_missing_eula_operator_or_invalid_access_never_silently_changed(
    prepared, name, value
):
    request, source, storage, target = prepared
    (source / name).write_bytes(value)
    assert not (target / runtime.PLAN).exists()
    with pytest.raises(ValueError):
        runtime.execute({**request, "action": "runtime-stage"}, source, storage, target)
    assert (source / name).read_bytes() == value
    assert not (target / runtime.PLAN).exists()


@pytest.mark.parametrize("name", ["mods/extra.jar", ".omk/tmp/extra", "foreign.json"])
def test_unknown_target_files_refuse_verification(prepared, name):
    execute(prepared, "runtime-stage")
    target = prepared[-1]
    p = target / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"foreign")
    with pytest.raises(ValueError, match=r"Unexpected|Foreign"):
        execute(prepared, "runtime-verify")


@pytest.mark.parametrize(
    "mutation", ["missing", "changed", "world", "plan", "receipt", "empty-directory"]
)
def test_incomplete_or_tampered_candidate_is_never_accepted(prepared, mutation):
    execute(prepared, "runtime-stage")
    target = prepared[-1]
    if mutation == "missing":
        (target / "server.properties").unlink()
    elif mutation == "changed":
        (target / "whitelist.json").write_text("[]")
    elif mutation == "world":
        (target / "world/region/r.0.0.mca").write_bytes(b"changed")
    elif mutation == "plan":
        (target / runtime.PLAN).write_text("{}")
    elif mutation == "receipt":
        (target / runtime.DONE).write_text("{}")
    else:
        (target / "mods/unexpected-empty").mkdir()
    with pytest.raises(ValueError):
        execute(prepared, "runtime-verify")


def test_partial_copy_retained_and_never_repeated_or_verified(prepared, monkeypatch):
    original = runtime._copy
    count = 0

    def fail(*args):
        nonlocal count
        count += 1
        original(*args)
        if count == 2:
            raise OSError("fixture interruption")

    monkeypatch.setattr(runtime, "_copy", fail)
    with pytest.raises(OSError):
        execute(prepared, "runtime-stage")
    assert (prepared[-1] / runtime.PLAN).exists() and not (
        prepared[-1] / runtime.DONE
    ).exists()
    monkeypatch.setattr(runtime, "_copy", original)
    for action in ["runtime-stage", "runtime-verify"]:
        with pytest.raises(ValueError):
            execute(prepared, action)


@pytest.mark.parametrize("reason", ["budget", "reserve"])
def test_combined_world_runtime_budget_and_free_reserve_precede_writes(
    prepared, monkeypatch, reason
):
    request, source, storage, target = prepared
    if reason == "reserve":
        monkeypatch.setattr(
            runtime.shutil, "disk_usage", lambda _: shutil._ntuple_diskusage(1, 1, 0)
        )
    else:
        # Each component fits alone; the combined candidate must still refuse.
        plan = copy.deepcopy(request["runtime_expected"])
        plan.update(world_bytes=12 * 1024**2, runtime_bytes=6 * 1024**2)
        with pytest.raises(OSError, match="Combined"):
            runtime._space(request, target, plan)
        assert not (target / runtime.PLAN).exists()
        return
    with pytest.raises(OSError):
        runtime.execute({**request, "action": "runtime-stage"}, source, storage, target)
    assert not (target / runtime.PLAN).exists()


@pytest.mark.skipif(os.name == "nt", reason="Linux hardlink/symlink controls in Docker")
@pytest.mark.parametrize("kind", ["source-link", "source-hardlink", "target-link"])
def test_no_linked_runtime_can_be_promoted(prepared, kind):
    _, source, _, target = prepared
    if kind == "source-link":
        p = source / "eula.txt"
        p.rename(source / "eula-original")
        p.symlink_to(source / "eula-original")
    elif kind == "source-hardlink":
        os.link(source / "eula.txt", source / "eula-hardlink")
    else:
        execute(prepared, "runtime-stage")
        p = target / "eula.txt"
        p.unlink()
        p.symlink_to(source / "eula.txt")
    with pytest.raises(ValueError):
        execute(
            prepared, "runtime-verify" if kind == "target-link" else "runtime-stage"
        )


@pytest.mark.parametrize("action", ["start", "promote", "runtime-start"])
def test_worker_has_no_lifecycle_action(prepared, action):
    with pytest.raises(ValueError, match="action"):
        execute(prepared, action)


@pytest.mark.skipif(
    sys.platform != "linux", reason="Linux runtime paths are case-sensitive"
)
def test_runtime_preserves_distinct_case_sensitive_files(prepared):
    _, source, _, _ = prepared
    for name, content in [("CaseProbe.txt", b"upper"), ("caseprobe.txt", b"lower")]:
        (source / "config" / name).write_bytes(content)
    manifest = runtime.files(source, "world")
    assert (
        manifest["config/CaseProbe.txt"]["sha256"]
        != manifest["config/caseprobe.txt"]["sha256"]
    )
