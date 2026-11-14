import copy
import json
from pathlib import Path

import pytest

from launcher.client_defaults import prepare_client_defaults
from launcher.client_policy import ClientDefaults
from launcher.releases import Release, ReleaseError
from tests.unit.test_client_defaults import setup

OPTIONS = {
    "bobView": False,
    "gamma": 1.0,
    "autoJump": False,
    "guiScale": 2,
    "fov": 0.25,
}


def test_initial_game_options_work_without_other_defaults_and_preserve_changes(
    tmp_path,
):
    folder, release = setup(tmp_path)
    release.launch["client_defaults"] = {"initial_options": OPTIONS}
    prepare_client_defaults(release, folder)
    path = folder / "options.txt"
    initial = path.read_text(encoding="utf-8")
    for line in [
        "bobView:false",
        "gamma:1.0",
        "autoJump:false",
        "guiScale:2",
        "fov:0.25",
    ]:
        assert line + "\n" in initial
    personal = (
        initial.replace("bobView:false", "bobView:true")
        .replace("gamma:1.0", "gamma:0.5")
        .replace("autoJump:false", "autoJump:true")
        .replace("guiScale:2", "guiScale:3")
    )
    personal = personal.replace("fov:0.25", "fov:0.75")
    path.write_text(personal, encoding="utf-8")
    prepare_client_defaults(release, folder)
    prepare_client_defaults(release, folder)
    assert path.read_text(encoding="utf-8") == personal


def test_existing_options_are_preserved_while_missing_defaults_are_added(tmp_path):
    folder, release = setup(tmp_path)
    release.launch["client_defaults"] = {"initial_options": OPTIONS}
    path = folder / "options.txt"
    original = b"bobView:true\nguiScale:1\ncustomModSetting:personal\n"
    path.write_bytes(original)
    prepare_client_defaults(release, folder)
    actual = path.read_text(encoding="utf-8")
    assert "bobView:true\n" in actual and "guiScale:1\n" in actual
    assert "customModSetting:personal\n" in actual
    assert "autoJump:false\n" in actual and "gamma:1.0\n" in actual
    assert any(
        p.read_bytes() == original
        for p in (folder / ".omk-defaults-backups").glob("*options.txt")
    )


@pytest.mark.parametrize(
    "options",
    [
        [],
        {"fullscreen": True},
        {"bobView": 0},
        {"autoJump": "false"},
        {"gamma": True},
        {"gamma": float("nan")},
        {"gamma": float("inf")},
        {"gamma": 2},
        {"guiScale": True},
        {"guiScale": 2.0},
        {"guiScale": 4},
        {"guiScale\nfullscreen": 2},
        {"fov": 80},
        {"fov": True},
        {"fov": float("nan")},
    ],
)
def test_unreviewed_or_invalid_initial_options_are_rejected(options):
    with pytest.raises(ValueError):
        ClientDefaults.parse({"initial_options": options})


@pytest.mark.parametrize("minimum", [None, "0.3.0.dev12", "0.3.0.dev13"])
def test_signed_initial_options_require_a_capable_launcher(tmp_path, minimum):
    _, release = setup(tmp_path)
    payload = {
        "schema": 1 if minimum is None else 2,
        "pack_id": release.pack_id,
        "version": release.version,
        "minecraft": release.minecraft,
        "platform": release.platform,
        "loader": "forge",
        "launch": copy.deepcopy(release.launch),
        "files": [
            {"path": name, "sha256": "a" * 64, "size": 1}
            for name in [
                release.launch["java"],
                release.launch["agent"],
                *release.launch["classpath"],
            ]
        ],
    }
    payload["launch"]["client_defaults"] = {"initial_options": OPTIONS}
    if minimum is not None:
        payload["minimum_launcher_version"] = minimum
    if minimum != "0.3.0.dev13":
        with pytest.raises(ReleaseError):
            Release.parse(payload, {})
    else:
        parsed = Release.parse(payload, {})
        parsed.require_launcher("0.3.0.dev13")
        with pytest.raises(ReleaseError, match="обновление"):
            parsed.require_launcher("0.3.0.dev12")


def test_dj2_profile_has_reviewed_initial_game_options():
    profile = Path(__file__).resolve().parents[2] / "profiles/client-defaults/dj2.json"
    assert json.loads(profile.read_text(encoding="utf-8"))["initial_options"] == OPTIONS
