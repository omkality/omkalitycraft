import copy
import io
import json
import os
import tarfile
import zipfile
from types import SimpleNamespace

import pytest

from omk import (
    component_archive as archive,
    project_export,
    project_stage as stage,
)
from omk.offsite_process import OffsiteError
from tests.unit.test_project_export import (
    clients as client_fixture,
    fixture as capture_fixture,
)


@pytest.fixture
def prepared(tmp_path):
    clients = client_fixture.__wrapped__(tmp_path)
    base = capture_fixture.__wrapped__(tmp_path, clients)
    # Distinct Linux names and executable mode are essential runtime properties.
    game = base.args["game"]
    (game / "config/Case").mkdir()
    (game / "config/case").mkdir()
    (game / "config/Case/value.cfg").write_bytes(b"upper")
    (game / "config/case/value.cfg").write_bytes(b"lower")
    context = {
        "source_commit": "1" * 40,
        "client_manifests": {
            "windows-x64": clients.snapshots["windows-x64"].release.digest
        },
        "declared_state_contract": "fixture-world-v1",
    }
    result = project_export.capture(
        base.out, release_context=context, **base.client_args, **base.args
    )
    target = tmp_path / "stage"
    target.mkdir(mode=0o700)
    selection = {
        "project_sha256": archive.digest(base.out / "project.json"),
        "release_identity": copy.deepcopy(result["manifest"]["release_identity"]),
    }
    args = {
        "operation": "d" * 32,
        "world": "lab-world",
        "selection": selection,
        "settings": copy.deepcopy(base.args["settings"]),
    }
    return SimpleNamespace(base=base, source=base.out, target=target, args=args)


def plan(p):
    return stage.plan(p.source, p.target, **p.args)


def test_stage_preserves_world_runtime_modes_and_case_without_auth(prepared):
    p = prepared
    before = {x.name: archive.digest(x) for x in p.source.iterdir()}
    expected = plan(p)
    assert not list(p.target.iterdir())
    result = stage.stage(p.source, p.target, expected=expected)
    game = p.target / stage.GAME
    assert (game / "lab-world/level.dat").read_bytes() == (
        p.base.args["game"] / "lab-world/level.dat"
    ).read_bytes()
    assert (game / "launch.sh").stat().st_mode & 0o777 == 0o750
    assert (game / "config/Case/value.cfg").read_bytes() == b"upper"
    assert (game / "config/case/value.cfg").read_bytes() == b"lower"
    assert not any(
        (game / name).exists() for name in ("drasl.db", "key.pkcs8", "operator.toml")
    )
    assert result["quarantine_required"] and not result["ready_for_players"]
    assert not result["boot_allowed"] and not result["current_policy_reconciled"]
    assert stage.verify(p.source, p.target, expected=expected)["verified"]
    assert {x.name: archive.digest(x) for x in p.source.iterdir()} == before
    with pytest.raises(OffsiteError):
        stage.stage(p.source, p.target, expected=expected)


def test_selected_world_snapshot_is_bound_even_with_identical_runtime(prepared):
    p = prepared
    expected = plan(p)
    manifest = json.loads((p.source / "project.json").read_bytes())
    world_file = p.base.args["game"] / "lab-world/level.dat"
    world_file.write_bytes(b"different later world state")
    with zipfile.ZipFile(p.source / "world.zip", "w") as z:
        z.write(world_file, "lab-world/level.dat")
    world = json.loads((p.source / "world.json").read_bytes())
    world["files"] = project_export.world_inventory(
        world_file.parent, world_name="lab-world", path_policy="linux-server"
    )
    world["sha256"] = archive.digest(p.source / "world.zip")
    world["bytes"] = (p.source / "world.zip").stat().st_size
    (p.source / "world.json").write_text(json.dumps(world))
    for name in ("world.zip", "world.json"):
        manifest["files"][name] = {
            "sha256": archive.digest(p.source / name),
            "bytes": (p.source / name).stat().st_size,
        }
    (p.source / "project.json").write_text(json.dumps(manifest))
    # A different sound export with the same release identity is not the selected snapshot.
    assert (
        project_export.verify(p.source, p.args["settings"])["manifest"][
            "release_identity"
        ]
        == p.args["selection"]["release_identity"]
    )
    with pytest.raises(OffsiteError):
        stage.stage(p.source, p.target, expected=expected)
    assert not list(p.target.iterdir())


