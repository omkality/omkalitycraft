"""Daily calendar preview only. No sleeping, lifecycle calls or catch-up job."""

import os
import re
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from omk.admin import AdminError


def settings(environment=None):
    env = os.environ if environment is None else environment
    clock = env.get("OMK_NIGHTLY_LOCAL_TIME", "05:00")
    zone = env.get("OMK_NIGHTLY_TIMEZONE", "Europe/Moscow")
    warnings = env.get("OMK_NIGHTLY_WARNINGS_SECONDS", "600,300,60,10")
    if not isinstance(clock, str) or not re.fullmatch(
        r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", clock
    ):
        raise AdminError("Invalid OMK_NIGHTLY_LOCAL_TIME")
    if (
        not isinstance(zone, str)
        or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_+/-]{0,99}", zone)
        or any(part in {"", ".", ".."} for part in zone.split("/"))
    ):
        raise AdminError("Invalid OMK_NIGHTLY_TIMEZONE")
    try:
        ZoneInfo(zone)
    except ZoneInfoNotFoundError:
        raise AdminError(
            "Unknown OMK_NIGHTLY_TIMEZONE or missing timezone data"
        ) from None
    if (
        not isinstance(warnings, str)
        or len(warnings) > 100
        or not re.fullmatch(r"[0-9]{1,4}(?:,[0-9]{1,4}){0,7}", warnings)
    ):
        raise AdminError("Invalid OMK_NIGHTLY_WARNINGS_SECONDS")
    seconds = [int(value) for value in warnings.split(",")]
    if any(not 1 <= value <= 3600 for value in seconds) or seconds != sorted(
        set(seconds), reverse=True
    ):
        raise AdminError("Nightly warnings require unique descending seconds (1-3600)")
    return {"local_time": clock, "timezone": zone, "warnings_seconds": seconds}


def next_window(policy, now=None):
    # Validate caller-supplied policies as strictly as environment settings.
    if (
        not isinstance(policy, dict)
        or set(policy) != {"local_time", "timezone", "warnings_seconds"}
        or not isinstance(policy["warnings_seconds"], list)
        or any(type(value) is not int for value in policy["warnings_seconds"])
    ):
        raise AdminError("Invalid nightly calendar policy")
    checked = settings(
        {
            "OMK_NIGHTLY_LOCAL_TIME": policy["local_time"],
            "OMK_NIGHTLY_TIMEZONE": policy["timezone"],
            "OMK_NIGHTLY_WARNINGS_SECONDS": ",".join(
                map(str, policy["warnings_seconds"])
            ),
        }
    )
    now = datetime.now(UTC) if now is None else now
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise AdminError("Nightly preview requires an aware current time")
    now = now.astimezone(UTC)
    zone = ZoneInfo(checked["timezone"])
    date = now.astimezone(zone).date()
    for offset in range(9):
        naive = datetime.combine(
            date + timedelta(days=offset), time.fromisoformat(checked["local_time"])
        )
        instants = set()
        for fold in (0, 1):
            instant = naive.replace(tzinfo=zone, fold=fold).astimezone(UTC)
            if instant.astimezone(zone).replace(tzinfo=None) == naive:
                instants.add(instant)
        if not instants:
            continue  # A nonexistent local time is skipped, never shifted silently.
        instant = min(instants)  # A repeated local time has exactly one occurrence.
        warning_times = [
            instant - timedelta(seconds=value) for value in checked["warnings_seconds"]
        ]
        if warning_times[0] < now:
            continue  # Never restart immediately after missing the first warning.
        return {
            "local_date": naive.date().isoformat(),
            "restart_utc": instant.isoformat(),
            "restart_local": instant.astimezone(zone).isoformat(),
            "warnings": [
                {"seconds_before": seconds, "at_utc": at.isoformat()}
                for seconds, at in zip(
                    checked["warnings_seconds"], warning_times, strict=True
                )
            ],
            "missed_window": "skip",
            "ambiguous_local_time": "first_occurrence_only",
            "nonexistent_local_time": "skip",
        }
    raise AdminError("No eligible nightly window within calendar horizon")
