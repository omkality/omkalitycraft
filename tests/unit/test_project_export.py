import copy
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import tarfile
import zipfile
from types import SimpleNamespace

import pytest

from omk import (
    component_archive as archive,
    project_export as project,
)
from omk.backup_archive import validate_inventory
from omk.offsite_process import OffsiteError


@pytest.fixture
def fixture(tmp_path):
    if sys.platform != "linux":
        pytest.skip("Linux project capture")
    game, auth, operator = (tmp_path / n for n in ("game", "auth", "operator"))
    for p in (game, auth, operator):
        p.mkdir(mode=0o700)
    world = game / "lab-world"
    world.mkdir()
    (world / "level.dat").write_bytes(b"opaque world marker; not a Minecraft test")
    (game / "server.properties").write_text("online-mode=true\n")
    (game / "config").mkdir()
    (game / "config/settings.cfg").write_bytes(b"runtime configuration")
    (game / "launch.sh").write_text("#!/bin/sh\nexit 0\n")
    (game / "launch.sh").chmod(0o750)
    with sqlite3.connect(auth / "drasl.db") as db:
        db.execute("CREATE TABLE fixture (id INTEGER PRIMARY KEY)")
        db.execute("INSERT INTO fixture VALUES (7)")
    (auth / "key.pkcs8").write_bytes(b"opaque test key; no real authentication")
    (operator / "operator.toml").write_text("schema=1\n")
    (operator / "drasl.toml").write_text('BaseURL="http://127.0.0.1:25586"\n')
    src = tmp_path / "world.zip"
    with zipfile.ZipFile(src, "x") as z:
        z.write(world / "level.dat", "lab-world/level.dat")
    files = project.world_inventory(
        world, world_name="lab-world", path_policy="linux-server"
    )
    manifest = tmp_path / "world.json"
    archive.json_write(
        manifest,
        {
            "schema": 1,
            "sequence": 1,
            "sha256": archive.digest(src),
            "files": files,
            "bytes": src.stat().st_size,
        },
    )
    stopped = {
        role: {
            "container_id": char * 64,
            "image_id": "sha256:" + char * 64,
            "volume": "isolated-" + role,
            "started_at": "2026-11-12T10:00:00Z",
            "finished_at": "2026-11-12T10:01:00Z",
            "exit_code": 0,
            "running": False,
            "restarting": False,
            "oom_killed": False,
        }
        for role, char in (("game", "a"), ("auth", "b"))
    }
    settings = {**project.policy({}), "reserve_bytes": 0}
    stopped["auth"]["config_sha256"] = archive.digest(operator / "drasl.toml")
    args = {
        "game": game,
        "auth": auth,
        "operator": operator,
        "operator_files": ["operator.toml", "drasl.toml"],
        "world_zip": src,
        "world_json": manifest,
        "world_name": "lab-world",
        "scope": {
            "project": "test",
            "server": "dj2",
            "pack_version": "fixture",
            "operation": "c" * 32,
        },
        "checkpoint": lambda: copy.deepcopy(stopped),
        "settings": settings,
    }
    return SimpleNamespace(args=args, stopped=stopped, out=tmp_path / "out")


def test_single_closed_set_preserves_all_roles_and_never_claims_admission(fixture):
    r = project.capture(fixture.out, **fixture.args)
    assert set(r["export"]["files"]) == project.FILES
    assert r["quarantine_required"] and not r["ready_for_players"]
    assert r["manifest"]["closed_sources"] == fixture.stopped
    for role in ("auth", "runtime", "operator"):
        p = fixture.out / (role + ".tar")
        archive.verify(
            p,
            archive.json_read(p.with_suffix(".json")),
            fixture.args["settings"][role + "_bytes"],
        )
    assert {p.name for p in fixture.out.iterdir()} == project.FILES
    assert project.verify(fixture.out, fixture.args["settings"]) == r
    with tarfile.open(fixture.out / "runtime.tar") as t:
        assert t.getmember("launch.sh").mode == 0o750
    with tarfile.open(fixture.out / "operator.tar") as t:
        assert all(m.mode == 0o600 for m in t)


