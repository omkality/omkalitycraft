import importlib
from pathlib import Path

import pytest

from launcher.pack.client_defaults import prepare_client_defaults
from omk.labs.launcher.pack_install_lab import (
    PackDirectory,
    _options_preserved,
    run_pack_install_lab,
)
from omk.labs.launcher.pack_process_lab import run_pack_process_lab
from tests.fixtures.unit.launcher.pack_install_lab import pack_releases

__all__ = ["pack_releases"]


def test_signed_upgrade_lab_exercises_real_http_fault_and_preserves_settings(
    tmp_path, pack_releases
):
    roots, keys = pack_releases
    report = run_pack_install_lab(*roots, keys, lab_parent=tmp_path / "owned")
    assert report["ok"], report
    assert report["minecraft_started"] is False
    assert report["accepted_player_release"] is False
    assert report["fault_offsets"] == [0, 128 * 1024, 256 * 1024, 384 * 1024]
    assert "options_maps_saves_and_screenshots_preserved" in report["checks"]
    assert (
        "repair_downloads_only_deleted_and_same_size_corrupt_mods" in report["checks"]
    )
    assert report["obsolete_source_files"] == 1
    assert (Path(report["lab"]) / ".omk-owned-pack-install-lab").is_file()


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("fov:0.4", "fov:0.25"),
        ("renderDistance:7", "renderDistance:8"),
        ("lang:en_us", "lang:ru_ru"),
        ("gamma:1.0", "gamma:0.5"),
        ("resourcePacks:", "unexpected:1\nresourcePacks:"),
    ],
)
def test_upgrade_oracle_rejects_personal_changes_or_undeclared_additions(
    pack_releases, old, new
):
    roots, keys = pack_releases
    release = PackDirectory(roots[1], keys).release
    folder = roots[1] / "files"
    original = b'lang:en_us\nrenderDistance:7\nfov:0.4\nresourcePacks:["MyPack"]\n'
    path = folder / "options.txt"
    path.write_bytes(original)
    prepare_client_defaults(release, folder)
    assert _options_preserved(original, folder, release)
    valid = path.read_text(encoding="utf-8")
    assert old in valid
    path.write_text(valid.replace(old, new), encoding="utf-8")
    assert not _options_preserved(original, folder, release)


def test_upgrade_oracle_requires_exact_original_backup(pack_releases):
    roots, keys = pack_releases
    release = PackDirectory(roots[1], keys).release
    folder = roots[1] / "files"
    original = b"renderDistance:7\nfov:0.4\n"
    (folder / "options.txt").write_bytes(original)
    prepare_client_defaults(release, folder)
    assert _options_preserved(original, folder, release)
    next((folder / ".omk-defaults-backups").glob("*-options.txt")).unlink()
    assert not _options_preserved(original, folder, release)


@pytest.mark.parametrize("module", ["pack_install_lab", "pack_process_lab"])
def test_both_labs_detect_personal_fov_reset(
    tmp_path, pack_releases, monkeypatch, module
):
    lab = importlib.import_module("omk.labs.launcher." + module)
    roots, keys = pack_releases

    def bad_defaults(release, folder):
        prepare_client_defaults(release, folder)
        if release.version == "new":
            path = folder / "options.txt"
            text = path.read_text(encoding="utf-8")
            assert "fov:0.4" in text
            path.write_text(text.replace("fov:0.4", "fov:0.25"), encoding="utf-8")

    monkeypatch.setattr(lab, "prepare_client_defaults", bad_defaults)
    report = getattr(lab, "run_" + module)(*roots, keys, lab_parent=tmp_path / "owned")
    assert report["ok"] is False
    assert report["error"] in {
        "options_maps_saves_and_screenshots_preserved",
        "options_journeymap_saves_screenshots_preserved",
    }


def test_actual_killed_installer_process_recovers_using_only_persisted_state(
    tmp_path, pack_releases
):
    roots, keys = pack_releases
    report = run_pack_process_lab(*roots, keys, lab_parent=tmp_path / "owned")
    assert report["ok"], report
    assert report["killed_child_exit_code"] != 0
    assert report["restarted_child_exit_code"] == 0
    assert report["owned_child_stopped"]
    assert report["partial_bytes_after_kill"] >= 256 * 1024
    assert report["range_offsets"][0] == 0
    assert any(offset > 0 for offset in report["range_offsets"][1:])
    assert len(report["checks"]) == 15
