import os
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from omk import estate_inventory as worker

pytestmark = pytest.mark.skipif(
    not hasattr(os, "statvfs"), reason="Linux Docker volume accounting"
)


@pytest.fixture
def census(tmp_path):
    resources = [
        {"id": "game-a", "role": "source", "world": "first"},
        {"id": "store-a", "role": "store", "world": "first"},
        {"id": "game-b", "role": "source", "world": "second"},
        {"id": "auth", "role": "auth", "world": "world"},
        {"id": "content", "role": "content", "world": "world"},
    ]
    files = {
        "game-a/first/level.dat": b"a" * 10,
        "game-b/second/level.dat": b"b" * 20,
        "game-a/.omk-cutovers/partial/next/first/file": b"old" * 10,
        "store-a/incoming.zip": b"partial" * 4,
        "auth/drasl.db": b"secret-database-canary",
        "auth/key.pkcs8": b"private-key-canary",
        "content/packs/current.zip": b"payload" * 30,
    }
    for name, value in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value)
    return (
        {
            "schema": 1,
            "resources": resources,
            "limits": {"max_entries": 1000, "max_depth": 64},
        },
        tmp_path,
        files,
    )


def test_multiple_worlds_and_shared_auth_are_counted_without_reading_secrets(
    census, monkeypatch
):
    request, root, files = census
    monkeypatch.setattr(
        Path, "read_bytes", lambda *a: pytest.fail("Census read file contents")
    )
    value = worker.execute(request, root)
    assert sum(
        v["files"] for r in value["resources"] for v in r["categories"].values()
    ) == len(files)
    assert sum(
        v["apparent_bytes"]
        for r in value["resources"]
        for v in r["categories"].values()
    ) == sum(map(len, files.values()))
    assert value["resources"][0]["categories"]["active_world"]["apparent_bytes"] == 10
    assert value["resources"][2]["categories"]["active_world"]["apparent_bytes"] == 20
    assert len(value["filesystems"]) == 1
    assert value["filesystems"][0]["resources"] == [
        r["id"] for r in request["resources"]
    ]
    assert "private-key-canary" not in str(value) and "drasl.db" not in str(value)
    assert not value["atomic_snapshot"] and not value["backup_integrity_verified"]


@pytest.mark.parametrize("kind", ["entries", "depth", "link", "mutation"])
def test_partial_or_changing_census_does_not_return_success(census, monkeypatch, kind):
    request, root, _ = census
    if kind == "entries":
        request["limits"]["max_entries"] = 4
    elif kind == "depth":
        request["limits"]["max_depth"] = 1
    elif kind == "link":
        (root / "auth/link").symlink_to(root / "game-a")
    else:
        scan = worker.scan

        def changed(*args):
            value = scan(*args)
            if args[1] == "auth":
                (root / "game-a/first/level.dat").write_bytes(b"changed")
            return value

        monkeypatch.setattr(worker, "scan", changed)
    with pytest.raises(ValueError):
        worker.execute(request, root)


def test_every_mount_contributes_to_minimum_available_space(census, monkeypatch):
    request, root, _ = census
    free = iter([100, 100, 5, 50, 100, 100, 100, 100, 100, 100])
    monkeypatch.setattr(
        worker.os,
        "statvfs",
        lambda _: SimpleNamespace(f_bavail=next(free), f_frsize=4096, f_blocks=1000),
    )
    assert (
        worker.execute(request, root)["filesystems"][0]["available_bytes"] == 5 * 4096
    )


@pytest.mark.parametrize(
    "kind", ["id", "duplicate", "role", "world", "schema", "auth", "bound"]
)
def test_ambiguous_requests_refused(census, kind):
    request, root, _ = census
    request = deepcopy(request)
    if kind == "schema":
        request["schema"] = True
    elif kind == "auth":
        request["resources"] = [r for r in request["resources"] if r["role"] != "auth"]
    elif kind == "bound":
        request["limits"]["max_entries"] = 1000001
    elif kind == "duplicate":
        request["resources"].append(dict(request["resources"][0]))
    else:
        request["resources"][0][kind] = {
            "id": "../escape",
            "role": "unknown",
            "world": "../data",
        }[kind]
    with pytest.raises(ValueError):
        worker.execute(request, root)
