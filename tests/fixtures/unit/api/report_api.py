"""Test dependencies for report api."""

from uuid import uuid4

import pytest
from litestar.testing import TestClient

from api.app import create_app
from api.settings.config import settings


@pytest.fixture
def api(tmp_path, monkeypatch):
    root = tmp_path / ".omk-admin/reports"
    monkeypatch.setattr(settings, "content_root", str(tmp_path / "cdn"))
    monkeypatch.setattr(settings, "client_reports_root", str(root))
    monkeypatch.setattr(settings, "client_reports_auth_url", "http://127.0.0.1:1")
    player = uuid4().hex
    monkeypatch.setattr(
        "api.routes.reports.DraslClient.request", lambda *a, **kw: {"id": player}
    )
    with TestClient(app=create_app()) as client:
        yield client, root, player
