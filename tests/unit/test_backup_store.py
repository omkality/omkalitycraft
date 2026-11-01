import errno
import hashlib
import json
import os
import stat
from pathlib import Path
from unittest.mock import Mock
from zipfile import BadZipFile, ZipFile

import pytest

from omk.backup_archive import verify_archive
from omk.backup_store import BackupPolicy, BackupStore, _lock


def make_archive(root, number=0, *, payload=None):
    source = root / f"input-{number}.zip"
    files = {}
    with ZipFile(source, "x") as archive:
        for name, data in {
            "world/level.dat": (
                payload if payload is not None else b"level" + bytes([number])
            ),
            "world/DIM-1/region/r.0.0.mca": b"dimension" + bytes([number]),
            "world/data/teams.dat": b"claims" + bytes([number]),
        }.items():
            archive.writestr(name, data)
            files[name] = {
                "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
    return source, files


def store_at(tmp_path, *, max_bytes=1024**2, max_count=2):
    policy = BackupPolicy(max_bytes, max_count, 1024**2, 1)
    return BackupStore.create(tmp_path / "store", policy)


def history(store):
    return {
        p.relative_to(store.root).as_posix(): p.read_bytes()
        for p in store.root.rglob("*")
        if p.is_file()
    }


def publish_next(store, root, number):
    source, files = make_archive(root, number)
    return store.publish(source, files)


def test_rotation_keeps_new_and_previous_fully_verified_copy(tmp_path):
    store = store_at(tmp_path)
    first = publish_next(store, tmp_path, 0)
    second = publish_next(store, tmp_path, 1)
    third = publish_next(store, tmp_path, 2)
    assert first["retired"] == second["retired"] == 0
    assert third["retired"] == 1
    copies = store.inspect()
    assert [c["sequence"] for c in copies] == [2, 3]
    assert {c["id"] for c in copies} == {second["id"], third["id"]}
    assert not (store.root / first["id"]).exists()
    assert all(c["verified"] for c in (first, second, third))


def test_byte_budget_rotates_oldest_without_sacrificing_previous(tmp_path):
    store = store_at(tmp_path, max_count=10)
    one = publish_next(store, tmp_path, 0)
    two = publish_next(store, tmp_path, 1)
    source, files = make_archive(tmp_path, 2)
    store.policy = BackupPolicy(store.inspect()[0]["bytes"] * 2, 10, 1024**2, 1)
    result = store.publish(source, files)
    assert result["retired"] == 1
    assert [c["id"] for c in store.inspect()] == [two["id"], result["id"]]
    assert not (store.root / one["id"]).exists()


def test_budget_too_small_for_two_never_deletes_existing_copy(tmp_path):
    store = store_at(tmp_path)
    publish_next(store, tmp_path, 0)
    source, files = make_archive(tmp_path, 1, payload=os.urandom(2000))
    store.policy = BackupPolicy(source.stat().st_size + 1, 2, 1024**2, 1)
    before = history(store)
    with pytest.raises(ValueError, match="preceding copy"):
        store.publish(source, files)
    assert history(store) == before


@pytest.mark.parametrize("kind", ["bytes", "count", "staging", "reserve"])
def test_policy_rejects_bad_values(kind):
    args = {
        "max_bytes": 1000,
        "max_count": 2,
        "staging_bytes": 2000,
        "reserve_bytes": 1,
    }
    args[
        {
            "bytes": "max_bytes",
            "count": "max_count",
            "staging": "staging_bytes",
            "reserve": "reserve_bytes",
        }[kind]
    ] = 0
    with pytest.raises(ValueError):
        BackupPolicy(**args)
    with pytest.raises(ValueError):
        BackupPolicy(100, 1, 100, 1)
    with pytest.raises(ValueError):
        BackupPolicy(True, 2, 100, 1)


def test_existing_folder_never_adopted_or_cleared(tmp_path):
    root = tmp_path / "backups"
    root.mkdir()
    marker = root / "old-ftb.zip"
    marker.write_bytes(b"precious")
    with pytest.raises(FileExistsError):
        BackupStore.create(root, BackupPolicy(100, 2, 100, 1))
    assert marker.read_bytes() == b"precious" and len(list(root.iterdir())) == 1


@pytest.mark.parametrize("problem", ["missing", "extra", "hash", "size", "duplicate"])
def test_incomplete_input_is_not_committed_and_history_unchanged(tmp_path, problem):
    store = store_at(tmp_path)
    publish_next(store, tmp_path, 0)
    source, files = make_archive(tmp_path, 1)
    if problem == "missing":
        files["world/missing.dat"] = {
            "bytes": 0,
            "sha256": hashlib.sha256(b"").hexdigest(),
        }
    elif problem == "extra":
        files.pop("world/data/teams.dat")
    elif problem in {"hash", "size"}:
        files["world/level.dat"]["sha256" if problem == "hash" else "bytes"] = (
            "0" * 64 if problem == "hash" else 200
        )
    else:
        with ZipFile(source, "a") as archive:
            archive.writestr("world/level.dat", b"level")
    before = history(store)
    with pytest.raises(ValueError):
        store.publish(source, files)
    assert history(store) == before


@pytest.mark.parametrize(
    "name",
    [
        "../out",
        "/abs",
        "world/../out",
        "world\\bad",
        "world/AUX.txt",
        "world/a.",
        "world/a ",
        "world/a\x00b",
        "world//a",
        "world/a:b",
    ],
)
def test_unsafe_inventory_paths_rejected(tmp_path, name):
    source, files = make_archive(tmp_path)
    files[name] = {"bytes": 0, "sha256": hashlib.sha256(b"").hexdigest()}
    with pytest.raises(ValueError, match="Unsafe"):
        verify_archive(source, files)


@pytest.mark.parametrize(
    "names",
    [
        ("world/level.dat", "world/LEVEL.DAT"),
        ("world/a", "world/a/b"),
        ("world/A/b", "world/a/c"),
    ],
)
def test_casing_and_file_directory_collisions_refused(tmp_path, names):
    source, _ = make_archive(tmp_path)
    files = {
        name: {"bytes": 0, "sha256": hashlib.sha256(b"").hexdigest()} for name in names
    }
    with pytest.raises(ValueError):
        verify_archive(source, files)


def test_symlink_payload_and_crc_corruption_refused(tmp_path):
    source, files = make_archive(tmp_path)
    source.write_bytes(source.read_bytes().replace(b"dimension", b"DimEnsion"))
    with pytest.raises(BadZipFile, match="CRC"):
        verify_archive(source, files)
    other, files = make_archive(tmp_path, 1)
    # Rewrite an entry as a symlink without changing its apparent payload hash.
    target = tmp_path / "linked.zip"
    with ZipFile(other) as incoming, ZipFile(target, "x") as output:
        for info in incoming.infolist():
            if info.filename.endswith("level.dat"):
                info.create_system = 3
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
            output.writestr(info, incoming.read(info))
    with pytest.raises(ValueError, match="Unsafe"):
        verify_archive(target, files)


def test_low_free_space_fails_before_staging_or_retirement(tmp_path, monkeypatch):
    store = store_at(tmp_path)
    publish_next(store, tmp_path, 0)
    source, files = make_archive(tmp_path, 1)
    before = history(store)
    monkeypatch.setattr("omk.backup_store.shutil.disk_usage", lambda _: Mock(free=1))
    with pytest.raises(OSError, match="Insufficient"):
        store.publish(source, files)
    assert history(store) == before


def test_copy_enospc_preserves_history_and_blocks_unbounded_retries(
    tmp_path, monkeypatch
):
    store = store_at(tmp_path)
    first = publish_next(store, tmp_path, 0)
    second = publish_next(store, tmp_path, 1)
    source, files = make_archive(tmp_path, 2)
    before = history(store)

    def fail_copy(archive, target, size):
        target.write_bytes(b"interrupted")
        raise OSError(errno.ENOSPC, "synthetic full disk")

    monkeypatch.setattr(store, "_copy", fail_copy)
    with pytest.raises(OSError) as error:
        store.publish(source, files)
    assert error.value.errno == errno.ENOSPC
    for name, payload in before.items():
        assert (store.root / name).read_bytes() == payload
    assert (store.root / first["id"]).exists() and (store.root / second["id"]).exists()
    pending = list(store.root.glob("pending-*"))
    assert len(pending) == 1
    with pytest.raises(ValueError, match="operator inspection"):
        store.publish(source, files)
    assert list(store.root.glob("pending-*")) == pending


def test_corrupted_staged_copy_cannot_trigger_retention(tmp_path, monkeypatch):
    store = store_at(tmp_path)
    old = publish_next(store, tmp_path, 0)
    source, files = make_archive(tmp_path, 1)
    copy = store._copy

    def corrupt(archive, target, size):
        copy(archive, target, size)
        target.write_bytes(target.read_bytes().replace(b"level", b"LeVeL"))

    monkeypatch.setattr(store, "_copy", corrupt)
    with pytest.raises(ValueError, match="hash mismatch"):
        store.publish(source, files)
    assert (store.root / old["id"]).exists()
    assert len(list(store.root.glob("snapshot-*"))) == 1


def test_retirement_failure_leaves_new_and_previous_copy_readable(
    tmp_path, monkeypatch
):
    store = store_at(tmp_path)
    first = publish_next(store, tmp_path, 0)
    second = publish_next(store, tmp_path, 1)
    original = Path.unlink

    def fail_delete(path, *args, **kwargs):
        if path.parent.name.startswith("retired-"):
            raise OSError("synthetic failed retirement")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_delete)
    with pytest.raises(OSError, match="retirement"):
        publish_next(store, tmp_path, 2)
    assert not (store.root / first["id"]).exists()
    assert (store.root / second["id"] / "archive.zip").exists()
    assert len(list(store.root.glob("snapshot-*"))) == 2
    assert len(list(store.root.glob("retired-*"))) == 1
    for entry in store.root.glob("snapshot-*"):
        manifest = json.loads((entry / "manifest.json").read_bytes())
        verify_archive(entry / "archive.zip", manifest["files"], manifest["sha256"])
    with pytest.raises(ValueError, match="operator inspection"):
        store.inspect()