@pytest.mark.parametrize(
    "field,value",
    [
        ("running", True),
        ("restarting", True),
        ("oom_killed", True),
        ("exit_code", 137),
        ("exit_code", False),
        ("image_id", "mutable:tag"),
    ],
)
def test_unclean_or_live_source_refuses_before_output(fixture, field, value):
    fixture.stopped["auth"][field] = value
    with pytest.raises(OffsiteError):
        project.capture(fixture.out, **fixture.args)
    assert not fixture.out.exists()


def test_lifecycle_restart_inside_window_leaves_no_seal(fixture):
    calls = 0

    def checkpoint():
        nonlocal calls
        calls += 1
        value = copy.deepcopy(fixture.stopped)
        if calls == 2:
            value["auth"]["started_at"] = "2026-11-12T10:00:10Z"
        return value

    fixture.args["checkpoint"] = checkpoint
    with pytest.raises(OffsiteError, match="lifecycle changed"):
        project.capture(fixture.out, **fixture.args)
    assert not (fixture.out / "project.json").exists()
    with pytest.raises(OffsiteError, match="Incomplete"):
        project.verify(fixture.out, fixture.args["settings"])


def test_world_from_another_snapshot_is_not_adopted(fixture):
    (fixture.args["game"] / "lab-world/level.dat").write_bytes(b"changed world")
    with pytest.raises(OffsiteError, match="another stopped"):
        project.capture(fixture.out, **fixture.args)
    assert not fixture.out.exists()


def test_auth_configuration_must_match_inspected_source(fixture):
    (fixture.args["operator"] / "drasl.toml").write_text(
        'BaseURL="http://different.invalid"\n'
    )
    with pytest.raises(OffsiteError, match="configuration differs"):
        project.capture(fixture.out, **fixture.args)
    assert not fixture.out.exists()


@pytest.mark.parametrize("kind", ["missing", "extra", "changed", "hardlink"])
def test_tampered_or_incomplete_export_refuses(fixture, kind):
    project.capture(fixture.out, **fixture.args)
    p = fixture.out / "runtime.tar"
    if kind == "missing":
        p.unlink()
    elif kind == "extra":
        (fixture.out / "unexpected").write_text("extra")
    elif kind == "changed":
        p.write_bytes(b"different archive")
    else:
        os.link(p, fixture.out.parent / "linked-runtime")
    with pytest.raises(OffsiteError):
        project.verify(fixture.out, fixture.args["settings"])


def test_corrupt_sqlite_never_gets_a_project_seal(fixture):
    (fixture.args["auth"] / "drasl.db").write_bytes(b"corrupt SQLite")
    with pytest.raises(sqlite3.DatabaseError):
        project.capture(fixture.out, **fixture.args)
    assert not (fixture.out / "project.json").exists()


def test_new_source_file_during_export_is_detected(fixture, monkeypatch):
    original = archive.write

    def write(root, files, path, maximum, **kwargs):
        r = original(root, files, path, maximum, **kwargs)
        if path.name == "operator.tar":
            (fixture.args["auth"] / "new-skin.png").write_bytes(b"late file")
        return r

    monkeypatch.setattr(archive, "write", write)
    with pytest.raises(OffsiteError, match="source changed"):
        project.capture(fixture.out, **fixture.args)
    assert not (fixture.out / "project.json").exists()


def test_existing_destination_is_not_overwritten(fixture):
    fixture.out.mkdir()
    (fixture.out / "keep").write_text("pre-existing")
    with pytest.raises(FileExistsError):
        project.capture(fixture.out, **fixture.args)
    assert (fixture.out / "keep").read_text() == "pre-existing"


