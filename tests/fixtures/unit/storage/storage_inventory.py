"""Test dependencies for storage inventory."""

import pytest


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
