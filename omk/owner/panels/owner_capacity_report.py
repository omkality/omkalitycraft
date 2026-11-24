"""Summarize existing Prometheus history over completed hours."""

import math
import time
from pathlib import Path
from statistics import quantiles

from omk.owner.admin import AdminError, load_operator_config
from omk.owner.panels.owner_metrics import load_settings, query

WINDOWS = {"24h": (24, 60), "7d": (168, 300), "14d": (336, 300)}
BATCH_POINTS = 96
DISK = "project_disk_free_min_bytes"


def _observed(selector, job, maximum):
    # Collapse old and new release labels across the report, but discard
    # a sample if two sources claim the same service at the same time.
    up = f'up{{job="{job}"}}'
    fresh = (
        f"(({selector} >= 0) <= {maximum}) "
        f"and (time() - timestamp({selector}) <= 90) "
        f"and on(job,instance) (({up} == 1) and (time() - timestamp({up}) <= 90))"
    )
    return f"(sum by(host) ({fresh}) and (count by(host) ({fresh}) == 1))"


def _selectors(host, server):
    def source(metric, maximum, job="host", extra=""):
        selector = f'{metric}{{host="{host}",job="{job}"{extra}}}'
        return _observed(selector, job, maximum)

    service = f',service="{server}"'
    idle_cpu = source("cpu_usage_idle", 100, extra=',cpu="cpu-total"')
    return {
        "players": source("omk_game_online", 1_000_000, server, service),
        "host_cpu_p95_percent": f"(100 - {idle_cpu})",
        "host_cpu_steal_p95_percent": source(
            "cpu_usage_steal", 100, extra=',cpu="cpu-total"'
        ),
        "host_ram_available_min_bytes": source("mem_available", 2**53),
        DISK: source("disk_free", 2**53, extra=',path="/storage/project"'),
        "game_cpu_p95_vcpus": source("omk_service_cpu_vcpus", 10_000, extra=service),
        "game_memory_max_bytes": source(
            "omk_service_memory_bytes", 2**53, extra=service
        ),
        "game_tps_min": source("omk_game_tps", 20, server, service),
        "game_tick_mean_p95_ms": source("omk_game_tick_mean_ms", 1e9, server, service),
    }


def _read_batch(series, rows, host, first, last, step):
    seen = set()
    for row in rows:
        key = row["metric"]["stat"]
        values = row["values"]
        if (
            row["metric"].get("host") != host
            or key not in series
            or key in seen
            or not isinstance(values, list)
            or len(values) > (last - first) // step + 1
        ):
            raise ValueError("Invalid capacity series")
        seen.add(key)
        previous = first - step
        for stamp, raw in values:
            if (
                type(stamp) not in {int, float}
                or not first <= stamp <= last
                or (stamp - first) % step
                or stamp <= previous
                or not isinstance(raw, str)
            ):
                raise ValueError("Invalid capacity timestamp")
            number = float(raw)
            if (
                not math.isfinite(number)
                or number < 0
                or (key == "players" and not number.is_integer())
            ):
                raise ValueError("Invalid capacity value")
            series[key][int(stamp)] = number
            previous = stamp


def _read_series(settings, server, start, end, step):
    selectors = _selectors(settings["host"], server)
    query_text = " or ".join(
        f'label_replace({selector}, "stat", "{key}", "host", ".+")'
        for key, selector in selectors.items()
    )
    series = {key: {} for key in selectors}
    # Keep long reports within both the Prometheus sample budget and the
    # owner HTTP client's response limit.
    for first in range(start, end, BATCH_POINTS * step):
        last = min(first + (BATCH_POINTS - 1) * step, end - step)
        rows = query(
            settings, query_text, result_type="matrix", start=first, end=last, step=step
        )
        _read_batch(series, rows, settings["host"], first, last, step)
    return series


def _p95(values):
    return quantiles(values, n=100, method="inclusive")[94]


def _summarize(series):
    online = series["players"]
    active = {stamp for stamp, count in online.items() if count > 0}
    reductions = {
        "host_cpu_p95_percent": _p95,
        "host_cpu_steal_p95_percent": _p95,
        "host_ram_available_min_bytes": min,
        DISK: min,
        "game_cpu_p95_vcpus": _p95,
        "game_memory_max_bytes": max,
        "game_tps_min": min,
        "game_tick_mean_p95_ms": _p95,
    }
    metrics = {}
    for key, reduce in reductions.items():
        values = [
            value
            for stamp, value in series[key].items()
            if key == DISK or stamp in active
        ]
        metrics[key] = {
            "value": reduce(values) if values else None,
            "samples": len(values),
        }
    return (
        len(active),
        len(online),
        int(max(online.values())) if online else None,
        metrics,
    )


def run(path: Path, server: str, window: str) -> dict:
    """Read a capacity summary using only the owner's configured Prometheus."""
    hours, step = WINDOWS[window]
    duration = hours * 3600
    end = int(time.time()) // 3600 * 3600
    expected = duration // step
    result = {
        "schema_version": 1,
        "action": "owner.capacity-report",
        "server_id": server,
        "ok": True,
        "state": "disabled",
        "start": end - duration,
        "end_exclusive": end,
        "step": step,
        "coverage": None,
        "metrics": {},
    }
    try:
        config = load_operator_config(path)
        if server not in config.servers:
            raise ValueError("Server is not allowlisted")
        settings = load_settings(config)
    except AdminError, OSError, ValueError, TypeError, KeyError:
        return {
            **result,
            "ok": False,
            "state": "unavailable",
            "error": "invalid_configuration",
        }
    if settings is None:
        return result

    try:
        series = _read_series(settings, server, end - duration, end, step)
        active, known, peak, metrics = _summarize(series)
    except OSError, ValueError, TypeError, KeyError:
        return {
            **result,
            "ok": False,
            "state": "unavailable",
            "error": "history_unavailable",
        }

    state = "missing"
    if known:
        state = "available" if known == expected else "partial"
    return {
        **result,
        "state": state,
        "coverage": {
            "expected": expected,
            "with_players": active,
            "without_players": known - active,
            "unknown": expected - known,
            "peak_players": peak,
        },
        "metrics": metrics,
    }
