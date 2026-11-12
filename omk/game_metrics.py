"""Read bounded Core snapshots from a dedicated readonly metrics volume."""

import hashlib
import json
import math
import re
from pathlib import Path

from omk.resource_metrics import read

FIELDS = {
    "schema",
    "profile",
    "core_version",
    "boot",
    "sequence",
    "sampled_at_ms",
    "uptime_ms",
    "running",
    "online",
    "ticks_total",
    "observed_tps",
    "interval_ms",
    "tick",
    "heap_used_bytes",
    "heap_committed_bytes",
    "heap_max_bytes",
    "gc_collections_total",
    "gc_millis_total",
    "dimension_count",
    "dimensions_truncated",
    "dimensions",
}


def number(value, maximum=10**18, *, nullable=False, integer=False):
    if nullable and value is None:
        return
    types = (int,) if integer else (int, float)
    if (
        type(value) not in types
        or not math.isfinite(value)
        or not 0 <= value <= maximum
    ):
        raise ValueError("Invalid game metric number")


def tick_window(value):
    if not isinstance(value, dict) or set(value) != {
        "samples",
        "mean_ms",
        "p95_ms",
        "max_ms",
    }:
        raise ValueError("Invalid game tick window")
    number(value["samples"], 100, integer=True)
    for key in ("mean_ms", "p95_ms", "max_ms"):
        if value["samples"] == 0:
            if value[key] is not None:
                raise ValueError("Empty tick window has a fabricated value")
        else:
            number(value[key], 10**12)
    if value["samples"] and max(value["mean_ms"], value["p95_ms"]) > value["max_ms"]:
        raise ValueError("Invalid game tick maximum")


def validate_snapshot(value, entry):
    if not isinstance(value, dict) or set(value) != FIELDS:
        raise ValueError("Invalid game metric snapshot")
    if (
        type(value["schema"]) is not int
        or value["schema"] != 1
        or value["profile"] != entry["profile"]
        or value["core_version"] != entry["core_version"]
    ):
        raise ValueError("Wrong game metric producer")
    if not isinstance(value["boot"], str) or not re.fullmatch(
        r"[a-f0-9]{32}", value["boot"]
    ):
        raise ValueError("Invalid game metric boot")
    for key in (
        "sequence",
        "sampled_at_ms",
        "uptime_ms",
        "ticks_total",
        "heap_used_bytes",
        "heap_committed_bytes",
    ):
        number(value[key], integer=True)
    if value["sequence"] < 1:
        raise ValueError("Invalid game metric sequence")
    number(value["online"], 10000, integer=True)
    number(value["dimension_count"], 4096, integer=True)
    for key in ("heap_max_bytes", "gc_collections_total", "gc_millis_total"):
        number(value[key], nullable=True, integer=True)
    number(value["observed_tps"], 20, nullable=True)
    number(value["interval_ms"], nullable=True)
    if (value["interval_ms"] is None) != (value["observed_tps"] is None) or value[
        "interval_ms"
    ] == 0:
        raise ValueError("Invalid game measurement interval")
    if value["heap_used_bytes"] > value["heap_committed_bytes"] or (
        value["heap_max_bytes"] is not None
        and value["heap_committed_bytes"] > value["heap_max_bytes"]
    ):
        raise ValueError("Invalid JVM heap measurement")
    if (
        type(value["running"]) is not bool
        or type(value["dimensions_truncated"]) is not bool
    ):
        raise ValueError("Invalid game lifecycle flags")
    tick_window(value["tick"])
    dimensions = value["dimensions"]
    if (
        not isinstance(dimensions, dict)
        or len(dimensions) > 64
        or value["dimension_count"] < len(dimensions)
        or value["dimensions_truncated"] != (value["dimension_count"] > len(dimensions))
    ):
        raise ValueError("Invalid game dimension inventory")
    for key, window in dimensions.items():
        if (
            not isinstance(key, str)
            or not re.fullmatch(r"-?(0|[1-9][0-9]{0,9})", key)
            or not -(2**31) <= int(key) < 2**31
            or key == "-0"
        ):
            raise ValueError("Invalid game dimension identifier")
        tick_window(window)
    return value


class GameMetrics:
    def __init__(self, entries, *, root=Path("/gamefeeds")):
        self.entries, self.root = entries, root
        self.previous = {}

    def sample(self, now_ms):
        metrics, metadata, issues = {}, {}, []
        for label, entry in self.entries.items():
            prefix = "game." + label
            try:
                raw = read(self.root / entry["mount"] / "current.json")
                if len(raw) > 65536:
                    raise ValueError("Game metric snapshot exceeds bound")
                value = validate_snapshot(json.loads(raw), entry)
                age = now_ms - value["sampled_at_ms"]
                if age < -5000:
                    raise ValueError("Game metric timestamp is in the future")
                if age > entry["max_age_seconds"] * 1000:
                    self.previous.pop(label, None)
                    issues.append(prefix + ":stale")
                    continue
                before = self.previous.get(label)
                digest = hashlib.sha256(raw.encode("ascii")).hexdigest()
                if (
                    before
                    and before[0]["boot"] == value["boot"]
                    and (
                        value["sequence"] < before[0]["sequence"]
                        or (
                            value["sequence"] == before[0]["sequence"]
                            and digest != before[1]
                        )
                        or value["uptime_ms"] < before[0]["uptime_ms"]
                    )
                ):
                    raise ValueError("Game metric sequence or uptime regressed")
                values = self._metrics(prefix, value, before)
                self.previous[label] = (value, digest)
                metrics.update(values)
                metrics[prefix + ".age_seconds"] = max(0, age / 1000)
                metadata[label] = {
                    k: value[k]
                    for k in (
                        "profile",
                        "core_version",
                        "boot",
                        "sequence",
                        "sampled_at_ms",
                        "running",
                        "dimensions_truncated",
                    )
                }
            except (
                OSError,
                ValueError,
                TypeError,
                KeyError,
                OverflowError,
                RecursionError,
            ):
                self.previous.pop(label, None)
                issues.append(prefix + ":unavailable")
        return {"metrics": metrics, "games": metadata, "issues": issues}

    @staticmethod
    def _metrics(prefix, value, before):
        result = {prefix + ".running": int(value["running"])}
        if not value["running"]:
            return result
        result[prefix + ".dimensions_truncated"] = int(value["dimensions_truncated"])
        for key in (
            "online",
            "uptime_ms",
            "ticks_total",
            "observed_tps",
            "interval_ms",
            "heap_used_bytes",
            "heap_committed_bytes",
            "heap_max_bytes",
            "gc_collections_total",
            "gc_millis_total",
            "dimension_count",
        ):
            if value[key] is not None:
                result[prefix + "." + key] = value[key]
        for label, window in (
            ("tick", value["tick"]),
            *(("dimension." + k, v) for k, v in value["dimensions"].items()),
        ):
            for key, reading in window.items():
                if reading is not None:
                    result[prefix + "." + label + "." + key] = reading
        if before:
            old = before[0]
            elapsed = (value["uptime_ms"] - old["uptime_ms"]) / 1000
            if (
                old["running"]
                and old["boot"] == value["boot"]
                and value["sequence"] > old["sequence"]
                and elapsed > 0
            ):
                for key in ("gc_collections_total", "gc_millis_total"):
                    if (
                        value[key] is not None
                        and old[key] is not None
                        and value[key] >= old[key]
                    ):
                        result[
                            prefix + "." + key.removesuffix("_total") + "_per_second"
                        ] = (value[key] - old[key]) / elapsed
        return result
