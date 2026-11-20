"""Test dependencies for project policy."""

import copy
import gzip
import hashlib
import shutil
import zipfile
from types import SimpleNamespace

import pytest

from launcher.nbt import write_nbt
from omk.backups import ftb_restore_authority as ftb
from omk.distribution import component_archive as archive
from omk.owner.storage import (
    project_export,
    project_stage as raw,
)
from omk.worlds.linux_restore_policy import LISTS, RANKS
from tests.fixtures.unit.storage.project_export import (
    clients as client_fixture,
    fixture as capture_fixture,
)
from tests.fixtures.unit.worlds.linux_restore_policy import records

OLD_SECRET = "old-rcon-fixture-password-123456"

NEW_SECRET = "current-rcon-fixture-password-654321"


def properties(secret, *, current=False):
    return (
        "level-name=lab-world\nonline-mode=true\nwhite-list="
        + ("true" if current else "false")
        + "\nserver-ip=\nserver-port=25576\nenable-rcon=true\nrcon.port=25575\nrcon.password="
        + secret
        + "\npvp=true\ndifficulty=3\nmax-players=20\nmotd="
        + ("current" if current else "selected")
        + "\n"
    ).encode()


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    clients = client_fixture.__wrapped__(tmp_path)
    base = capture_fixture.__wrapped__(tmp_path, clients)
    game, world = base.args["game"], base.args["game"] / "lab-world"
    old = records("owner")
    for name, value in old.items():
        path = world / "data/ftb_lib" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(gzip.compress(write_nbt("", value), mtime=0))
    claims = world / "data/ftb_lib/teams/claimedchunks/base.dat"
    claims.parent.mkdir(parents=True, exist_ok=True)
    claims.write_bytes(b"historical claimed chunks")
    (world / "progress.dat").write_bytes(b"historical progress")
    (game / "mods").mkdir()
    pins = {n: hashlib.sha256(n.encode()).hexdigest() for n in ftb.PINS}
    for name in pins:
        (game / "mods" / name).write_bytes(name.encode())
    monkeypatch.setattr(ftb, "PINS", pins)
    (game / "mods/versioned.jar").write_bytes(b"selected old mod")
    for name in LISTS:
        (game / name).write_text("[]")
    (game / "ops.json").write_text('[{"name":"historical-op"}]')
    (game / RANKS).parent.mkdir(parents=True)
    (game / RANKS).write_bytes(b"old ranks")
    (game / "server.properties").write_bytes(properties(OLD_SECRET))
    current = tmp_path / "current"
    shutil.copytree(game, current)
    (current / "server.properties").write_bytes(properties(NEW_SECRET, current=True))
    (current / "ops.json").write_text("[]")
    (current / "banned-players.json").write_text('[{"name":"guest"}]')
    (current / RANKS).write_bytes(b"current ranks")
    (current / "mods/versioned.jar").write_bytes(b"newer mod being rolled back")
    now = copy.deepcopy(old)
    now["teams/base.dat"]["Players"].value.clear()
    now["players/owner.dat"]["Data"].value["ftbutilities"].value["Homes"].value.clear()
    for name, value in now.items():
        (current / "lab-world/data/ftb_lib" / name).write_bytes(
            gzip.compress(write_nbt("", value), mtime=0)
        )
    with zipfile.ZipFile(base.args["world_zip"], "w", zipfile.ZIP_DEFLATED) as z:
        for p in world.rglob("*"):
            if p.is_file():
                z.write(p, p.relative_to(game).as_posix())
    files = project_export.world_inventory(
        world, world_name="lab-world", path_policy="linux-server"
    )
    base.args["world_json"].unlink()
    archive.json_write(
        base.args["world_json"],
        {
            "schema": 1,
            "sequence": 1,
            "sha256": archive.digest(base.args["world_zip"]),
            "bytes": base.args["world_zip"].stat().st_size,
            "files": files,
        },
    )
    export = project_export.capture(
        base.out,
        release_context={
            "source_commit": "1" * 40,
            "client_manifests": {
                "windows-x64": clients.snapshots["windows-x64"].release.digest
            },
            "declared_state_contract": "fixture-v1",
        },
        **base.client_args,
        **base.args,
    )
    target = tmp_path / "candidate"
    target.mkdir(mode=0o700)
    expected = raw.plan(
        base.out,
        target,
        operation="d" * 32,
        world="lab-world",
        selection={
            "project_sha256": archive.digest(base.out / "project.json"),
            "release_identity": export["manifest"]["release_identity"],
        },
        settings=base.args["settings"],
    )
    raw.stage(base.out, target, expected=expected)
    return SimpleNamespace(
        source=base.out, target=target, current=current, raw=expected, old=old
    )
