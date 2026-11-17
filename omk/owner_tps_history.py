"""Bounded TPS history from existing Prometheus; missing points remain gaps."""

import math
import time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from omk.admin import load_operator_config
from omk.owner_metrics import load_settings, query
from omk.owner_result import ServerId

STEP = 5
WINDOWS = {"5m": (300, 5), "15m": (900, 15), "1h": (3600, 60), "3h": (10800, 180)}


class Point(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    timestamp: int = Field(ge=0)
    tps: float | None = Field(ge=0, le=20, allow_inf_nan=False)


class TpsHistory(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: Literal[1] = 1
    action: Literal["owner.tps-history"] = "owner.tps-history"
    server_id: ServerId
    ok: bool
    state: Literal["available", "partial", "missing", "disabled", "unavailable"]
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    step: Literal[5, 15, 60, 180] = STEP
    points: list[Point] = Field(max_length=61)
    error: Literal["invalid_configuration", "history_unavailable"] | None = None


def project(rows, settings, server, start, end, step=STEP):
    values = dict.fromkeys(range(start, end + 1, step))
    if len(rows) > 1:
        raise ValueError("Ambiguous TPS history")
    if rows:
        row = rows[0]
        if (
            row["metric"].get("host") != settings["host"]
            or row["metric"].get("service") != server
        ):
            raise ValueError("TPS history binding differs")
        if not isinstance(row["values"], list) or len(row["values"]) > 61:
            raise ValueError("TPS history exceeds limit")
        seen = set()
        previous = -1
        for timestamp, raw in row["values"]:
            if (
                type(timestamp) not in {int, float}
                or not math.isfinite(timestamp)
                or timestamp != int(timestamp)
            ):
                raise ValueError("Invalid history timestamp")
            stamp = int(timestamp)
            if (
                stamp not in values
                or stamp in seen
                or stamp <= previous
                or not isinstance(raw, str)
            ):
                raise ValueError("Invalid history sample order or grid")
            seen.add(stamp)
            previous = stamp
            number = float(raw)
            if math.isfinite(number) and 0 <= number <= 20:
                values[stamp] = number
    return [Point(timestamp=stamp, tps=number) for stamp, number in values.items()]


def run(path, server, window="5m"):
    duration, step = WINDOWS[window]
    end = int(time.time()) // STEP * STEP
    start = end - duration
    base = {"server_id": server, "start": start, "end": end, "step": step}
    try:
        config = load_operator_config(path)
        if server not in config.servers:
            raise ValueError("Server is not allowlisted")
        settings = load_settings(config)
    except Exception:
        return TpsHistory(
            **base,
            ok=False,
            state="unavailable",
            points=[],
            error="invalid_configuration",
        ).model_dump(mode="json")
    if settings is None:
        return TpsHistory(
            **base,
            ok=True,
            state="disabled",
            points=project([], {}, server, start, end, step),
        ).model_dump(mode="json")
    try:
        selector = (
            'omk_game_tps{host="' + settings["host"] + '",service="' + server + '"}'
        )
        # Preserve short drops between the coarse points of a longer window.
        series = selector if step == 5 else f"min_over_time({selector}[{step}s])"
        expression = (
            series
            + " and (time() - timestamp("
            + selector
            + ") <= 90) and on(job,instance) (up == 1)"
        )
        rows = query(
            settings, expression, result_type="matrix", start=start, end=end, step=step
        )
        points = project(rows, settings, server, start, end, step)
        count = sum(point.tps is not None for point in points)
        state = "available" if count == 61 else "partial" if count else "missing"
        return TpsHistory(**base, ok=True, state=state, points=points).model_dump(
            mode="json"
        )
    except Exception:
        return TpsHistory(
            **base,
            ok=False,
            state="unavailable",
            points=[],
            error="history_unavailable",
        ).model_dump(mode="json")
