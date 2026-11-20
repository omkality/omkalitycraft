"""Test dependencies for project export."""

import copy
import json
import sqlite3
import sys
import zipfile
from types import SimpleNamespace

import pytest

from omk.distribution import component_archive as archive
from omk.distribution.publish import build_release, signing_key
from omk.distribution.release_store import ReleaseStore, ReleaseStorePolicy
from omk.owner.storage import project_export as project


@pytest.fixture
def clients(tmp_path):
    source = tmp_path / "client-files"
    (source / "runtime").mkdir(parents=True)
    for name in ("runtime/java", "agent.jar", "forge.jar", "locale.lang"):
        (source / name).write_bytes(b"opaque signed fixture; not a game")
    key = signing_key(tmp_path / "client-key.pem", tmp_path / "client-keys.json")
    keys = json.loads((tmp_path / "client-keys.json").read_bytes())
    store = ReleaseStore.create(
        tmp_path / "client-store", ReleaseStorePolicy(1024**2, 1), keys
    )

    def publish(
        platform="windows-x64", pack_id="fixture", minecraft="1.12.2", version="one"
    ):
        envelope = build_release(
            source,
            pack_id=pack_id,
            version=version,
            minecraft=minecraft,
            platform=platform,
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
        return store.publish(source, envelope)

    snapshots = {p: publish(p) for p in ("windows-x64", "linux-x64")}
    return SimpleNamespace(
        source=source, keys=keys, store=store, snapshots=snapshots, publish=publish
    )


@pytest.fixture
def fixture(tmp_path, clients):
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
    return SimpleNamespace(
        args=args,
        client_args={"client_store": clients.store, "client_pack_id": "fixture"},
        stopped=stopped,
        out=tmp_path / "out",
    )


@pytest.fixture
def release_context(clients):
    return {
        "source_commit": "1" * 40,
        "client_manifests": {p: s.release.digest for p, s in clients.snapshots.items()},
        "declared_state_contract": "dj2-2.23.4-world-v1",
    }
