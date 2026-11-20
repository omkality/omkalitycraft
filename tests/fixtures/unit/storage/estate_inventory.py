"""Test dependencies for estate inventory."""

import pytest


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
