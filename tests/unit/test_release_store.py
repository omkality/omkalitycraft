import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from launcher.releases import ReleaseError, read_release
from omk.backup_store import _lock
from omk.publish import build_release, signing_key
from omk.release_cli import _write_manifest, add_release_commands, prepare_release
from omk.release_store import ReleaseStore, ReleaseStorePolicy


@pytest.fixture
def release(tmp_path):
    source = tmp_path / "files"
    (source / "runtime").mkdir(parents=True)
    for name in ["runtime/java", "agent.jar", "forge.jar", "locale.lang"]:
        (source / name).write_bytes(b"not executable, fixture only")
    keys_path = tmp_path / "public.json"
    key = signing_key(tmp_path / "offline.pem", keys_path)
    keys = json.loads(keys_path.read_bytes())

    def build(version="one"):
        return build_release(
            source,
            pack_id="fixture",
            version=version,
            minecraft="1.12.2",
            platform="windows-x64",
            key=key,
            launch={
                "java": "runtime/java",
                "agent": "agent.jar",
                "classpath": ["forge.jar"],
                "main_class": "net.minecraft.launchwrapper.Launch",
                "assets": "assets",
                "natives": "natives",
                "game_args": [],
            },
        )

    return source, keys, build


def store(tmp_path, keys):
    return ReleaseStore.create(tmp_path / "store", ReleaseStorePolicy(1024**2, 1), keys)


def test_snapshot_copies_only_signed_files_and_survives_source_changes(
    tmp_path, release
):
    source, keys, build = release
    envelope = build()
    saved = store(tmp_path, keys)
    (source / "userdata").mkdir()
    (source / "userdata/session.json").write_text("private fixture")
    snapshot = saved.publish(source, envelope)
    assert not (snapshot.files / "userdata").exists()
    assert not os.path.samefile(snapshot.files / "locale.lang", source / "locale.lang")
    (source / "locale.lang").write_bytes(b"new translation")
    verified = saved.verify(snapshot.release.digest)
    assert (
        verified.files / "locale.lang"
    ).read_bytes() == b"not executable, fixture only"
    assert json.loads((snapshot.directory / "manifest.json").read_bytes()) == envelope


def test_idempotent_capture_and_multiple_generations_never_replace_old(
    tmp_path, release
):
    source, keys, build = release
    saved = store(tmp_path, keys)
    one = build()
    first = saved.publish(source, one)
    original = (first.directory / "manifest.json").read_bytes()
    assert saved.publish(source, one).directory == first.directory
    (source / "locale.lang").write_bytes(b"new")
    second = saved.publish(source, build("two"))
    assert second.directory != first.directory and saved.verify(first.release.digest)
    assert (first.directory / "manifest.json").read_bytes() == original


@pytest.mark.parametrize("mutation", ["changed", "missing", "longer"])
def test_changed_source_fails_without_partial_generation(tmp_path, release, mutation):
    source, keys, build = release
    envelope = build()
    saved = store(tmp_path, keys)
    if mutation == "missing":
        (source / "locale.lang").unlink()
    else:
        (source / "locale.lang").write_bytes(
            b"x" * (100 if mutation == "longer" else 3)
        )
    with pytest.raises(ValueError):
        saved.publish(source, envelope)
    assert {p.name for p in saved.root.iterdir()} == {"owner.json", "lock"}


def test_copy_failure_removes_only_its_own_stage(tmp_path, release, monkeypatch):
    source, keys, build = release
    saved = store(tmp_path, keys)
    first = saved.publish(source, build())
    original = ReleaseStore._copy

    def fail(source, stage, artifact):
        original(source, stage, artifact)
        raise OSError("injected disk fault")

    monkeypatch.setattr(ReleaseStore, "_copy", staticmethod(fail))
    with pytest.raises(OSError):
        saved.publish(source, build("two"))
    assert {p.name for p in saved.root.iterdir()} == {
        "owner.json",
        "lock",
        first.release.digest,
    }


@pytest.mark.parametrize("mutation", ["payload", "manifest", "foreign", "directory"])
def test_stored_corruption_and_foreign_content_fail_closed(tmp_path, release, mutation):
    source, keys, build = release
    saved = store(tmp_path, keys)
    snapshot = saved.publish(source, build())
    if mutation == "payload":
        (snapshot.files / "locale.lang").write_bytes(b"corrupt")
    elif mutation == "manifest":
        (snapshot.directory / "manifest.json").write_bytes(b"{}")
    elif mutation == "foreign":
        (snapshot.directory / "extra.txt").write_bytes(b"extra")
    else:
        (snapshot.directory / "foreign").mkdir()
    with pytest.raises((ValueError, RuntimeError)):
        saved.verify(snapshot.release.digest)
    with pytest.raises((ValueError, RuntimeError)):
        saved.publish(source, build("two"))


