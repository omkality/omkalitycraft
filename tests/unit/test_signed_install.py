import json
from pathlib import Path

import pytest

from launcher.client_defaults import prepare_client_defaults
from launcher.install import (
    InstallCancelled,
    Installer,
    ReleaseClient,
    current_platform,
)
from launcher.releases import ReleaseError, read_release, safe_path, sha256_file
from omk.publish import build_release, signing_key
from tests.http_fixture import serve


@pytest.fixture
def repository(tmp_path: Path):
    root = tmp_path / "cdn"
    folder = root / "releases" / "dj2" / current_platform()
    files = folder / "files"
    for name in [
        "runtime/bin/java",
        "agent.jar",
        "forge.jar",
        "mods/old.jar",
        "config/test.cfg",
    ]:
        path = files / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((name * 1000).encode())
    public = tmp_path / "public.json"
    key = signing_key(tmp_path / "private.pem", public)
    launch = {
        "java": "runtime/bin/java",
        "agent": "agent.jar",
        "classpath": ["forge.jar"],
        "main_class": "net.minecraft.launchwrapper.Launch",
        "assets": "assets",
        "natives": "natives",
        "game_args": ["--username", "{username}"],
    }
    envelope = build_release(
        files,
        pack_id="dj2",
        version="1.0",
        minecraft="1.12.2",
        platform=current_platform(),
        launch=launch,
        key=key,
    )
    (folder / "manifest.json").write_text(json.dumps(envelope))
    return root, files, envelope, json.loads(public.read_text()), key


@pytest.mark.parametrize(
    "path",
    [
        "../evil",
        "a/../evil",
        "/absolute",
        "C:/evil",
        "a\\b",
        "AUX.txt",
        "mods/a. ",
        "userdata/session.json",
        "saves/player/region",
        "world/level.dat",
        ".omk-install.json",
        "mods/.env",
    ],
)
def test_release_rejects_unsafe_paths(path: str):
    with pytest.raises(ReleaseError):
        safe_path(path)


def test_manifest_tampering_is_rejected(repository):
    _, _, envelope, keys, _ = repository
    envelope["manifest"]["version"] = "tampered"
    with pytest.raises(ReleaseError):
        read_release(json.dumps(envelope).encode(), keys)


def test_download_resume_repair_and_user_data(repository, tmp_path: Path):
    root, _, envelope, keys, _ = repository
    with serve(root) as (url, requests):
        installer = Installer(tmp_path / "portable", ReleaseClient(url, keys))
        release = installer.client.fetch("dj2")
        partial_file = release.files[0]
        partial = installer.root / f"cache/downloads/{partial_file.sha256}.part"
        partial.parent.mkdir(parents=True)
        source = root / f"releases/dj2/{current_platform()}/files/{partial_file.path}"
        partial.write_bytes(source.read_bytes()[:25])
        progress = []
        folder = installer.install(release, progress.append)
        assert any(offset == 25 for _, offset in requests)
        assert progress[-1].percent == 100
        assert installer.local_state("dj2")["state"] == "installed"
        (folder / "saves").mkdir()
        (folder / "saves/personal.dat").write_bytes(b"keep me")
        managed = folder / release.files[1].path
        managed.write_bytes(b"corrupted")
        requests.clear()
        installer.install(release, progress.append)
        assert len(requests) == 1
        assert (folder / "saves/personal.dat").read_bytes() == b"keep me"
        requests.clear()
        installer.install(release, progress.append)
        assert requests == []
        assert (
            read_release(json.dumps(envelope).encode(), keys).digest == release.digest
        )


def test_bad_file_hash_never_becomes_installed(repository, tmp_path: Path):
    root, files, _, keys, _ = repository
    (files / "forge.jar").write_bytes(b"wrong content" * 1000)
    with serve(root) as (url, _):
        installer = Installer(tmp_path / "portable", ReleaseClient(url, keys))
        with pytest.raises(ReleaseError):
            installer.install(installer.client.fetch("dj2"), lambda _: None)
        assert installer.local_state("dj2")["state"] == "incomplete"