@pytest.mark.parametrize(
    "kind", ["budget", "reserve", "recursive", "transport-credentials"]
)
def test_unsafe_plan_refuses_before_output(fixture, monkeypatch, kind):
    if kind == "budget":
        fixture.args["settings"]["max_bytes"] = 1
    elif kind == "reserve":
        monkeypatch.setattr(
            project.shutil, "disk_usage", lambda p: SimpleNamespace(free=1)
        )
    elif kind == "recursive":
        fixture.out = fixture.args["game"] / "export"
    else:
        root = fixture.args["operator"]
        (root / "offsite").mkdir()
        (root / "offsite/password").write_text("private fixture")
        fixture.args["operator_files"].append("offsite/password")
    with pytest.raises(OffsiteError):
        project.capture(fixture.out, **fixture.args)
    assert not fixture.out.exists()


@pytest.mark.parametrize(
    "key,value",
    [
        ("AUTH_BYTES", "134217729"),
        ("MAX_BYTES", "0"),
        ("MAX_BYTES", "x"),
        ("RUNTIME_BYTES", "-1"),
    ],
)
def test_policy_validation(key, value):
    with pytest.raises(OffsiteError):
        project.policy({"OMK_PROJECT_EXPORT_" + key: value})


def test_tar_with_unexpected_member_is_rejected_before_extraction(tmp_path):
    p = tmp_path / "unsafe.tar"
    with tarfile.open(p, "w") as t:
        t.addfile(tarfile.TarInfo("../escape"))
    m = {
        "schema": 1,
        "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
        "bytes": p.stat().st_size,
        "files": {"valid": hashlib.sha256(b"").hexdigest()},
        "sizes": {"valid": 0},
        "modes": {"valid": 0o600},
    }
    with pytest.raises(OffsiteError):
        archive.verify(p, m, 1024)
    assert not (tmp_path.parent / "escape").exists()


@pytest.mark.skipif(sys.platform != "linux", reason="Linux case-sensitive filesystem")
def test_linux_runtime_keeps_distinct_case_paths(tmp_path):
    root = tmp_path / "game"
    for name, raw in (
        ("config/DivineRPG/general.cfg", b"old upper"),
        ("config/divinerpg/general.cfg", b"new lower"),
    ):
        p = root / name
        p.parent.mkdir(parents=True)
        p.write_bytes(raw)
    files = archive.inventory(root, archive.file_names(root), 1024)
    # Original portable semantics remain a negative control.
    with pytest.raises(ValueError, match="Ambiguous"):
        validate_inventory(files)
    target = tmp_path / "runtime.tar"
    result = archive.write(root, files, target, 1024)
    assert len(result["files"]) == 2
    with tarfile.open(target) as t:
        assert t.extractfile("config/DivineRPG/general.cfg").read() == b"old upper"
        assert t.extractfile("config/divinerpg/general.cfg").read() == b"new lower"


def test_case_sensitive_mode_cannot_loosen_portable_inventory():
    with pytest.raises(ValueError, match="requires the Linux"):
        validate_inventory(
            {"ok": {"bytes": 0, "sha256": hashlib.sha256(b"").hexdigest()}},
            case_sensitive=True,
        )


@pytest.fixture
def release_context():
    return {
        "source_commit": "1" * 40,
        "client_manifests": {"windows-x64": "2" * 64, "linux-x64": "3" * 64},
        "declared_state_contract": "dj2-2.23.4-world-v1",
    }


def test_release_context_is_detached_from_mutable_controller_input(release_context):
    expected = copy.deepcopy(release_context)
    frozen = project._release_context(release_context)
    release_context["client_manifests"]["windows-x64"] = "4" * 64
    assert frozen == expected


@pytest.mark.parametrize("fault", ["missing_pin", "mutable_image", "boolean_digest"])
def test_malformed_selected_runtime_identity_is_rejected(release_context, fault):
    identity = {
        **release_context,
        "game_image_id": "sha256:" + "a" * 64,
        "runtime_archive_sha256": "b" * 64,
        "runtime_manifest_sha256": "c" * 64,
    }
    if fault == "missing_pin":
        identity.pop("runtime_archive_sha256")
    elif fault == "mutable_image":
        identity["game_image_id"] = "image:latest"
    else:
        identity["runtime_manifest_sha256"] = True
    with pytest.raises(OffsiteError):
        project._release_identity(identity)


