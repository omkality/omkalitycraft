import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from omk.cli import main
from omk.owner.admin import _write_private
from omk.owner.panels import owner_tps_history as history
from tests.fixtures.unit.observability.owner_metrics import endpoint
from tests.fixtures.unit.owner.operator_commands import config


def series(values, **labels):
    return {"metric": {"host": "test", "service": "dj2", **labels}, "values": values}


def test_zero_remains_a_measurement_and_absent_or_nan_points_remain_gaps():
    points = history.project(
        [series([[700, "0"], [710, "NaN"], [715, "20"]])],
        {"host": "test"},
        "dj2",
        700,
        1000,
    )
    assert len(points) == 61
    assert [p.tps for p in points[:4]] == [0.0, None, None, 20.0]


@pytest.mark.parametrize(
    "rows",
    [
        [series([[701, "20"]])],
        [series([[1005, "20"]])],
        [series([[700, "20"], [700, "19"]])],
        [series([[705, "20"], [700, "19"]])],
        [series([[700, "20"]], service="other")],
        [series([[700, "20"]]), series([[700, "19"]])],
        [series([[700 + i * 5, "20"] for i in range(62)])],
    ],
    ids=[
        "off-grid",
        "future",
        "duplicate",
        "unordered",
        "wrong-server",
        "ambiguous",
        "too-many",
    ],
)
def test_ambiguous_or_malformed_history_never_draws_a_guessed_curve(rows):
    with pytest.raises(ValueError):
        history.project(rows, {"host": "test"}, "dj2", 700, 1000)


def test_real_range_http_is_bounded_bound_and_preserves_outage(tmp_path, monkeypatch):
    settings, path = config(tmp_path)
    monkeypatch.setattr(history.time, "time", lambda: 1002)
    payload = json.dumps(
        {
            "status": "success",
            "data": {
                "resultType": "matrix",
                "result": [series([[700, "20"], [705, "18"], [720, "19"]])],
            },
        }
    ).encode()
    with endpoint(payload) as (origin, requests):
        _write_private(
            settings.private / "tui.json",
            settings.private,
            {"schema": 1, "host": "test", "prometheus_origin": origin},
        )
        result = history.run(path, "dj2")
    value = history.TpsHistory.model_validate(result)
    assert value.ok and value.state == "partial" and value.points[2].tps is None
    request = urlsplit(requests[0])
    query = parse_qs(request.query)
    assert request.path == "/api/v1/query_range" and query["step"] == ["5"]
    assert query["start"] == ["700"] and query["end"] == ["1000"]
    assert 'service="dj2"' in query["query"][0] and "(up == 1)" in query["query"][0]


@pytest.mark.parametrize(
    "payload",
    [
        b"bad",
        b"x" * 65537,
        b'{"status":"success","data":{"resultType":"vector","result":[]}}',
    ],
    ids=["bad-json", "size-limit", "wrong-result-type"],
)
def test_query_failure_is_not_a_zero_tps_history(tmp_path, payload):
    settings, path = config(tmp_path)
    with endpoint(payload) as (origin, _):
        _write_private(
            settings.private / "tui.json",
            settings.private,
            {"schema": 1, "host": "test", "prometheus_origin": origin},
        )
        value = history.run(path, "dj2")
    assert not value["ok"] and value["state"] == "unavailable" and not value["points"]
    assert value["error"] == "history_unavailable"


def test_empty_matrix_is_an_explicit_missing_history(tmp_path):
    settings, path = config(tmp_path)
    payload = b'{"status":"success","data":{"resultType":"matrix","result":[]}}'
    with endpoint(payload) as (origin, _):
        _write_private(
            settings.private / "tui.json",
            settings.private,
            {"schema": 1, "host": "test", "prometheus_origin": origin},
        )
        value = history.run(path, "dj2")
    assert value["ok"] and value["state"] == "missing"
    assert len(value["points"]) == 61 and all(p["tps"] is None for p in value["points"])


@pytest.mark.parametrize("window", ["5m", "15m", "1h", "3h"])
def test_all_periods_are_bounded_and_long_periods_preserve_interval_minima(
    tmp_path, monkeypatch, window
):
    settings, path = config(tmp_path)
    monkeypatch.setattr(history.time, "time", lambda: 12002)
    duration, step = history.WINDOWS[window]
    start, end = 12000 - duration, 12000
    payload = json.dumps(
        {
            "status": "success",
            "data": {
                "resultType": "matrix",
                "result": [series([[start, "20"], [start + step, "7"], [end, "19"]])],
            },
        }
    ).encode()
    with endpoint(payload) as (origin, requests):
        _write_private(
            settings.private / "tui.json",
            settings.private,
            {"schema": 1, "host": "test", "prometheus_origin": origin},
        )
        value = history.run(path, "dj2", window)
    assert value["ok"] and value["state"] == "partial"
    assert len(value["points"]) == 61 and value["step"] == step
    assert value["end"] == end and value["end"] - value["start"] == duration
    assert value["points"][1]["tps"] == 7 and value["points"][2]["tps"] is None
    params = parse_qs(urlsplit(requests[0]).query)
    assert params["step"] == [str(step)]
    if step > 5:
        assert (
            "min_over_time(" in params["query"][0]
            and f"[{step}s]" in params["query"][0]
        )
    else:
        assert "min_over_time(" not in params["query"][0]


def test_cli_is_read_only_and_keeps_older_result_contract(tmp_path, capsys):
    _, path = config(tmp_path)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    prefix = ["admin", "--config", str(path)]
    assert main([*prefix, "tps-history", "--server", "dj2"]) == 0
    assert (
        history.TpsHistory.model_validate_json(capsys.readouterr().out).state
        == "disabled"
    )
    assert before == {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert main([*prefix, "tps-history", "--server", "other"]) == 1
    assert (
        history.TpsHistory.model_validate_json(capsys.readouterr().out).error
        == "invalid_configuration"
    )
    assert (
        main([*prefix, "--result-version", "1", "tps-history", "--server", "dj2"]) == 1
    )
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "unsupported_action"


def test_published_history_schema_matches_model():
    path = Path(__file__).parents[3] / "docs/contracts/owner-tps-history-v1.schema.json"
    assert json.loads(path.read_bytes()) == history.TpsHistory.model_json_schema()