def test_deleted_files_and_same_size_corruption_repair_without_resetting_maps(
    repository, tmp_path: Path
):
    root, files, envelope, keys, key = repository
    defaults = json.loads(
        (
            Path(__file__).resolve().parents[2] / "profiles/client-defaults/dj2.json"
        ).read_text(encoding="utf-8")
    )
    font = files / "resourcepacks/FM_NewFont/pack.mcmeta"
    font.parent.mkdir(parents=True)
    font.write_text('{"pack":{"pack_format":3}}')
    launch = {**envelope["manifest"]["launch"], "client_defaults": defaults}
    release = read_release(
        json.dumps(
            build_release(
                files,
                pack_id="dj2",
                version="1.1",
                minecraft="1.12.2",
                platform=current_platform(),
                launch=launch,
                key=key,
            )
        ).encode(),
        keys,
    )
    with serve(root) as (url, requests):
        installer = Installer(tmp_path / "portable", ReleaseClient(url, keys))
        folder = installer.install(release, lambda _: None)
        prepare_client_defaults(release, folder)
        minimap = folder / "journeymap/config/5.7/journeymap.minimap.config"
        personal = b'{"shape":"Circle","showGrid":"true","sizePercent":"24"}'
        minimap.write_bytes(personal)
        saves = folder / "saves/personal.dat"
        saves.parent.mkdir()
        saves.write_bytes(b"user save sentinel")
        options = (folder / "options.txt").read_bytes()
        deleted = [
            "runtime/bin/java",
            "mods/old.jar",
            "config/test.cfg",
            "resourcepacks/FM_NewFont/pack.mcmeta",
        ]
        for name in deleted:
            (folder / name).unlink()
        forge = folder / "forge.jar"
        forge.write_bytes(b"X" * forge.stat().st_size)
        assert installer.local_state("dj2")["state"] == "incomplete"
        requests.clear()
        installer.install(release, lambda _: None)
        prepare_client_defaults(release, folder)
        assert len(requests) == 5  # Only four missing artifacts and one altered hash.
        assert installer.local_state("dj2")["state"] == "installed"
        assert all(
            sha256_file(folder / file.path) == file.sha256 for file in release.files
        )
        assert minimap.read_bytes() == personal
        assert saves.read_bytes() == b"user save sentinel"
        assert (folder / "options.txt").read_bytes() == options
        # A new signed release may change defaults, but never an existing personal map.
        defaults["initial_configs"][0]["content"]["shape"] = "Rectangle"
        updated = read_release(
            json.dumps(
                build_release(
                    files,
                    pack_id="dj2",
                    version="1.2",
                    minecraft="1.12.2",
                    platform=current_platform(),
                    launch=launch,
                    key=key,
                )
            ).encode(),
            keys,
        )
        requests.clear()
        installer.install(updated, lambda _: None)
        prepare_client_defaults(updated, folder)
        assert requests == [] and minimap.read_bytes() == personal
        # Losing the launcher install record also must not erase personal game state.
        (folder / ".omk-install.json").write_text("broken metadata")
        installer.install(updated, lambda _: None)
        prepare_client_defaults(updated, folder)
        assert (
            minimap.read_bytes() == personal
            and saves.read_bytes() == b"user save sentinel"
        )


def test_cancelled_download_is_not_ready(repository, tmp_path: Path):
    root, _, _, keys, _ = repository
    with serve(root) as (url, _):
        installer = Installer(tmp_path / "portable", ReleaseClient(url, keys))
        release = installer.client.fetch("dj2")
        installer.cancel.set()
        with pytest.raises(InstallCancelled):
            installer.install(release, lambda _: None)
        assert installer.local_state("dj2")["state"] != "installed"


def test_interrupted_upgrade_remembers_obsolete_files_without_deleting_user_files(
    repository, tmp_path: Path
):
    root, files, envelope, keys, key = repository
    with serve(root) as (url, _):
        installer = Installer(tmp_path / "portable", ReleaseClient(url, keys))
        old = installer.client.fetch("dj2")
        folder = installer.install(old, lambda _: None)
        (folder / "mods/personal.jar").write_bytes(b"user-owned test fixture")
        (files / "mods/old.jar").unlink()
        (files / "mods/new.jar").write_bytes(b"new managed content")
        updated = build_release(
            files,
            pack_id="dj2",
            version="2.0",
            minecraft="1.12.2",
            platform=current_platform(),
            launch=envelope["manifest"]["launch"],
            key=key,
        )
        release = read_release(json.dumps(updated).encode(), keys)

        def pause(progress):
            if progress.stage.startswith("Скачиваем"):
                installer.cancel.set()

        with pytest.raises(InstallCancelled):
            installer.install(release, pause)
        assert installer.local_state("dj2")["state"] == "incomplete"
        installer.cancel.clear()
        installer.install(release, lambda _: None)
        assert not (folder / "mods/old.jar").exists()
        assert (folder / "mods/new.jar").read_bytes() == b"new managed content"
        assert (folder / "mods/personal.jar").read_bytes() == b"user-owned test fixture"