def test_consistent_outer_metadata_does_not_admit_an_unsafe_tar_member(prepared):
    p = prepared
    path = p.source / "runtime.tar"
    with tarfile.open(path) as t:
        entries = [(copy.copy(m), t.extractfile(m).read()) for m in t]
    with tarfile.open(path, "w") as t:
        for i, (member, raw) in enumerate(entries):
            if i == 0:
                member.type, member.linkname, member.size = (
                    tarfile.SYMTYPE,
                    "../../outside",
                    0,
                )
                t.addfile(member)
            else:
                t.addfile(member, io.BytesIO(raw))
    r = json.loads((p.source / "runtime.json").read_bytes())
    r["sha256"], r["bytes"] = archive.digest(path), path.stat().st_size
    (p.source / "runtime.json").write_text(json.dumps(r))
    m = json.loads((p.source / "project.json").read_bytes())
    for name in ("runtime.tar", "runtime.json"):
        m["files"][name] = {
            "bytes": (p.source / name).stat().st_size,
            "sha256": archive.digest(p.source / name),
        }
    m["release_identity"]["runtime_archive_sha256"] = m["files"]["runtime.tar"][
        "sha256"
    ]
    m["release_identity"]["runtime_manifest_sha256"] = m["files"]["runtime.json"][
        "sha256"
    ]
    (p.source / "project.json").write_text(json.dumps(m))
    p.args["selection"] = {
        "project_sha256": archive.digest(p.source / "project.json"),
        "release_identity": m["release_identity"],
    }
    project_export.verify(
        p.source, p.args["settings"], expected_release_identity=m["release_identity"]
    )
    with pytest.raises(OffsiteError):
        plan(p)
    assert not list(p.target.iterdir())


def test_plan_detaches_the_mutable_controller_context(prepared):
    p = prepared
    expected = plan(p)
    saved = copy.deepcopy(expected)
    p.args["selection"]["release_identity"]["client_manifests"]["windows-x64"] = (
        "9" * 64
    )
    p.args["settings"]["reserve_bytes"] += 1
    assert expected == saved
    assert stage.stage(p.source, p.target, expected=expected)["staged"]


@pytest.mark.parametrize(
    "fault", ["legacy", "identity", "project_hash", "world", "setting", "operation"]
)
def test_bad_selection_refuses_before_any_target_write(prepared, fault):
    p = prepared
    if fault == "legacy":
        m = json.loads((p.source / "project.json").read_bytes())
        m["schema"] = 1
        m.pop("release_identity")
        (p.source / "project.json").write_text(json.dumps(m))
        p.args["selection"]["project_sha256"] = archive.digest(
            p.source / "project.json"
        )
    elif fault == "identity":
        p.args["selection"]["release_identity"]["source_commit"] = "f" * 40
    elif fault == "project_hash":
        p.args["selection"]["project_sha256"] = "0" * 64
    elif fault == "world":
        p.args["world"] = "different"
    elif fault == "setting":
        p.args["settings"]["world_bytes"] += 1
    else:
        p.args["operation"] = "../secret-value"
    with pytest.raises((OffsiteError, ValueError)) as error:
        plan(p)
    assert "secret-value" not in str(error.value)
    assert not list(p.target.iterdir())


