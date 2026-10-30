import hashlib
import os
import subprocess
from dataclasses import replace
from unittest.mock import patch

import pytest

from launcher.game import GameRunner
from launcher.mod_policy import clean_extra_mods, verify_mods
from launcher.releases import Artifact, ReleaseError
from tests.unit.test_game_runner import fixture


def prepared(tmp_path):
    folder, release, session = fixture(tmp_path)
    artifacts = []
    for name in [
        "mods/KnownMod.jar",
        "mods/1.12.2/Core.jar",
        "mods/memory_repo/Library.jar.meta",
    ]:
        path = folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        data = b"signed test content"
        path.write_bytes(data)
        artifacts.append(Artifact(name, hashlib.sha256(data).hexdigest(), len(data)))
    return folder, replace(release, files=tuple(artifacts)), session


def test_extras_removed_silently_without_touching_signed_mods_or_player_files(tmp_path):
    folder, release, _ = prepared(tmp_path)
    extras = [
        "mods/added.jar",
        "mods/1.12.2/extra.zip",
        "coremods/extra.jar",
        "mods/expanded/Example.class",
    ]
    for name in [
        *extras,
        "journeymap/personal.config",
        "saves/test.dat",
        "resourcepacks/personal.zip",
    ]:
        path = folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"personal test content")
    assert clean_extra_mods(release, folder) == 4
    assert all(not (folder / name).exists() for name in extras)
    assert (folder / "saves/test.dat").exists()
    assert (folder / "journeymap/personal.config").exists()
    assert (folder / "resourcepacks/personal.zip").exists()
    verify_mods(release, folder)
    assert clean_extra_mods(release, folder) == 0


def test_altered_or_missing_signed_mod_blocks_process_creation(tmp_path):
    folder, release, session = prepared(tmp_path)
    mod = folder / "mods/KnownMod.jar"
    mod.write_bytes(b"X" * mod.stat().st_size)
    with patch("launcher.game.subprocess.Popen") as start:
        with pytest.raises(ReleaseError):
            GameRunner(tmp_path).start(release, folder, session)
        start.assert_not_called()
    mod.unlink()
    with pytest.raises(ReleaseError):
        verify_mods(release, folder)


def test_extra_symlink_is_removed_without_following_its_target(tmp_path):
    folder, release, _ = prepared(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "keep.jar"
    sentinel.write_bytes(b"outside sentinel")
    link = folder / "mods/linked"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Creating directory symlinks requires local Windows privileges")
    clean_extra_mods(release, folder)
    assert not link.is_symlink() and sentinel.read_bytes() == b"outside sentinel"


@pytest.mark.skipif(os.name != "nt", reason="Windows junction safety")
def test_extra_windows_junction_does_not_remove_target(tmp_path):
    folder, release, _ = prepared(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "keep.jar"
    sentinel.write_bytes(b"outside sentinel")
    link = folder / "mods/junction"
    subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(outside)],
        capture_output=True,
        check=True,
    )
    assert link.is_junction()
    clean_extra_mods(release, folder)
    assert not link.exists() and sentinel.read_bytes() == b"outside sentinel"
