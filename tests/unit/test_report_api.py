import json
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from litestar.testing import TestClient

from api.app import create_app
from api.settings.config import settings
from omk.drasl import DraslError
from omk.report_store import ReportConflict, ReportLimit, ReportStore
from tests.unit.test_client_incidents import report

TOKEN = "fixture_game_token_not_real"


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


def test_upload_is_authenticated_private_and_idempotent(api):
    client, root, player = api
    value = report(player, detail="Failure api_token=" + TOKEN)
    assert client.post("/reports/client", json=value).status_code == 401
    assert (
        client.post(
            "/reports/client", json=value, headers={"Authorization": "Bearer " + TOKEN}
        ).status_code
        == 201
    )
    assert (
        client.post(
            "/reports/client", json=value, headers={"Authorization": "Bearer " + TOKEN}
        ).status_code
        == 201
    )
    saved = ReportStore(root).get(value["id"])
    assert TOKEN not in json.dumps(saved)
    assert len(ReportStore(root).list()) == 1
    for url in ["/reports/client", "/reports/client/" + value["id"], "/admin/reports"]:
        response = client.get(url, headers={"Authorization": "Bearer " + TOKEN})
        assert response.status_code in {404, 405}
        assert "Failure" not in response.text


def test_player_cannot_impersonate_another_report_owner(api):
    client, _root, _player = api
    assert (
        client.post(
            "/reports/client",
            json=report(),
            headers={"Authorization": "Bearer " + TOKEN},
        ).status_code
        == 409
    )


def test_running_report_schema_two_keeps_unknown_exit_and_private_run_metadata(api):
    client, root, player = api
    run = uuid4().hex
    value = report(
        player, schema=2, run_id=run, process_state="running", exit_code=None
    )
    response = client.post(
        "/reports/client", json=value, headers={"Authorization": "Bearer " + TOKEN}
    )
    assert response.status_code == 201
    store = ReportStore(root)
    saved = store.get(value["id"])
    assert saved["exit_code"] is None and saved["process_state"] == "running"
    summary = store.list()[0]
    assert summary["run_id"] == run and summary["exit_code"] is None
    assert summary["process_state"] == "running" and "detail" not in summary


def test_revoked_session_is_not_accepted(api, monkeypatch):
    client, root, player = api

    def denied(*args, **kwargs):
        raise DraslError(403)

    monkeypatch.setattr("api.routes.reports.DraslClient.request", denied)
    assert (
        client.post(
            "/reports/client",
            json=report(player),
            headers={"Authorization": "Bearer " + TOKEN},
        ).status_code
        == 401
    )
    assert not root.exists()


def test_body_limit_and_per_account_limit(api):
    client, _root, player = api
    headers = {"Authorization": "Bearer " + TOKEN}
    assert (
        client.post(
            "/reports/client", content=b"x" * (129 * 1024), headers=headers
        ).status_code
        == 413
    )
    for _ in range(3):
        assert (
            client.post(
                "/reports/client", json=report(player), headers=headers
            ).status_code
            == 201
        )
    assert (
        client.post("/reports/client", json=report(player), headers=headers).status_code
        == 429
    )


def test_storage_under_cdn_is_rejected(api, monkeypatch):
    client, root, player = api
    monkeypatch.setattr(settings, "content_root", str(root.parent))
    assert (
        client.post(
            "/reports/client",
            json=report(player),
            headers={"Authorization": "Bearer " + TOKEN},
        ).status_code
        == 503
    )


def test_unconfigured_inbox_does_not_enable_collection(api, monkeypatch):
    client, root, player = api
    monkeypatch.setattr(settings, "client_reports_root", None)
    assert (
        client.post(
            "/reports/client",
            json=report(player),
            headers={"Authorization": "Bearer " + TOKEN},
        ).status_code
        == 404
    )
    assert not root.exists()


def test_global_retention_bounds_total_report_count(tmp_path):
    store = ReportStore(tmp_path / "reports")
    value = report()
    store.ingest(value, player=value["player"], token=TOKEN)
    now = int(time.time())
    with sqlite3.connect(store.path) as db:
        for _ in range(1005):
            item = report()
            db.execute(
                "INSERT INTO reports VALUES (?,?,?,?,?)",
                (item["id"], item["player"], now, "fixture", json.dumps(item)),
            )
    store.prune()
    with sqlite3.connect(store.path) as db:
        assert db.execute("SELECT count(*) FROM reports").fetchone()[0] == 1000


def test_retention_expires_old_reports_and_preserves_newest_twenty_per_player(tmp_path):
    store = ReportStore(tmp_path / "reports")
    player = uuid4().hex
    start = int(time.time()) - 30 * 86400
    for index in range(30):
        store.ingest(
            report(player), player=player, token=TOKEN, now=start + index * 86400
        )
    newest = report(player)
    store.ingest(newest, player=player, token=TOKEN)
    assert store.get(newest["id"])["id"] == newest["id"]
    assert len(store.list(limit=100)) <= 15
    with sqlite3.connect(store.path) as db:
        assert db.execute("SELECT count(*) FROM reports").fetchone()[0] <= 20


def test_concurrent_identical_reports_remain_one_record(tmp_path):
    store = ReportStore(tmp_path / "reports")
    value = report()
    # Initialize schema before exercising concurrent transactions from separate connections.
    store.ingest(value, player=value["player"], token=TOKEN)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(
            pool.map(
                lambda _: store.ingest(value, player=value["player"], token=TOKEN),
                range(12),
            )
        )
    assert all(v["ok"] for v in results) and len(store.list()) == 1
    with pytest.raises(ReportConflict):
        store.ingest(
            {**value, "detail": "different"}, player=value["player"], token=TOKEN
        )


@pytest.mark.parametrize("workers", [2, 4, 8])
def test_concurrent_first_uploads_initialize_one_private_inbox(tmp_path, workers):
    store = ReportStore(tmp_path / "reports")
    values = [report() for _ in range(8)]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(
            pool.map(lambda v: store.ingest(v, player=v["player"], token=TOKEN), values)
        )
    assert all(value["ok"] for value in results)
    assert len(store.list()) == 8


def test_report_rate_limit_does_not_share_the_cdn_rate_bucket(api):
    client, _root, player = api
    for _ in range(20):
        assert client.post("/reports/client", json=report(player)).status_code == 401
    assert client.post("/reports/client", json=report(player)).status_code == 429
    assert client.get("/health").status_code == 200


def test_account_quota_survives_eviction_of_old_report_bodies(tmp_path):
    store = ReportStore(tmp_path / "reports")
    player = uuid4().hex
    for _ in range(3):
        store.ingest(report(player), player=player, token=TOKEN)
    # Model count-based retention in this isolated inbox, not a schema reset.
    with sqlite3.connect(store.path) as db:
        db.execute("DELETE FROM reports WHERE player=?", (player,))
    with pytest.raises(ReportLimit):
        store.ingest(report(player), player=player, token=TOKEN)