@pytest.mark.parametrize(
    "fault",
    ["file", "empty_directory", "symlink", "shared_directory", "source_overlap"],
)
def test_nonempty_or_unsafe_target_is_not_adopted(prepared, fault):
    p = prepared
    if fault == "file":
        (p.target / "keep").write_bytes(b"existing")
    elif fault == "empty_directory":
        (p.target / "keep").mkdir()
    elif fault == "symlink":
        alias = p.target.with_name("alias")
        alias.symlink_to(p.target, target_is_directory=True)
        p.target = alias
    elif fault == "shared_directory":
        p.target.chmod(0o755)
    else:
        p.target = p.source
    with pytest.raises((OffsiteError, ValueError)):
        plan(p)
    if fault == "file":
        assert (p.target / "keep").read_bytes() == b"existing"


def test_low_disk_reserve_refuses_without_creating_plan(prepared, monkeypatch):
    p = prepared
    monkeypatch.setattr(
        stage.shutil, "disk_usage", lambda path: SimpleNamespace(free=0)
    )
    with pytest.raises(OSError):
        plan(p)
    assert not list(p.target.iterdir())


@pytest.mark.parametrize("fault", ["operation", "count", "settings", "source", "extra"])
def test_stale_or_modified_plan_refuses_before_write(prepared, fault):
    p = prepared
    expected = plan(p)
    if fault == "operation":
        expected["operation"] = False
    elif fault == "count":
        expected["files"] += 1
    elif fault == "settings":
        expected["settings"]["reserve_bytes"] += 1
    elif fault == "source":
        expected["source"] += "/elsewhere"
    else:
        expected["password"] = "secret-value"
    with pytest.raises((OffsiteError, ValueError)):
        stage.stage(p.source, p.target, expected=expected)
    assert not list(p.target.iterdir())


def test_interrupted_copy_is_retained_and_cannot_be_retried_or_verified(
    prepared, monkeypatch
):
    p = prepared
    expected = plan(p)
    original = stage.copy_file
    calls = 0

    def interrupted(*args):
        nonlocal calls
        original(*args)
        calls += 1
        raise OSError("simulated copy interruption")

    monkeypatch.setattr(stage, "copy_file", interrupted)
    with pytest.raises(OSError):
        stage.stage(p.source, p.target, expected=expected)
    assert calls == 1 and (p.target / stage.PLAN).is_file()
    assert not (p.target / stage.DONE).exists()
    assert list((p.target / stage.GAME).rglob("*"))
    with pytest.raises(OffsiteError):
        stage.stage(p.source, p.target, expected=expected)
    with pytest.raises((OffsiteError, ValueError)):
        stage.verify(p.source, p.target, expected=expected)


def test_lost_response_after_complete_receipt_is_recoverable_by_read_only_verify(
    prepared, monkeypatch
):
    p = prepared
    expected = plan(p)
    original = stage.write_record

    def response_lost(path, value):
        original(path, value)
        if path.name == stage.DONE:
            raise OSError("simulated response loss")

    monkeypatch.setattr(stage, "write_record", response_lost)
    with pytest.raises(OSError):
        stage.stage(p.source, p.target, expected=expected)
    before = (p.target / stage.DONE).read_bytes()
    assert stage.verify(p.source, p.target, expected=expected)["verified"]
    assert (p.target / stage.DONE).read_bytes() == before


@pytest.mark.parametrize(
    "fault",
    [
        "bytes",
        "mode",
        "world_mode",
        "extra_file",
        "empty_dir",
        "missing_receipt",
        "receipt",
        "receipt_number_instead_of_bool",
        "hardlink",
    ],
)
def test_completed_stage_detects_late_damage_without_repairs(prepared, fault):
    p = prepared
    expected = plan(p)
    stage.stage(p.source, p.target, expected=expected)
    game = p.target / stage.GAME
    if fault == "bytes":
        (game / "config/settings.cfg").write_bytes(b"changed")
    elif fault == "mode":
        (game / "launch.sh").chmod(0o600)
    elif fault == "world_mode":
        (game / "lab-world/level.dat").chmod(0o644)
    elif fault == "extra_file":
        (game / "extra").write_bytes(b"extra")
    elif fault == "empty_dir":
        (game / "extra").mkdir()
    elif fault == "missing_receipt":
        (p.target / stage.DONE).unlink()
    elif fault in {"receipt", "receipt_number_instead_of_bool"}:
        r = json.loads((p.target / stage.DONE).read_bytes())
        r["boot_allowed"] = True if fault == "receipt" else 0
        (p.target / stage.DONE).write_text(json.dumps(r))
    else:
        q = game / "config/settings.cfg"
        q.unlink()
        os.link(game / "config/Case/value.cfg", q)
    with pytest.raises((OffsiteError, ValueError)):
        stage.verify(p.source, p.target, expected=expected)


