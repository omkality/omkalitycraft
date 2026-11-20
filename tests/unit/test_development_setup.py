from pathlib import Path

import pytest

from api.settings.content import (
    get_instance_config,
    get_instance_manifest_settings,
    get_launch_profile,
    get_launcher_manifest_settings,
)
from omk.profiles import load_profiles


def test_content_settings_survive_api_directory_move() -> None:
    assert get_instance_config("divinejourney2")
    assert get_launch_profile("divinejourney2")
    assert get_instance_manifest_settings("divinejourney2")
    assert get_launcher_manifest_settings()


def test_shipped_profile_catalog_has_only_dj2() -> None:
    (dj2,) = load_profiles()
    assert dj2.id == "dj2"
    assert dj2.status == "legacy"
    assert dj2.utilities_adapter == "ftbutilities_112"


def test_duplicate_server_id_is_rejected(tmp_path: Path) -> None:
    entry = """
[[servers]]
id = "duplicate"
name = "Test"
minecraft = "1.12.2"
pack_version = "test"
loader = "forge"
utilities_adapter = "ftbutilities_112"
status = "testing"
"""
    path = tmp_path / "profiles.toml"
    path.write_text("schema_version = 1\n" + entry * 2, encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate"):
        load_profiles(path)
