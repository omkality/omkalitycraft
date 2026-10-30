from pathlib import Path

import pytest
from litestar.testing import TestClient

from api.app import create_app
from api.settings.config import settings


def test_readonly_update_routes_and_content_guards(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(settings, "content_root", str(tmp_path))
    metadata = tmp_path / "updates/metadata"
    metadata.mkdir(parents=True)
    (metadata / "timestamp.json").write_text('{"fixture":true}')
    (metadata / "private.pem").write_text("not a real key")
    target = tmp_path / "updates/targets/windows-x64/launcher.zip"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"fixture archive")
    with TestClient(create_app()) as client:
        response = client.get("/updates/metadata/timestamp.json")
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-cache"
        assert (
            client.get("/updates/targets/windows-x64/launcher.zip").content
            == b"fixture archive"
        )
        assert client.get("/updates/metadata/private.pem").status_code == 404
        assert (
            client.get("/updates/targets/windows-x64/session.json").status_code == 404
        )
        assert (
            client.post("/updates/metadata/timestamp.json", json={}).status_code == 405
        )


def test_cdn_rate_limit_rejects_excess_requests():
    with TestClient(create_app(requests_per_second=2)) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/health").status_code == 200
        assert client.get("/health").status_code == 429
