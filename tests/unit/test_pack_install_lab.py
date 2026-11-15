import base64
import hashlib
import importlib
import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from launcher.client_defaults import prepare_client_defaults
from launcher.install import current_platform
from launcher.version import VERSION
from omk.pack_install_lab import PackDirectory, _options_preserved, run_pack_install_lab
from omk.pack_process_lab import run_pack_process_lab
from omk.publish import build_release


@pytest.fixture
def pack_releases(tmp_path):
    key = Ed25519PrivateKey.generate()
    # The same signer is sufficient here; the full DJ2 lab also verifies key rotation.
    public = key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    keys = {hashlib.sha256(public).hexdigest()[:16]: base64.b64encode(public).decode()}
    defaults = json.loads(
        Path("profiles/client-defaults/dj2.json").read_text(encoding="utf-8")
    )
    roots = []
    for version in ["old", "new"]:
        root = tmp_path / version
        files = root / "files"
        payload = {
            "runtime/bin/java": b"not an executable runtime",
            "agent.jar": b"not an executable agent",
            "forge.jar": b"not an executable loader",
            "mods/keep.jar": b"not an executable mod",
            f"mods/{version}.jar": version.encode() * (512 * 1024),
            "resourcepacks/FM_NewFont/pack.mcmeta": b'{"pack":{"pack_format":3}}',
            "resources/empty.txt": b"",
        }
        for name, data in payload.items():
            path = files / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        launch = {
            "java": "runtime/bin/java",
            "agent": "agent.jar",
            "classpath": ["forge.jar"],
            "main_class": "net.minecraft.launchwrapper.Launch",
            "assets": "assets",
            "natives": "natives",
            "game_args": ["--username", "{username}"],
            "client_defaults": {
                **{
                    k: v
                    for k, v in defaults.items()
                    if version != "old"
                    or k not in {"initial_options", "initial_keybindings"}
                },
                "servers": [
                    {"id": "omk-dj2", "name": version, "address": "127.0.0.1:25576"}
                ],
            },
        }
        envelope = build_release(
            files,
            pack_id="dj2",
            version=version,
            minecraft="1.12.2",
            platform=current_platform(),
            launch=launch,
            key=key,
            minimum_launcher_version=VERSION,
        )
        (root / "manifest.json").write_text(json.dumps(envelope), encoding="utf-8")
        roots.append(root)
    return roots, keys


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
    lab = importlib.import_module("omk." + module)
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
