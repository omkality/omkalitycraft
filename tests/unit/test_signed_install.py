import json
import os
from pathlib import Path

import pytest

from launcher.install import (
    InstallCancelled,
    Installer,
    ReleaseClient,
    current_platform,
)
from launcher.pack.client_defaults import prepare_client_defaults
from launcher.releases import ReleaseError, read_release, safe_path, sha256_file
from launcher.version import VERSION
from omk.publish import build_release, signing_key
from omk.release_store import ReleaseStore, ReleaseStorePolicy
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


@pytest.mark.parametrize("replacement_name", ["old.jar", "new.jar"])
def test_unmanaged_discovery_cache_survives_check_repair_and_pack_update(
    repository, tmp_path: Path, replacement_name: str
):
    root, files, envelope, keys, key = repository
    with serve(root) as (url, requests):
        installer = Installer(tmp_path / "portable", ReleaseClient(url, keys))
        release = installer.client.fetch("dj2")
        folder = installer.install(release, lambda _: None)
        cache = folder / "vintagefix/transformerCache/jarDiscoverer.cache"
        cache.parent.mkdir(parents=True)
        # A byte sentinel tests ownership, not VintageFix's binary cache parser.
        sentinel = b"local runtime cache owned by the mod"
        cache.write_bytes(sentinel)
        requests.clear()
        installer.install(release, lambda _: None)
        assert requests == []
        assert cache.read_bytes() == sentinel

        (folder / "mods/old.jar").unlink()
        installer.install(release, lambda _: None)
        assert len(requests) == 1
        assert (folder / "mods/old.jar").read_bytes() == (
            files / "mods/old.jar"
        ).read_bytes()
        assert cache.read_bytes() == sentinel

        os.utime(folder / "mods/old.jar", (1, 1))
        if replacement_name != "old.jar":
            (files / "mods/old.jar").unlink()
        (files / "mods" / replacement_name).write_bytes(b"new reviewed mod version")
        updated = build_release(
            files,
            pack_id="dj2",
            version="2.0",
            minecraft="1.12.2",
            platform=current_platform(),
            launch=envelope["manifest"]["launch"],
            key=key,
        )
        (files.parent / "manifest.json").write_text(json.dumps(updated))
        updated_release = installer.client.fetch("dj2")
        requests.clear()
        installer.install(updated_release, lambda _: None)
        assert len(requests) == 1
        if replacement_name != "old.jar":
            assert not (folder / "mods/old.jar").exists()
        installed = folder / "mods" / replacement_name
        assert installed.read_bytes() == b"new reviewed mod version"
        assert installed.stat().st_mtime_ns != 1_000_000_000
        assert cache.read_bytes() == sentinel


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
                minimum_launcher_version=VERSION,
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
                    minimum_launcher_version=VERSION,
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