def test_source_change_during_copy_leaves_unsealed_stage(prepared, monkeypatch):
    p = prepared
    expected = plan(p)
    original = stage.copy_file

    def mutate(*args):
        original(*args)
        (p.source / "project.json").write_bytes(b"changed after selection")

    monkeypatch.setattr(stage, "copy_file", mutate)
    with pytest.raises((OffsiteError, ValueError)):
        stage.stage(p.source, p.target, expected=expected)
    assert not (p.target / stage.DONE).exists()


def test_relative_source_is_not_bound_to_an_ambient_working_directory(
    prepared, monkeypatch
):
    p = prepared
    monkeypatch.chdir(p.source.parent)
    p.source = p.source.relative_to(p.source.parent)
    with pytest.raises(OffsiteError):
        plan(p)


def test_foreign_target_root_entry_during_copy_prevents_receipt(prepared, monkeypatch):
    p = prepared
    expected = plan(p)
    original = stage.copy_file

    def add_entry(*args):
        original(*args)
        (p.target / "foreign").write_bytes(b"do not adopt this")

    monkeypatch.setattr(stage, "copy_file", add_entry)
    with pytest.raises(OffsiteError):
        stage.stage(p.source, p.target, expected=expected)
    assert not (p.target / stage.DONE).exists()
    assert (p.target / "foreign").read_bytes() == b"do not adopt this"


def test_non_linux_stage_refuses_before_reading_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(stage.sys, "platform", "win32")
    with pytest.raises(OffsiteError, match="Linux"):
        stage.plan(
            tmp_path / "missing",
            tmp_path,
            operation="d" * 32,
            world="lab-world",
            selection={},
            settings={},
        )


@pytest.mark.parametrize(
    "fault",
    [
        "bool",
        "negative",
        "too_large",
        "auth",
        "operator",
        "extra",
        "selection",
        "identity",
    ],
)
def test_invalid_limits_and_identity_are_rejected_without_echoing_input(fault):
    settings = {**project_export.policy({}), "reserve_bytes": 0}
    identity = {
        "source_commit": "1" * 40,
        "client_manifests": {"windows-x64": "2" * 64},
        "declared_state_contract": "fixture-v1",
        "game_image_id": "sha256:" + "3" * 64,
        "runtime_archive_sha256": "4" * 64,
        "runtime_manifest_sha256": "5" * 64,
    }
    selection = {"project_sha256": "6" * 64, "release_identity": identity}
    if fault in {"bool", "negative", "too_large"}:
        settings["world_bytes"] = {
            "bool": True,
            "negative": -1,
            "too_large": 1024**4 + 1,
        }[fault]
    elif fault == "auth":
        settings["auth_bytes"] = 128 * 1024**2 + 1
    elif fault == "operator":
        settings["operator_bytes"] = 1024**3 + 1
    elif fault == "extra":
        settings["password"] = "secret-value"
    elif fault == "selection":
        selection["project_sha256"] = "secret-value"
    else:
        identity["client_manifests"]["windows-x64"] = "secret-value"
    with pytest.raises(OffsiteError) as error:
        stage._context("a" * 32, "lab-world", selection, settings)
    assert "secret-value" not in str(error.value)