def test_budget_refuses_new_generation_without_pruning_previous(tmp_path, release):
    source, keys, build = release
    saved = store(tmp_path, keys)
    one = saved.publish(source, build())
    two = saved.publish(source, build("two"))
    tight = ReleaseStore(saved.root, ReleaseStorePolicy(one.bytes + two.bytes, 1), keys)
    with pytest.raises(ValueError, match="budget"):
        tight.publish(source, build("three"))
    assert saved.verify(one.release.digest) and saved.verify(two.release.digest)


def test_disk_reserve_is_checked_before_copy(tmp_path, release):
    source, keys, build = release
    saved = store(tmp_path, keys)
    with (
        patch(
            "omk.release_store.shutil.disk_usage", return_value=SimpleNamespace(free=0)
        ),
        pytest.raises(ValueError, match="free space"),
    ):
        saved.publish(source, build())
    assert {p.name for p in saved.root.iterdir()} == {"owner.json", "lock"}


def test_interrupted_stage_is_preserved_for_inspection(tmp_path, release):
    source, keys, build = release
    saved = store(tmp_path, keys)
    pending = saved.root / ("pending-" + "a" * 32)
    pending.mkdir()
    (pending / "evidence").write_bytes(b"keep")
    with pytest.raises(ValueError, match="inspection"):
        saved.publish(source, build())
    assert (pending / "evidence").read_bytes() == b"keep"


def test_store_never_adopts_existing_data(tmp_path, release):
    _, keys, _ = release
    root = tmp_path / "existing"
    root.mkdir()
    (root / "keep").write_bytes(b"old")
    with pytest.raises(FileExistsError):
        ReleaseStore.create(root, ReleaseStorePolicy(), keys)
    with pytest.raises(ValueError):
        ReleaseStore(root, ReleaseStorePolicy(), keys)
    assert (root / "keep").read_bytes() == b"old"


def test_invalid_signature_and_extra_envelope_fields_do_not_write(tmp_path, release):
    source, keys, build = release
    saved = store(tmp_path, keys)
    envelope = build()
    envelope["manifest"]["version"] = "tampered"
    with pytest.raises(RuntimeError):
        saved.publish(source, envelope)
    envelope = build()
    envelope["private"] = "must not be stored"
    with pytest.raises(ValueError):
        saved.publish(source, envelope)
    assert {p.name for p in saved.root.iterdir()} == {"owner.json", "lock"}


def test_cooperative_writer_lock_prevents_a_second_publication(tmp_path, release):
    source, keys, build = release
    saved = store(tmp_path, keys)
    with _lock(saved.root), pytest.raises(OSError):
        saved.publish(source, build())


def test_nested_source_and_store_are_rejected(tmp_path, release):
    source, keys, build = release
    envelope = build()
    saved = ReleaseStore.create(source / "store", ReleaseStorePolicy(), keys)
    with pytest.raises(ValueError, match="separate"):
        saved.publish(source, envelope)


def test_source_and_snapshot_links_are_rejected(tmp_path, release):
    source, keys, build = release
    envelope = build()
    saved = store(tmp_path, keys)
    target = source / "locale.lang"
    original = tmp_path / "original"
    target.rename(original)
    try:
        target.symlink_to(original)
    except OSError:
        pytest.skip("Symlink privilege unavailable")
    with pytest.raises((ValueError, ReleaseError)):
        saved.publish(source, envelope)
    target.unlink()
    target.write_bytes(original.read_bytes())
    snap = saved.publish(source, envelope)
    entry = snap.files / "locale.lang"
    entry.unlink()
    entry.symlink_to(target)
    with pytest.raises(ValueError, match="Linked"):
        saved.verify(snap.release.digest)


@pytest.mark.parametrize("value", ["0", "-1", "1.5", "private-value", "9" * 14, True])
def test_invalid_environment_policy_never_echoes_values(value):
    with pytest.raises(ValueError) as error:
        ReleaseStorePolicy.environment({"OMK_RELEASE_SNAPSHOT_MAX_BYTES": value})
    assert str(value) not in str(error.value)


def test_cli_captures_before_manifest_publication_and_keeps_old_on_budget_error(
    tmp_path, release, monkeypatch
):
    monkeypatch.setenv("OMK_RELEASE_SNAPSHOT_RESERVE_BYTES", "1")
    source, keys, _ = release
    parser = argparse.ArgumentParser()
    add_release_commands(parser.add_subparsers(required=True))
    output = tmp_path / "manifest.json"
    snapshots = tmp_path / "snapshots"
    args = [
        "release",
        "pack",
        "--files",
        str(source),
        "--launch-profile",
        str(tmp_path / "launch.json"),
        "--private-key",
        str(tmp_path / "offline.pem"),
        "--public-keys",
        str(tmp_path / "public.json"),
        "--output",
        str(output),
        "--pack-id",
        "fixture",
        "--minecraft",
        "1.12.2",
        "--version",
        "one",
        "--platform",
        "windows-x64",
        "--snapshot-root",
        str(snapshots),
    ]
    _, _, build = release
    (tmp_path / "launch.json").write_text(json.dumps(build()["manifest"]["launch"]))
    first = prepare_release(parser.parse_args(args))
    before = output.read_bytes()
    parsed = read_release(before, keys)
    assert ReleaseStore(snapshots, ReleaseStorePolicy(), keys).verify(parsed.digest)
    assert first["snapshot"] == str(snapshots / parsed.digest)
    args[args.index("one")] = "two"
    monkeypatch.setenv("OMK_RELEASE_SNAPSHOT_MAX_BYTES", "1")
    with pytest.raises(ValueError, match="budget"):
        prepare_release(parser.parse_args(args))
    assert output.read_bytes() == before


