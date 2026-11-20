"""Instant view of the existing private Prometheus; no sampler or new database."""

import json
import math
import re
import time
import urllib.parse
import urllib.request
from typing import Literal

from pydantic import BaseModel, ConfigDict

from omk.owner.admin import _private_path, _read_json

KEYS = ("host_cpu", "host_ram", "host_disk", "game_tps", "game_mspt", "game_players")
SOURCES = {
    "host_cpu": "cpu_usage_idle",
    "host_ram": "mem_used_percent",
    "host_disk": "disk_used_percent",
    "game_tps": "omk_game_tps",
    "game_mspt": "omk_game_tick_mean_ms",
    "game_players": "omk_game_online",
}


class Metric(BaseModel):
    """Describe the observed value and availability of a monitoring metric."""

    model_config = ConfigDict(extra="forbid", strict=True)
    key: Literal[
        "host_cpu", "host_ram", "host_disk", "game_tps", "game_mspt", "game_players"
    ]
    value: float | None
    state: Literal["fresh", "missing", "stale", "invalid"]


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """Keep monitoring HTTP requests at the configured origin."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        """Decline redirects from the configured monitoring endpoint."""
        return None


def project(rows, host, server, now):
    result = []
    for key, source in SOURCES.items():
        matches = []
        for row in rows:
            labels = row["metric"]
            if labels.get("__name__") != source or labels.get("host") != host:
                continue
            if key.startswith("game_") and labels.get("service") != server:
                continue
            if key == "host_cpu" and labels.get("cpu") != "cpu-total":
                continue
            if key == "host_disk" and labels.get("path") != "/storage/project":
                continue
            matches.append(row)
        state, value = "missing", None
        if len(matches) > 1:
            state = "invalid"
        elif matches:
            state = "invalid"
            stamp, raw = matches[0]["value"]
            if type(stamp) in {int, float} and isinstance(raw, str):
                number = float(raw)
                maximum = (
                    100 if key.startswith("host_") else 20 if key == "game_tps" else 1e9
                )
                if (
                    math.isfinite(stamp)
                    and math.isfinite(number)
                    and 0 <= number <= maximum
                ):
                    state = "fresh" if -10 <= now - stamp <= 90 else "stale"
                    if state == "fresh":
                        value = 100 - number if key == "host_cpu" else number
        result.append(Metric(key=key, value=value, state=state).model_dump(mode="json"))
    return result


def load_settings(config):
    path = _private_path(config.private, "tui.json")
    if not path.exists():
        return None
    settings = _read_json(path, config.private)
    if (
        set(settings) != {"schema", "prometheus_origin", "host"}
        or type(settings["schema"]) is not int
        or settings["schema"] != 1
        or not isinstance(settings["host"], str)
        or not re.fullmatch(r"[a-z][a-z0-9_-]{0,47}", settings["host"])
        or not isinstance(settings["prometheus_origin"], str)
        or not re.fullmatch(
            r"http://127\.0\.0\.1:[1-9][0-9]{0,4}", settings["prometheus_origin"]
        )
        or not 1024
        <= urllib.parse.urlsplit(settings["prometheus_origin"]).port
        <= 65535
    ):
        raise ValueError("Invalid private TUI monitoring configuration")
    return settings


def query(settings, expression, *, result_type="vector", **parameters):
    endpoint = "query_range" if result_type == "matrix" else "query"
    url = (
        settings["prometheus_origin"]
        + "/api/v1/"
        + endpoint
        + "?"
        + urllib.parse.urlencode({"query": expression, "timeout": "2s", **parameters})
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    with opener.open(url, timeout=3) as stream:
        raw = stream.read(65537)
    if len(raw) > 65536:
        raise ValueError("Prometheus response exceeds limit")
    value = json.loads(raw)
    if (
        value["status"] != "success"
        or value.get("warnings")
        or value["data"]["resultType"] != result_type
    ):
        raise ValueError("Invalid Prometheus response")
    rows = value["data"]["result"]
    if not isinstance(rows, list) or len(rows) > 128:
        raise ValueError("Prometheus vector exceeds limit")
    return rows


def sample(config, server):
    missing = [
        Metric(key=key, value=None, state="missing").model_dump(mode="json")
        for key in KEYS
    ]
    try:
        settings = load_settings(config)
        if settings is None:
            return "disabled", missing
        selector = (
            '{host="'
            + settings["host"]
            + '",__name__=~"'
            + "|".join(SOURCES.values())
            + '"}'
        )
        rows = query(settings, selector + " and on(job,instance) (up == 1)")
        metrics = project(rows, settings["host"], server, time.time())
        return (
            "available"
            if all(row["state"] == "fresh" for row in metrics)
            else "partial"
        ), metrics
    except Exception:
        return "unavailable", missing