@pytest.mark.parametrize(
    "fault",
    [
        "missing_commit",
        "mutable_tag",
        "short_commit",
        "uppercase_commit",
        "empty_clients",
        "unknown_platform",
        "mutable_client_tag",
        "contract_newline",
        "contract_oversize",
        "extra_secret_field",
        "non_mapping",
    ],
)
def test_invalid_release_context_never_echoes_input(release_context, fault):
    marker = "private-identity-fixture"
    if fault == "missing_commit":
        release_context.pop("source_commit")
    elif fault == "mutable_tag":
        release_context["source_commit"] = "dev"
    elif fault == "short_commit":
        release_context["source_commit"] = "1" * 7
    elif fault == "uppercase_commit":
        release_context["source_commit"] = "A" * 40
    elif fault == "empty_clients":
        release_context["client_manifests"] = {}
    elif fault == "unknown_platform":
        release_context["client_manifests"] = {"unreviewed": "2" * 64}
    elif fault == "mutable_client_tag":
        release_context["client_manifests"]["windows-x64"] = "latest"
    elif fault == "contract_newline":
        release_context["declared_state_contract"] = marker + "\n"
    elif fault == "contract_oversize":
        release_context["declared_state_contract"] = marker * 10
    elif fault == "extra_secret_field":
        release_context["password"] = marker
    else:
        release_context = [marker]
    with pytest.raises(OffsiteError) as error:
        project._release_context(release_context)
    assert marker not in str(error.value)


def test_selected_release_binds_existing_sealed_components(fixture, release_context):
    result = project.capture(
        fixture.out, release_context=release_context, **fixture.args
    )
    assert result["manifest"]["schema"] == 2
    identity = result["manifest"]["release_identity"]
    assert {key: identity[key] for key in release_context} == release_context
    assert identity["game_image_id"] == fixture.stopped["game"]["image_id"]
    assert identity["runtime_archive_sha256"] == archive.digest(
        fixture.out / "runtime.tar"
    )
    assert identity["runtime_manifest_sha256"] == archive.digest(
        fixture.out / "runtime.json"
    )
    assert result["manifest"]["closed_sources"] == fixture.stopped
    assert set(result["export"]["files"]) == project.FILES
    assert result["quarantine_required"] and not result["ready_for_players"]
    assert (
        project.verify(
            fixture.out,
            fixture.args["settings"],
            expected_release_identity=identity,
        )
        == result
    )
    for role in ("runtime", "auth", "operator"):
        archive.verify(
            fixture.out / (role + ".tar"),
            archive.json_read(fixture.out / (role + ".json")),
            fixture.args["settings"][role + "_bytes"],
        )


def test_legacy_export_is_readable_but_not_a_selected_release(fixture, release_context):
    result = project.capture(fixture.out, **fixture.args)
    assert result["manifest"]["schema"] == 1
    assert "release_identity" not in result["manifest"]
    assert project.verify(fixture.out, fixture.args["settings"]) == result
    expected = {
        **release_context,
        "game_image_id": fixture.stopped["game"]["image_id"],
        "runtime_archive_sha256": archive.digest(fixture.out / "runtime.tar"),
        "runtime_manifest_sha256": archive.digest(fixture.out / "runtime.json"),
    }
    with pytest.raises(OffsiteError):
        project.verify(
            fixture.out,
            fixture.args["settings"],
            expected_release_identity=expected,
        )


