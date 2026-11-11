import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from omk import storage_inventory as worker

pytestmark = pytest.mark.skipif(
    not hasattr(os, "statvfs"), reason="Linux Docker filesystem accounting"
)


@pytest.fixture
def storage(tmp_path):
    request = {
        "schema": 1,
        "roles": ["source", "store", "reset", "restore"],
        "world": "world",
        "limits": {"max_entries": 2000, "max_depth": 64},
    }
    files = {
        "source/world/region/r.0.0.mca": b"world" * 100,
        "source/.omk-cutovers/old/previous/world/region/r.0.0.mca": b"old" * 300,
        "source/.omk-cutovers/partial/next/world/part": b"part" * 20,
        "source/logs/latest.log": b"a" * 110,
        "source/crash-reports/crash.txt": b"crash",
        "source/backups/legacy.zip": b"legacy" * 30,
        "source/server.properties": b"private configuration is never read",
        "store/store/snapshot-abc/archive.zip": b"zip" * 200,
        "store/pending-abc/incomplete": b"pending",
        "reset/world/data/file.dat": b"candidate" * 100,
        "restore/world/level.dat": b"restore" * 100,
    }
    for name, payload in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
    return request, tmp_path, files


def test_all_data_is_counted_including_retained_partial_and_legacy_files(
    storage, monkeypatch
):
    request, root, files = storage
    monkeypatch.setattr(
        Path, "read_bytes", lambda *a: pytest.fail("Read file contents")
    )
    report = worker.execute(request, root)
    buckets = {r["role"]: r["categories"] for r in report["resources"]}
    expected = {}
    for name, payload in files.items():
        role, *parts = name.split("/")
        key = (role, worker.category(role, parts, "world"))
        expected[key] = expected.get(key, 0) + len(payload)
    assert {
        (role, key): val["apparent_bytes"]
        for role, values in buckets.items()
        for key, val in values.items()
    } == expected
    assert sum(
        v["files"] for values in buckets.values() for v in values.values()
    ) == len(files)
    assert len(report["filesystems"]) == 1
    assert report["filesystems"][0]["roles"] == request["roles"]
    assert report["atomic_snapshot"] is False
    assert report["host_disk_complete"] is False
    assert report["backup_integrity_verified"] is False
    assert "private configuration" not in str(report)


@pytest.mark.parametrize("kind", ["symlink", "hardlink", "fifo", "alias"])
def test_links_special_files_and_aliased_roots_are_refused(storage, kind):
    request, root, _ = storage
    target = root / "source/world/region/r.0.0.mca"
    if kind == "symlink":
        (root / "store/link").symlink_to(target)
    elif kind == "hardlink":
        os.link(target, root / "store/linked")
    elif kind == "fifo":
        os.mkfifo(root / "store/pipe")
    else:
        request["roles"] = ["source", "source"]
    with pytest.raises(ValueError):
        worker.execute(request, root)


@pytest.mark.parametrize("limit,value", [("max_entries", 3), ("max_depth", 2)])
def test_configured_scan_bounds_do_not_return_partial_success(storage, limit, value):
    request, root, _ = storage
    request["limits"][limit] = value
    with pytest.raises(ValueError, match="bound"):
        worker.execute(request, root)


def test_file_mutation_during_scan_is_refused(storage, monkeypatch):
    request, root, _ = storage
    original = worker.scan

    def changed(*args):
        result = original(*args)
        if args[1] == "store":
            (root / "source/world/region/r.0.0.mca").write_bytes(b"changed")
        return result

    monkeypatch.setattr(worker, "scan", changed)
    with pytest.raises(ValueError, match="changed"):
        worker.execute(request, root)


def test_sparse_files_report_logical_and_allocated_space_separately(storage):
    request, root, _ = storage
    path = root / "store/sparse"
    with path.open("wb") as stream:
        stream.seek(16 * 1024**2)
        stream.write(b"x")
    value = worker.execute(request, root)["resources"][1]["categories"]["store"]
    assert value["apparent_bytes"] > 16 * 1024**2
    assert value["allocated_bytes"] < value["apparent_bytes"]


def test_shared_filesystem_uses_lowest_available_observation_for_every_role(
    storage, monkeypatch
):
    request, root, _ = storage
    available = iter([100, 100, 5, 50, 100, 100, 100, 100])
    monkeypatch.setattr(
        worker.os,
        "statvfs",
        lambda _: SimpleNamespace(
            f_bavail=next(available),
            f_frsize=4096,
            f_blocks=1000,
        ),
    )
    report = worker.execute(request, root)
    assert report["filesystems"][0]["available_bytes"] == 5 * 4096


@pytest.mark.parametrize(
    "edit",
    [
        {"schema": True},
        {"roles": ["source", "store", "unknown"]},
        {"world": "../world"},
        {"limits": {"max_entries": True, "max_depth": 64}},
        {"limits": {"max_entries": 1000001, "max_depth": 64}},
    ],
)
def test_invalid_request_refused(storage, edit):
    request, root, _ = storage
    with pytest.raises(ValueError):
        worker.execute({**request, **edit}, root)
