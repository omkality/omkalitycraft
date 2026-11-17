import json
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from omk import owner_metrics as metrics
from omk.admin import _write_private
from tests.unit.test_operator_commands import config


def row(name, value="0", stamp=None, **labels):
    return {
        "metric": {"__name__": name, "host": "test", "service": "dj2", **labels},
        "value": [time.time() if stamp is None else stamp, value],
    }


def test_zero_is_fresh_but_stale_nan_wrong_service_and_duplicate_are_not_zero():
    now = time.time()
    rows = [
        row("omk_game_online"),
        row("omk_game_tps", "NaN"),
        row("mem_used_percent", "0", now - 120),
        row("cpu_usage_idle", "90", cpu="cpu-total"),
        row("disk_used_percent", "30", path="/storage/project"),
    ]
    values = {v["key"]: v for v in metrics.project(rows, "test", "dj2", now)}
    assert values["game_players"]["value"] == 0.0
    assert values["host_cpu"]["value"] == 10.0
    assert (
        values["host_ram"]["state"] == "stale" and values["host_ram"]["value"] is None
    )
    assert values["game_tps"]["state"] == "invalid"
    assert all(v["value"] is None for v in metrics.project(rows, "other", "dj2", now))
    rows += [row("omk_game_online")]
    assert metrics.project(rows, "test", "dj2", now)[-1]["state"] == "invalid"


@contextmanager
def endpoint(payload, status=200, location=None):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append(self.path)
            self.send_response(status)
            if location:
                self.send_header("Location", location)
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


@pytest.mark.parametrize(
    "payload",
    [b"bad", b"x" * 65537, b'{"status":"error"}'],
    ids=["invalid-json", "oversized", "failed-query"],
)
def test_failed_http_response_never_fakes_empty_metrics(tmp_path, payload):
    settings, _ = config(tmp_path)
    with endpoint(payload) as (origin, requests):
        _write_private(
            settings.private / "tui.json",
            settings.private,
            {"schema": 1, "host": "test", "prometheus_origin": origin},
        )
        state, values = metrics.sample(settings, "dj2")
    assert state == "unavailable" and all(v["value"] is None for v in values)
    assert len(requests) == 1


def test_real_http_projection_and_redirect_rejection(tmp_path):
    settings, _ = config(tmp_path)
    payload = json.dumps(
        {
            "status": "success",
            "data": {"resultType": "vector", "result": [row("omk_game_online", "2")]},
        }
    ).encode()
    with endpoint(payload) as (origin, requests):
        _write_private(
            settings.private / "tui.json",
            settings.private,
            {"schema": 1, "host": "test", "prometheus_origin": origin},
        )
        state, values = metrics.sample(settings, "dj2")
    assert state == "partial" and values[-1]["value"] == 2.0
    assert "query=" in requests[0]
    with endpoint(b"", 302, "http://127.0.0.1:1/private") as (origin, requests):
        _write_private(
            settings.private / "tui.json",
            settings.private,
            {"schema": 1, "host": "test", "prometheus_origin": origin},
        )
        assert metrics.sample(settings, "dj2")[0] == "unavailable"
    assert len(requests) == 1
