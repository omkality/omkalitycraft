import json
import re
from itertools import pairwise

import pytest

from omk.cli import main
from omk.owner.admin import _write_private
from omk.owner.panels import owner_capacity_report as report
from tests.fixtures.unit.observability.owner_metrics import endpoint
from tests.fixtures.unit.owner.operator_commands import config

NOW = 1_790_000_321
HOUR = NOW // 3600 * 3600


@pytest.mark.parametrize(
    ("window", "step", "expected"),
    [("24h", 60, 1440), ("7d", 300, 2016), ("14d", 300, 4032)],
)
def test_capacity_summarizes_only_completed_hours(
    tmp_path, capsys, monkeypatch, window, step, expected
):
    settings, path = config(tmp_path)
    _write_private(
        settings.private / "tui.json",
        settings.private,
        {"schema": 1, "host": "test", "prometheus_origin": "http://127.0.0.1:9000"},
    )
    monkeypatch.setattr(report.time, "time", lambda: NOW)
    first = HOUR - expected * step
    observed = [0, 1, 2, 95, 96, expected - 2, expected - 1]
    sample_values = {
        "players": dict(zip(observed, [0, 1, 3, 1, 0, 2, 1], strict=True)),
        "host_cpu_p95_percent": dict.fromkeys(observed, 65) | {0: 99, 96: 100},
        "game_memory_max_bytes": {0: 9000, 2: 3500, 3: 9500, 95: 2100},
        "game_tps_min": {1: 20, 95: 0, expected - 1: 18},
        "project_disk_free_min_bytes": {0: 1000, 1: 1010},
    }
    chunks = []

    def sample(_settings, expression, *, result_type, start, end, step):
        assert result_type == "matrix"
        assert end - start < report.BATCH_POINTS * step
        assert 'host="test"' in expression
        assert 'service="dj2"' in expression
        assert 'timestamp(up{job="dj2"})' in expression
        chunks.append((start, end))
        rows = []
        for name in re.findall(r'"stat", "([^"]+)"', expression):
            values = [
                [first + point * step, str(value)]
                for point, value in sample_values.get(name, {}).items()
                if start <= first + point * step <= end
            ]
            if values:
                rows.append(
                    {"metric": {"host": "test", "stat": name}, "values": values}
                )
        return rows

    monkeypatch.setattr(report, "query", sample)
    assert (
        main(
            [
                "admin",
                "--config",
                str(path),
                "capacity-report",
                "--server",
                "dj2",
                "--window",
                window,
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert result["state"] == "partial"
    assert result["end_exclusive"] == HOUR
    assert result["start"] == first
    assert chunks[0][0] == first and chunks[-1][1] == HOUR - step
    assert all(left[1] + step == right[0] for left, right in pairwise(chunks))
    assert result["coverage"] == {
        "expected": expected,
        "with_players": 5,
        "without_players": 2,
        "unknown": expected - 7,
        "peak_players": 3,
    }
    assert result["metrics"]["host_cpu_p95_percent"] == {"value": 65, "samples": 5}
    assert result["metrics"]["game_tps_min"] == {"value": 0, "samples": 3}
    assert result["metrics"]["game_cpu_p95_vcpus"] == {"value": None, "samples": 0}
    assert result["metrics"]["project_disk_free_min_bytes"] == {
        "value": 1000,
        "samples": 2,
    }
    assert result["metrics"]["game_memory_max_bytes"] == {"value": 3500, "samples": 2}

    groups = result["by_player_count"]
    assert [(group["players"], group["samples"]) for group in groups] == [
        (1, 3),
        (2, 1),
        (3, 1),
    ]
    one, two, three = (group["metrics"] for group in groups)
    assert one["game_tps_min"] == {"value": 0, "samples": 3}
    assert one["game_memory_max_bytes"] == {"value": 2100, "samples": 1}
    assert two["game_memory_max_bytes"] == {"value": None, "samples": 0}
    assert three["game_memory_max_bytes"] == {"value": 3500, "samples": 1}
    assert all(report.DISK not in group["metrics"] for group in groups)


def test_capacity_samples_short_and_overlapping_backup_windows(tmp_path, monkeypatch):
    settings, path = config(tmp_path)
    _write_private(
        settings.private / "tui.json",
        settings.private,
        {"schema": 1, "host": "test", "prometheus_origin": "http://127.0.0.1:9000"},
    )
    monkeypatch.setattr(report.time, "time", lambda: NOW)
    first = HOUR - 24 * 3600
    _write_private(
        settings.private / "hourly-backups/dj2/capture-windows.json",
        settings.private,
        {
            "schema": 1,
            "windows": [
                [first - 10, first],
                [first + 12.25, first + 26.75],
                [first + 40.25, first + 90.5],
                [first + 50, first + 65],
                [HOUR, HOUR + 10],
            ],
        },
    )
    backup_chunks = []

    def sample(_settings, expression, *, start, end, step, **_options):
        if step != report.OPERATION_STEP:
            return []
        backup_chunks.append((start, end))
        short_window = start == first + 26
        since = first + (12.25 if short_window else 40.25)
        assert (
            f'timestamp(omk_game_online{{host="test",job="dj2",service="dj2"}}) >= {since}'
            in expression
        )
        return [
            {
                "metric": {"host": "test", "stat": "players"},
                "values": [[start, "1" if short_window else "0"]],
            },
            {
                "metric": {"host": "test", "stat": "game_tps_min"},
                "values": [[start, "18" if short_window else "20"]],
            },
        ]

    monkeypatch.setattr(report, "query", sample)
    backup = report.run(path, "dj2", "24h")["during_hourly_backup"]
    assert backup["windows"] == 3
    assert backup["step"] == 30
    assert backup_chunks == [(first + 26, first + 26), (first + 60, first + 90)]
    assert backup["coverage"] == {"with_players": 1, "without_players": 1, "unknown": 1}
    assert backup["metrics"]["game_tps_min"] == {"value": 18, "samples": 2}


def test_capacity_reports_each_operation_separately(tmp_path, monkeypatch):
    settings, path = config(tmp_path)
    _write_private(
        settings.private / "tui.json",
        settings.private,
        {"schema": 1, "host": "test", "prometheus_origin": "http://127.0.0.1:9000"},
    )
    monkeypatch.setattr(report.time, "time", lambda: NOW)
    reset_starts = HOUR - 65
    boot_starts = HOUR - 210
    for folder, bounds in (
        ("hourly-backups", [HOUR - 105, HOUR - 90]),
        ("world-reset", [reset_starts, HOUR + 20]),
        ("server-starts", [boot_starts, HOUR - 132]),
    ):
        _write_private(
            settings.private / folder / "dj2/capture-windows.json",
            settings.private,
            {"schema": 1, "windows": [bounds]},
        )

    def sample(_settings, expression, *, start, end, step, **_options):
        if step != 30:
            return []
        assert end < HOUR
        if start < HOUR - 105:
            assert (
                f'timestamp(cpu_usage_idle{{host="test",job="host",cpu="cpu-total"}}) >= {boot_starts}'
                in expression
            )
            return [
                {
                    "metric": {"host": "test", "stat": "host_cpu_p95_percent"},
                    "values": [[start, "67"]],
                },
                {"metric": {"host": "test", "stat": "players"}, "values": [[end, "0"]]},
            ]
        if start < reset_starts:
            return [
                {
                    "metric": {"host": "test", "stat": "players"},
                    "values": [[start, "2"]],
                }
            ]
        assert (
            f'timestamp(omk_game_online{{host="test",job="dj2",service="dj2"}}) >= {reset_starts}'
            in expression
        )
        return [
            {"metric": {"host": "test", "stat": "players"}, "values": [[end, "0"]]},
            {
                "metric": {"host": "test", "stat": "host_cpu_p95_percent"},
                "values": [[start, "86"]],
            },
        ]

    monkeypatch.setattr(report, "query", sample)
    result = report.run(path, "dj2", "24h")
    hourly = result["during_hourly_backup"]
    assert hourly["coverage"] == {"with_players": 1, "without_players": 0, "unknown": 0}
    reset = result["during_world_reset"]
    assert reset["windows"] == 1
    assert reset["coverage"] == {"with_players": 0, "without_players": 1, "unknown": 2}
    assert reset["metrics"]["host_cpu_p95_percent"] == {"value": 86, "samples": 1}
    assert reset["metrics"]["game_tps_min"] == {"value": None, "samples": 0}
    boot = result["during_server_start"]
    assert boot["windows"] == 1
    assert boot["coverage"] == {"with_players": 0, "without_players": 1, "unknown": 2}
    assert boot["metrics"]["host_cpu_p95_percent"] == {"value": 67, "samples": 1}
    assert boot["metrics"]["game_tps_min"] == {"value": None, "samples": 0}

    # Damaged reset history must not hide successful samples from hourly backups.
    _write_private(
        settings.private / "world-reset/dj2/capture-windows.json",
        settings.private,
        {"schema": 1, "windows": [[reset_starts, reset_starts]]},
    )
    result = report.run(path, "dj2", "24h")
    assert result["ok"] and result["during_world_reset"] is None
    assert result["during_hourly_backup"] == hourly
    assert result["during_server_start"] == boot


def test_empty_prometheus_history_has_no_guessed_load(tmp_path):
    settings, path = config(tmp_path)
    payload = b'{"status":"success","data":{"resultType":"matrix","result":[]}}'
    assert report.run(path, "dj2", "24h")["state"] == "disabled"
    with endpoint(payload) as (origin, requests):
        _write_private(
            settings.private / "tui.json",
            settings.private,
            {"schema": 1, "host": "test", "prometheus_origin": origin},
        )
        assert report.run(path, "unknown", "24h")["error"] == "invalid_configuration"
        assert not requests
        result = report.run(path, "dj2", "24h")
    assert requests and all(
        item.startswith("/api/v1/query_range?") for item in requests
    )
    assert result["ok"] and result["state"] == "missing"
    assert result["coverage"]["unknown"] == 1440
    assert result["coverage"]["peak_players"] is None
    assert result["by_player_count"] == []
    assert result["during_hourly_backup"] is None
    assert result["during_world_reset"] is None
    assert result["during_server_start"] is None
    assert all(
        metric == {"value": None, "samples": 0} for metric in result["metrics"].values()
    )


def test_ambiguous_history_is_reported_as_unavailable(tmp_path, monkeypatch):
    settings, path = config(tmp_path)
    _write_private(
        settings.private / "tui.json",
        settings.private,
        {"schema": 1, "host": "test", "prometheus_origin": "http://127.0.0.1:9000"},
    )

    def duplicate(_, _expression, *, start, **_options):
        row = {"metric": {"host": "test", "stat": "players"}, "values": [[start, "3"]]}
        return [row, row]

    monkeypatch.setattr(report, "query", duplicate)
    result = report.run(path, "dj2", "24h")
    assert not result["ok"] and result["state"] == "unavailable"
    assert result["error"] == "history_unavailable"
    assert result["coverage"] is None
