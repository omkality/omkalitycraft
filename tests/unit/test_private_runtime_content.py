from pathlib import Path

import pytest
from litestar.testing import TestClient

from api.app import app
from api.settings.config import settings
from scripts.generate_manifest import build_manifest
from scripts.stage_launcher_content import copy_path


@pytest.mark.parametrize(
    "relative",
    ["userdata/session.json", "AUTH_TOKEN.JSON", "config/.env", "session.json"],
)
def test_cdn_never_serves_account_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, relative: str
) -> None:
    monkeypatch.setattr(settings, "content_root", str(tmp_path))
    path = tmp_path / "launcher" / "files" / relative
    path.parent.mkdir(parents=True)
    path.write_text("test-private-runtime-data", encoding="utf-8")
    with TestClient(app=app) as client:
        response = client.get("/download/launcher/" + relative)
    assert response.status_code == 404
    assert "test-private-runtime-data" not in response.text


def test_manifest_excludes_portable_sessions(tmp_path: Path) -> None:
    (tmp_path / "userdata").mkdir()
    (tmp_path / "userdata" / "session.json").write_text("test-private-runtime-data")
    (tmp_path / "auth_token.json").write_text("test-private-runtime-data")
    (tmp_path / "launcher.bin").write_bytes(b"public-artifact")
    manifest = build_manifest(tmp_path, [], ["."], "launcher", "launcher")
    assert set(manifest["files"]) == {"launcher.bin"}


def test_staging_excludes_portable_sessions(tmp_path: Path) -> None:
    source, destination = tmp_path / "release", tmp_path / "staged"
    (source / "userdata").mkdir(parents=True)
    (source / "userdata" / "session.json").write_text("test-private-runtime-data")
    (source / "auth_token.json").write_text("test-private-runtime-data")
    (source / "launcher.bin").write_bytes(b"public-artifact")
    copy_path(source, destination)
    assert list(destination.iterdir()) == [destination / "launcher.bin"]