@pytest.mark.parametrize(
    "changed", ["source_commit", "client_manifests", "contract", "image", "runtime"]
)
def test_wrong_selected_release_refuses_without_changing_export(
    fixture, release_context, changed
):
    result = project.capture(
        fixture.out, release_context=release_context, **fixture.args
    )
    expected = copy.deepcopy(result["manifest"]["release_identity"])
    if changed == "client_manifests":
        expected["client_manifests"]["windows-x64"] = "4" * 64
    elif changed == "contract":
        expected["declared_state_contract"] = "different-world-v2"
    elif changed == "image":
        expected["game_image_id"] = "sha256:" + "6" * 64
    elif changed == "runtime":
        expected["runtime_archive_sha256"] = "7" * 64
    else:
        expected[changed] = "5" * 40
    with pytest.raises(OffsiteError):
        project.verify(
            fixture.out,
            fixture.args["settings"],
            expected_release_identity=expected,
        )
    assert project.verify(fixture.out, fixture.args["settings"]) == result


@pytest.mark.parametrize("fault", ["strip", "legacy_field", "extra", "bool_schema"])
def test_release_metadata_cannot_be_stripped_or_downgraded_for_selection(
    fixture, release_context, fault
):
    result = project.capture(
        fixture.out, release_context=release_context, **fixture.args
    )
    expected = copy.deepcopy(result["manifest"]["release_identity"])
    manifest = result["manifest"]
    if fault == "strip":
        manifest.pop("release_identity")
        manifest["schema"] = 1
    elif fault == "legacy_field":
        manifest["schema"] = 1
    elif fault == "extra":
        manifest["unreviewed"] = "not an instruction"
    else:
        manifest["schema"] = True
    path = fixture.out / "project.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(OffsiteError):
        project.verify(
            fixture.out,
            fixture.args["settings"],
            expected_release_identity=expected,
        )
    # The existing transport signature covers metadata too, not just the TARs.
    assert (
        project.signature(
            fixture.out,
            {"max_files": 9, "max_bytes": fixture.args["settings"]["max_bytes"]},
        )
        != result["export"]
    )


def test_bad_release_context_refuses_before_creating_export(fixture, release_context):
    release_context["client_manifests"]["windows-x64"] = "latest"
    with pytest.raises(OffsiteError):
        project.capture(fixture.out, release_context=release_context, **fixture.args)
    assert not fixture.out.exists()


@pytest.mark.parametrize("fault", ["image", "runtime_manifest", "missing_runtime_pin"])
def test_release_record_must_bind_the_enclosed_runtime(fixture, release_context, fault):
    result = project.capture(
        fixture.out, release_context=release_context, **fixture.args
    )
    manifest = result["manifest"]
    if fault == "image":
        manifest["closed_sources"]["game"]["image_id"] = "sha256:" + "4" * 64
    elif fault == "runtime_manifest":
        manifest["release_identity"]["runtime_manifest_sha256"] = "5" * 64
    else:
        manifest["files"]["runtime.tar"].pop("sha256")
    (fixture.out / "project.json").write_text(json.dumps(manifest), encoding="utf-8")
    # Internal inconsistency refuses even when no release selection was requested.
    with pytest.raises(OffsiteError):
        project.verify(fixture.out, fixture.args["settings"])


@pytest.mark.parametrize("rebind", [False, True])
def test_another_valid_runtime_cannot_be_substituted_for_the_selected_release(
    fixture, release_context, rebind
):
    original = project.capture(
        fixture.out, release_context=release_context, **fixture.args
    )
    selected = copy.deepcopy(original["manifest"]["release_identity"])
    (fixture.args["game"] / "server.properties").write_text("online-mode=false\n")
    other_dir = fixture.out.with_name("other-export")
    other = project.capture(other_dir, release_context=release_context, **fixture.args)
    assert other["manifest"]["release_identity"] != selected
    # Both components are valid TAR/manifest pairs, but belong to different code/config.
    for name in ("runtime.tar", "runtime.json"):
        shutil.copyfile(other_dir / name, fixture.out / name)
        original["manifest"]["files"][name] = other["manifest"]["files"][name]
    if rebind:
        original["manifest"]["release_identity"] = other["manifest"]["release_identity"]
    (fixture.out / "project.json").write_text(
        json.dumps(original["manifest"]), encoding="utf-8"
    )
    with pytest.raises(OffsiteError):
        project.verify(
            fixture.out,
            fixture.args["settings"],
            expected_release_identity=selected,
        )