def test_atomic_manifest_replace_failure_preserves_previous_file(tmp_path):
    path = tmp_path / "manifest.json"
    path.write_bytes(b"previous")
    with (
        patch("omk.release_cli.os.replace", side_effect=OSError("injected")),
        pytest.raises(OSError),
    ):
        _write_manifest(path, {"fixture": True})
    assert path.read_bytes() == b"previous" and list(tmp_path.iterdir()) == [path]


def test_snapshot_policy_defaults_and_explicit_values():
    assert ReleaseStorePolicy.environment({}) == ReleaseStorePolicy()
    assert ReleaseStorePolicy.environment(
        {
            "OMK_RELEASE_SNAPSHOT_MAX_BYTES": "4096",
            "OMK_RELEASE_SNAPSHOT_RESERVE_BYTES": "128",
        }
    ) == ReleaseStorePolicy(4096, 128)


def test_changed_content_cannot_reuse_a_retained_version(tmp_path, release):
    source, keys, build = release
    saved = store(tmp_path, keys)
    one = saved.publish(source, build())
    (source / "locale.lang").write_bytes(b"changed")
    with pytest.raises(ValueError, match="new version"):
        saved.publish(source, build())
    assert saved.verify(one.release.digest)


def test_count_budget_keeps_existing_generations_and_allows_idempotent_read(
    tmp_path, release
):
    source, keys, build = release
    saved = ReleaseStore.create(
        tmp_path / "store", ReleaseStorePolicy(1024**2, 1, 2), keys
    )
    one = saved.publish(source, build())
    two = saved.publish(source, build("two"))
    assert saved.publish(source, build()).directory == one.directory
    with pytest.raises(ValueError, match="count budget"):
        saved.publish(source, build("three"))
    assert saved.verify(one.release.digest) and saved.verify(two.release.digest)


def test_snapshot_root_environment_and_cli_write_overlap_are_validated(
    tmp_path, monkeypatch
):
    root = tmp_path / "private-releases"
    monkeypatch.setenv("OMK_RELEASE_SNAPSHOT_ROOT", str(root))
    parser = argparse.ArgumentParser()
    add_release_commands(parser.add_subparsers(required=True))
    args = parser.parse_args(
        [
            "release",
            "pack",
            "--files",
            str(tmp_path / "source"),
            "--launch-profile",
            str(tmp_path / "launch"),
            "--private-key",
            str(tmp_path / "key"),
            "--public-keys",
            str(tmp_path / "public"),
            "--output",
            str(root / "manifest.json"),
            "--pack-id",
            "fixture",
            "--minecraft",
            "1.12.2",
            "--version",
            "one",
        ]
    )
    assert args.snapshot_root == root
    with pytest.raises(ValueError, match="outside snapshots"):
        prepare_release(args)
    assert not root.exists() and not (tmp_path / "key").exists()


def test_real_worker_kill_keeps_previous_snapshot_readable_and_blocks_new_publication(
    tmp_path, release
):
    source, keys, build = release
    saved = store(tmp_path, keys)
    previous = saved.publish(source, build())
    manifest = tmp_path / "candidate.json"
    manifest.write_text(json.dumps(build("two")))
    public = tmp_path / "worker-keys.json"
    public.write_text(json.dumps(keys))
    marker = tmp_path / "copy-started"
    worker = """import json,sys,time
from pathlib import Path
from omk.release_store import ReleaseStore,ReleaseStorePolicy
source,root,manifest,keys,marker=map(Path,sys.argv[1:])
copy=ReleaseStore._copy
def pause(source,stage,artifact):
 copy(source,stage,artifact)
 marker.write_text('ready')
 time.sleep(60)
ReleaseStore._copy=staticmethod(pause)
ReleaseStore(root,ReleaseStorePolicy(1024**2,1),json.loads(keys.read_bytes())).publish(source,json.loads(manifest.read_bytes()))
"""
    process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            worker,
            str(source),
            str(saved.root),
            str(manifest),
            str(public),
            str(marker),
        ],
        cwd=Path(__file__).resolve().parents[2],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        deadline = time.monotonic() + 10
        while (
            not marker.exists()
            and time.monotonic() < deadline
            and process.poll() is None
        ):
            time.sleep(0.02)
        assert marker.exists()
        process.terminate()
        process.wait(timeout=10)
        assert process.returncode != 0
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=10)
        process.communicate(timeout=10)
    assert saved.verify(previous.release.digest)
    assert len(list(saved.root.glob("pending-*"))) == 1
    with pytest.raises(ValueError, match="inspection"):
        saved.publish(source, build("three"))