@pytest.mark.parametrize("interruption", [None, "missing", "bad_hash"])
def test_return_to_retained_client_removes_only_added_language_file(
    repository, tmp_path: Path, interruption
):
    root, files, envelope, keys, key = repository
    launch = envelope["manifest"]["launch"]

    def sign(source, version):
        return build_release(
            source,
            pack_id="dj2",
            version=version,
            minecraft="1.12.2",
            platform=current_platform(),
            launch=launch,
            key=key,
            minimum_launcher_version=VERSION,
        )

    original = sign(files, "1.0")
    retained = ReleaseStore.create(
        tmp_path / "retained", ReleaseStorePolicy(1024**2, 1), keys
    )
    snapshot = retained.publish(files, original)
    old_bytes = (snapshot.files / "mods/old.jar").read_bytes()
    added = "resources/omkalityclient/lang/ru_ru.lang"
    with serve(root) as (url, _):
        installer = Installer(tmp_path / "portable", ReleaseClient(url, keys))
        folder = installer.install(
            read_release(json.dumps(original).encode(), keys), lambda _: None
        )
        personal = {
            "options.txt": b"key_roots.keybinds.spell_library:199:SHIFT\n",
            "journeymap/config/5.7/personal.json": b'{"shape":"Circle"}',
            "saves/personal.dat": b"player save fixture",
            "resources/omkalityclient/lang/notes.txt": b"unmanaged neighbour",
        }
        for name, content in personal.items():
            destination = folder / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
        session = installer.root / "userdata/session.json"
        session.parent.mkdir()
        session.write_bytes(b"revocable game session fixture")
        (files / added).parent.mkdir(parents=True)
        (files / added).write_text("AutoRun=Автобег\n", encoding="utf-8")
        (files / "mods/old.jar").write_bytes(b"candidate mod fixture")
        candidate = sign(files, "2.0")
        installer.install(
            read_release(json.dumps(candidate).encode(), keys), lambda _: None
        )
        assert (folder / added).is_file()
        # Return old payload with a NEW signed generation and the same security floor.
        returned = sign(snapshot.files, "3.0")
        assert returned["manifest"]["files"] == original["manifest"]["files"]
        assert returned["manifest"]["minimum_launcher_version"] == VERSION
        release = read_release(json.dumps(returned).encode(), keys)
        if interruption:
            if interruption == "missing":
                (files / "mods/old.jar").unlink()
            else:
                (files / "mods/old.jar").write_bytes(b"x" * len(old_bytes))
            with pytest.raises(ReleaseError):
                installer.install(release, lambda _: None)
            assert installer.local_state("dj2")["state"] == "incomplete"
            assert (folder / added).is_file()
            assert (folder / "mods/old.jar").read_bytes() == b"candidate mod fixture"
            assert all(
                (folder / name).read_bytes() == data for name, data in personal.items()
            )
            assert session.read_bytes() == b"revocable game session fixture"
            installer.cancel.clear()
        for artifact in snapshot.release.files:
            (files / artifact.path).write_bytes(
                (snapshot.files / artifact.path).read_bytes()
            )
        installer.install(release, lambda _: None)
        assert not (folder / added).exists()
        assert (folder / "mods/old.jar").read_bytes() == old_bytes
        assert all(
            (folder / name).read_bytes() == data for name, data in personal.items()
        )
        assert session.read_bytes() == b"revocable game session fixture"
        assert installer.local_state("dj2")["state"] == "installed"
        assert retained.verify(snapshot.release.digest).release.version == "1.0"


def test_numbered_generations_preserve_files_and_allow_operator_restore(
    repository, tmp_path, monkeypatch
):
    root, files, envelope, keys, key = repository
    manifest = files.parent / "manifest.json"
    launch = envelope["manifest"]["launch"]

    def publish(version, generation, content):
        (files / "forge.jar").write_bytes(content)
        published = build_release(
            files,
            pack_id="dj2",
            version=version,
            minecraft="1.12.2",
            platform=current_platform(),
            launch=launch,
            key=key,
            generation=generation,
        )
        manifest.write_text(json.dumps(published), encoding="utf-8")
        return read_release(manifest.read_bytes(), keys)

    legacy = read_release(manifest.read_bytes(), keys)
    with serve(root) as (url, requests):
        client = ReleaseClient(url, keys, minimum_generations={"dj2": 2})
        installer = Installer(tmp_path / "portable", client)
        with pytest.raises(ReleaseError):
            client.fetch("dj2")
        with pytest.raises(ReleaseError):
            installer.install(legacy, lambda _: None)

        current = publish("2.0", 2, b"current content")
        assert client.fetch("dj2") == current
        folder = installer.install(current, lambda _: None, clean_mods=True)
        requests.clear()
        installer.install(current, lambda _: None, clean_mods=True)
        assert requests == []

        newer = publish("3.0", 3, b"new content")
        marker = folder / ".omk-install.json"
        accepted = marker.read_bytes()
        keep = folder / "mods/local.jar"
        keep.write_bytes(b"cleanup must wait until acceptance")

        def cannot_write(*_args):
            raise OSError("owned test storage unavailable")

        with monkeypatch.context() as patch:
            patch.setattr("launcher.install.atomic_write", cannot_write)
            with pytest.raises(OSError):
                installer.install(newer, lambda _: None, clean_mods=True)
        assert marker.read_bytes() == accepted
        assert keep.exists()
        assert (folder / "forge.jar").read_bytes() == b"current content"

        installer.install(newer, lambda _: None, clean_mods=True)
        reopened = Installer(installer.root, ReleaseClient(url, keys))
        requests.clear()
        with pytest.raises(ReleaseError):
            reopened.install(current, lambda _: None, clean_mods=True)
        conflict = publish("3.1", 3, b"different content")
        with pytest.raises(ReleaseError):
            reopened.install(conflict, lambda _: None, clean_mods=True)
        assert requests == []
        assert (folder / "forge.jar").read_bytes() == b"new content"

        restored = publish("4.0", 4, b"current content")
        reopened.install(restored, lambda _: None)
        assert reopened.local_state("dj2")["release"] == restored
        assert (folder / "forge.jar").read_bytes() == b"current content"
