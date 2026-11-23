"""Find played clock hours from the Forge connection log and current roster."""

import re
from datetime import datetime, timedelta, timezone

HOUR = timedelta(hours=1)
MOSCOW = timezone(timedelta(hours=3))
DAILY_HOUR = 4
EVENT = re.compile(
    r"(?P<time>\S+) \[[^\]]+\] \[Server thread/INFO\] "
    r"\[net\.minecraft\.server\.dedicated\.DedicatedServer\]: "
    r"(?P<player>[A-Za-z0-9_]{1,16}) (?P<event>joined|left) the game"
)


def hour_end(when):
    """Return the end of the most recent complete clock hour."""
    return when.replace(minute=0, second=0, microsecond=0)


def daily_due(when, latest):
    """Keep at least one successful copy each Moscow calendar day."""
    local = when.astimezone(MOSCOW)
    last_time = latest.get("time")
    last_day = (
        datetime.fromisoformat(last_time).astimezone(MOSCOW).date()
        if last_time
        else None
    )
    return local.hour >= DAILY_HOUR and last_day != local.date()


def had_players(boundary, logs, online):
    """Count connections overlapping [boundary - 1 hour, boundary)."""
    first = boundary - HOUR
    recent_joins = set()
    for line in logs.splitlines():
        event = EVENT.fullmatch(line)
        if not event:
            continue
        when = datetime.fromisoformat(event["time"])
        if first <= when < boundary:
            return True
        if when >= boundary:
            player = event["player"].casefold()
            if event["event"] == "joined":
                recent_joins.add(player)
            elif player not in recent_joins:
                return True  # An already connected player left just after the hour.
    return any(name.casefold() not in recent_joins for name in online)