def test_lock_foreign_files_and_changed_owner_fail_closed(tmp_path):
    store = store_at(tmp_path)
    source, files = make_archive(tmp_path)
    with _lock(store.root), pytest.raises(OSError):
        store.publish(source, files)
    foreign = store.root / "unrelated.zip"
    foreign.write_bytes(b"preserve")
    with pytest.raises(ValueError, match="Foreign"):
        store.publish(source, files)
    assert foreign.read_bytes() == b"preserve"
    (store.root / "owner.json").write_text("{}")
    with pytest.raises(ValueError, match="Unowned"):
        BackupStore(store.root, store.policy)
    foreign.unlink()
    with pytest.raises(ValueError, match="Unowned"):
        store.publish(source, files)


def test_tampered_committed_archive_is_never_retired(tmp_path):
    store = store_at(tmp_path)
    first = publish_next(store, tmp_path, 0)
    publish_next(store, tmp_path, 1)
    path = store.root / first["id"] / "archive.zip"
    path.write_bytes(path.read_bytes().replace(b"level", b"LeVeL"))
    before = history(store)
    source, files = make_archive(tmp_path, 2)
    with pytest.raises(ValueError, match="hash mismatch"):
        store.publish(source, files)
    assert history(store) == before


def test_crash_after_promotion_does_not_accumulate_unbounded_copies(
    tmp_path, monkeypatch
):
    store = store_at(tmp_path)
    publish_next(store, tmp_path, 0)
    publish_next(store, tmp_path, 1)
    monkeypatch.setattr(store, "_retire", Mock(side_effect=OSError("interrupted")))
    with pytest.raises(OSError):
        publish_next(store, tmp_path, 2)
    assert len(store.inspect()) == 3
    with pytest.raises(ValueError, match="Unfinished retention"):
        publish_next(store, tmp_path, 3)
    assert len(store.inspect()) == 3


