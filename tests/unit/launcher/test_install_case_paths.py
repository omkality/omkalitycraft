"""Signed update/return on the actual filesystem, including entry aliases."""

import os
from pathlib import Path

import pytest

from launcher.install import (
    InstallCancelled,
)
from launcher.releases import ReleaseError, sha256_file
from tests.fixtures.unit.launcher.install_case_paths import case_install, repository

__all__ = ["case_install", "repository"]


def assert_generation(installer, release, name, payload):
    folder = installer.directory("dj2")
    assert (folder / name).read_bytes() == payload
    assert all(sha256_file(folder / f.path) == f.sha256 for f in release.files)
    assert installer.local_state("dj2")["state"] == "installed"
    # Observe actual entries, not case-insensitive Path equality or inode equality.
    assert len(list((folder / "resources").rglob("*.json"))) == 1


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("resources/item/Tile.json", "resources/item/tile.json"),
        ("resources/item/tile.json", "resources/item/Tile.json"),
        ("resources/Item/tile.json", "resources/item/tile.json"),
        ("resources/Item/Tile.json", "resources/item/tile.json"),
    ],
)
@pytest.mark.parametrize("same_payload", [False, True])
def test_signed_case_update_repair_and_new_generation_return(
    case_install, old, new, same_payload
):
    installer, generation = case_install
    first = b'{"generation":"old"}'
    second = first if same_payload else b'{"generation":"new"}'
    with generation(old, first, "1.0") as (release, _):
        folder = installer.install(release, lambda _: None)
    personal = {
        "options.txt": b"personal settings",
        "saves/player.dat": b"personal world",
        "resources/unmanaged/notes.txt": b"unmanaged neighbour",
    }
    for name, data in personal.items():
        path = folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    for name, data, version in [(new, second, "2.0"), (old, first, "3.0")]:
        with generation(name, data, version) as (release, requests):
            installer.install(release, lambda _: None)
            assert_generation(installer, release, name, data)
            assert all((folder / p).read_bytes() == b for p, b in personal.items())
            requests.clear()
            installer.install(release, lambda _: None)
            assert requests == []
            # Repair missing/corrupt payload without changing the accepted generation.
            (folder / name).write_bytes(b"corrupted")
            installer.install(release, lambda _: None)
            assert len(requests) == 1
            assert_generation(installer, release, name, data)


def require_distinct_entries(folder):
    probe = folder / "CaseProbe"
    probe.write_bytes(b"filesystem case probe")
    insensitive = (folder / "caseprobe").exists()
    probe.unlink()
    if insensitive:
        pytest.skip("This filesystem aliases case-only names; cycle controls still run")


@pytest.mark.parametrize("link", ["hardlink", "symlink", "directory_symlink"])
def test_cleanup_distinguishes_link_entries_from_current_entry(case_install, link):
    installer, generation = case_install
    old = (
        "resources/Item/Tile.json"
        if link == "directory_symlink"
        else "resources/item/Tile.json"
    )
    new = old.lower()
    payload = b"same signed bytes"
    with generation(old, payload, "1.0") as (release, _):
        folder = installer.install(release, lambda _: None)
    require_distinct_entries(folder)
    source, target = folder / old, folder / new
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        if link == "directory_symlink":
            # Same directory entry through two differently spelled parent paths.
            new = "resources/item/Tile.json"
            (folder / "resources/item").rmdir()
            (folder / "resources/item").symlink_to(
                source.parent, target_is_directory=True
            )
        elif link == "hardlink":
            target.hardlink_to(source)
        else:
            target.write_bytes(payload)
            source.unlink()
            source.symlink_to(target)
    except OSError as error:
        pytest.skip(f"Filesystem does not permit this link: {error}")
    with generation(new, payload, "2.0") as (release, requests):
        installer.install(release, lambda _: None)
        assert requests == []
        assert (folder / new).read_bytes() == payload
        assert installer.local_state("dj2")["state"] == "installed"
        if link == "directory_symlink":
            assert source.read_bytes() == payload
        else:
            assert not source.exists() and not source.is_symlink()


