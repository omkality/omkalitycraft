import json
from pathlib import Path

import pytest
from litestar.exceptions import HTTPException
from litestar.testing import TestClient

from api.app import app
from api.core.storage import instance_root, safe_resolve
from api.settings.config import settings


@pytest.fixture
def cdn_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(settings, "content_root", str(tmp_path))
    return tmp_path


def test_cdn_starts_without_account_services(cdn_root: Path) -> None:
    with TestClient(app=app) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/version").json()["version"] == "0.3.0.dev7"
        assert client.get("/instances").json() == []
        assert client.get("/auth/me").status_code == 404


def test_manifest_and_download_use_test_content(cdn_root: Path) -> None:
    instance = cdn_root / "instances" / "test"
    files = instance / "files"
    files.mkdir(parents=True)
    (files / "config.txt").write_text("fixture content", encoding="utf-8")
    (instance / "manifest.json").write_text(
        json.dumps({"files": {"config.txt": {"size": 15}}, "total_size": 15}),
        encoding="utf-8",
    )
    (instance / "instance_config.json").write_text(
        '{"display_name":"Test pack"}', encoding="utf-8"
    )
    with TestClient(app=app) as client:
        assert client.get("/instances").json()[0]["name"] == "Test pack"
        assert "config.txt" in client.get("/instances/test/manifest").json()["files"]
        assert (
            client.get("/download/instances/test/config.txt").text == "fixture content"
        )
        assert client.get("/download/instances/test/missing.txt").status_code == 404


@pytest.mark.parametrize("instance_id", ["..", ".", "../launcher", "a/b", "a\\b", ""])
def test_instance_id_cannot_escape_content_root(
    cdn_root: Path, instance_id: str
) -> None:
    with pytest.raises(HTTPException) as error:
        instance_root(instance_id)
    assert error.value.status_code == 400


def test_download_cannot_escape_content_root(tmp_path: Path) -> None:
    with pytest.raises(HTTPException) as error:
        safe_resolve(tmp_path / "files", "../account.json")
    assert error.value.status_code == 400