@pytest.mark.parametrize(
    "field,value",
    [
        ("sha256", None),
        ("sha256", "invalid"),
        ("schema", True),
        ("sequence", 0),
        ("bytes", -1),
    ],
)
def test_tampered_metadata_cannot_disable_readback(tmp_path, field, value):
    store = store_at(tmp_path)
    result = publish_next(store, tmp_path, 0)
    metadata = store.root / result["id"] / "manifest.json"
    data = json.loads(metadata.read_bytes())
    data[field] = value
    metadata.write_text(json.dumps(data))
    before = history(store)
    source, files = make_archive(tmp_path, 1)
    with pytest.raises(ValueError):
        store.publish(source, files)
    assert history(store) == before


def test_growth_of_input_during_copy_has_no_committed_marker(tmp_path, monkeypatch):
    store = store_at(tmp_path)
    first = publish_next(store, tmp_path, 0)
    source, files = make_archive(tmp_path, 1)
    original = store._copy

    def change_input(archive, target, size):
        with archive.open("ab") as stream:
            stream.write(b"changed")
        return original(archive, target, size)

    monkeypatch.setattr(store, "_copy", change_input)
    with pytest.raises(ValueError, match="input changed"):
        store.publish(source, files)
    assert [p.name for p in store.root.glob("snapshot-*")] == [first["id"]]


def test_manifest_budget_and_staging_budget_include_metadata(tmp_path):
    store = store_at(tmp_path)
    source, files = make_archive(tmp_path)
    store.policy = BackupPolicy(1024**2, 2, source.stat().st_size + 1, 1)
    before = history(store)
    with pytest.raises(ValueError, match="metadata exceed"):
        store.publish(source, files)
    assert history(store) == before


def test_symlinked_store_or_input_is_refused(tmp_path):
    store = store_at(tmp_path)
    source, files = make_archive(tmp_path)
    link = tmp_path / "linked-input.zip"
    try:
        link.symlink_to(source)
    except OSError:
        pytest.skip("Windows symlink privilege unavailable")
    with pytest.raises(ValueError, match="without links"):
        store.publish(link, files)
    directory = tmp_path / "linked-store"
    directory.symlink_to(store.root, target_is_directory=True)
    with pytest.raises(ValueError, match="Linked"):
        BackupStore(directory, store.policy)
