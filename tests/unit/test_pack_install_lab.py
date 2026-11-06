import base64
import hashlib
import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from launcher.install import current_platform
from launcher.version import VERSION
from omk.pack_install_lab import run_pack_install_lab
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
                **defaults,
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