@pytest.mark.parametrize("failure", ["cancel", "hash", "cleanup"])
def test_interrupted_case_update_retains_history_and_can_retry(
    case_install, monkeypatch, failure
):
    installer, generation = case_install
    old, new = "resources/item/Tile.json", "resources/item/tile.json"
    with generation(old, b"first generation", "1.0") as (release, _):
        folder = installer.install(release, lambda _: None)
    if failure == "cleanup":
        require_distinct_entries(folder)
    personal = folder / "resources/item/personal.txt"
    personal.write_bytes(b"personal neighbour")
    with generation(new, b"second generation", "2.0") as (release, _):
        original_download = installer._download
        original_unlink = Path.unlink
        original_stream = installer._stream

        def download(*args):
            original_download(*args)
            if failure == "cancel":
                installer.cancel.set()

        def stream(release, artifact, temporary, progress):
            original_stream(release, artifact, temporary, progress)
            temporary.write_bytes(b"invalid downloaded bytes")

        def unlink(path, *args, **kwargs):
            if path == folder / old:
                raise PermissionError("Injected obsolete-entry unlink failure")
            return original_unlink(path, *args, **kwargs)

        with monkeypatch.context() as patch:
            if failure == "cleanup":
                patch.setattr(Path, "unlink", unlink)
            elif failure == "cancel":
                patch.setattr(installer, "_download", download)
            else:
                patch.setattr(installer, "_stream", stream)
            expected = PermissionError if failure == "cleanup" else ReleaseError
            with pytest.raises(expected):
                installer.install(release, lambda _: None)
        state = installer.local_state("dj2")
        assert state["state"] == "incomplete"
        assert [v.version for v in state["history"]] == ["1.0"]
        assert personal.read_bytes() == b"personal neighbour"
        installer.cancel.clear()
        installer.install(release, lambda _: None)
        assert_generation(installer, release, new, b"second generation")
        assert personal.read_bytes() == b"personal neighbour"


def test_cleanup_cannot_follow_obsolete_link_outside_install(case_install, tmp_path):
    installer, generation = case_install
    old, new = "resources/item/Tile.json", "resources/item/tile.json"
    with generation(old, b"first", "1.0") as (release, _):
        folder = installer.install(release, lambda _: None)
    require_distinct_entries(folder)
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"outside sentinel")
    with generation(new, b"second", "2.0") as (release, _):
        # Retain signed history as an interrupted update would.
        installer._state(
            folder,
            release,
            complete=False,
            history=[installer.local_state("dj2")["release"]],
        )
        (folder / old).unlink()
        try:
            (folder / old).symlink_to(outside)
        except OSError as error:
            pytest.skip(f"Filesystem does not permit symlinks: {error}")
        with pytest.raises(ReleaseError, match="пределы"):
            installer.install(release, lambda _: None)
        assert outside.read_bytes() == b"outside sentinel"
        assert installer.local_state("dj2")["state"] == "incomplete"


def test_new_generation_return_after_interrupted_case_update(case_install, monkeypatch):
    installer, generation = case_install
    old, new = "resources/item/tile.json", "resources/item/Tile.json"
    with generation(old, b"original bytes", "1.0") as (release, _):
        installer.install(release, lambda _: None)
    with generation(new, b"candidate bytes", "2.0") as (release, _):
        original = installer._download

        def pause(*args):
            original(*args)
            installer.cancel.set()

        with monkeypatch.context() as patch:
            patch.setattr(installer, "_download", pause)
            with pytest.raises(InstallCancelled):
                installer.install(release, lambda _: None)
    assert installer.local_state("dj2")["state"] == "incomplete"
    installer.cancel.clear()
    with generation(old, b"original bytes", "3.0") as (release, requests):
        installer.install(release, lambda _: None)
        assert_generation(installer, release, old, b"original bytes")
        requests.clear()
        installer.install(release, lambda _: None)
        assert requests == []


def test_obsolete_signed_name_replaced_by_personal_directory_is_not_removed(
    case_install,
):
    installer, generation = case_install
    old, new = "resources/item/Tile.json", "resources/item/tile.json"
    with generation(old, b"first", "1.0") as (release, _):
        folder = installer.install(release, lambda _: None)
    require_distinct_entries(folder)
    path = folder / old
    path.unlink()
    path.mkdir()
    personal = path / "personal.txt"
    personal.write_bytes(b"personal directory sentinel")
    with generation(new, b"second", "2.0") as (release, _):
        installer.install(release, lambda _: None)
        assert (folder / new).read_bytes() == b"second"
        assert personal.read_bytes() == b"personal directory sentinel"
        assert installer.local_state("dj2")["state"] == "installed"


def test_entry_inspection_error_preserves_current_file_and_retry(
    case_install, monkeypatch
):
    installer, generation = case_install
    old, new = "resources/item/Tile.json", "resources/item/tile.json"
    with generation(old, b"same bytes", "1.0") as (release, _):
        folder = installer.install(release, lambda _: None)
    source, target = folder / old, folder / new
    if not target.exists():
        target.hardlink_to(source)
    with generation(new, b"same bytes", "2.0") as (release, _):
        original = os.scandir

        def fail_parent(path):
            if Path(path) == source.parent:
                raise PermissionError("Injected parent inspection failure")
            return original(path)

        with monkeypatch.context() as patch:
            patch.setattr(os, "scandir", fail_parent)
            with pytest.raises(PermissionError):
                installer.install(release, lambda _: None)
        assert target.read_bytes() == b"same bytes"
        assert installer.local_state("dj2")["state"] == "incomplete"
        installer.install(release, lambda _: None)
        assert_generation(installer, release, new, b"same bytes")
