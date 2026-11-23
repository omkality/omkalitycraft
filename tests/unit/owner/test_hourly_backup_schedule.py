from datetime import datetime
from unittest.mock import Mock

import pytest

from omk.owner import hourly_backups
from omk.owner.hourly_backup_schedule import HOUR, daily_due, had_players


def moscow(hour, minute=0):
    return datetime.fromisoformat(f"2026-11-23T{hour:02}:{minute:02}:00+03:00")


def event(when, verb, player="Fixture"):
    return (
        f"{when.isoformat()} [2026-11-23 10:00:00.000] [Server thread/INFO] "
        f"[net.minecraft.server.dedicated.DedicatedServer]: {player} {verb} the game"
    )


def test_player_who_leaves_before_the_hour_still_triggers_it():
    events = "\n".join((event(moscow(13, 15), "joined"), event(moscow(13, 40), "left")))
    assert had_players(moscow(14), events, [])
    assert not had_players(moscow(15), events, [])


def test_forge_colors_in_connection_log():
    name = "§eFixture§r§e"
    same_hour = "\n".join(
        event(when, action, name) + "§r"
        for when, action in ((moscow(13, 15), "joined"), (moscow(13, 40), "left"))
    )
    assert had_players(moscow(14), same_hour, [])
    joined_after = event(moscow(14, 1), "joined", name) + "§r"
    assert not had_players(moscow(14), joined_after, ["Fixture"])


@pytest.mark.parametrize("boundary", [16, 17, 18, 19])
def test_session_across_multiple_hours(boundary):
    start, end = moscow(boundary) - HOUR, moscow(boundary)
    events = "\n".join(
        event(when, action)
        for when, action in ((moscow(15, 1), "joined"), (moscow(18, 2), "left"))
        if start <= when <= end
    )
    online = ["Fixture"] if end < moscow(18, 2) else []
    assert had_players(end, events, online)


def test_connection_after_the_boundary_does_not_count_backwards():
    now = moscow(14, 1)
    assert not had_players(moscow(14), event(now, "joined"), ["Fixture"])
    assert had_players(moscow(14), event(now, "left"), [])
    assert not had_players(
        moscow(14), event(now, "joined") + "\n" + event(now, "left"), []
    )


def test_daily_backup_due_even_with_empty_roster_and_recovers_after_delay():
    assert not daily_due(moscow(3, 59), {})
    assert daily_due(moscow(4), {})
    assert daily_due(moscow(11), {"time": "2026-11-22T19:00:00+00:00"})
    assert not daily_due(moscow(4), {"time": "2026-11-22T23:05:00+00:00"})
    send = Mock(side_effect=AssertionError("Daily copy does not depend on the roster"))
    assert hourly_backups._scheduled_reason(moscow(4), {}, {}, send) == "daily"
    assert (
        hourly_backups._scheduled_reason(
            moscow(4), {"slot": moscow(4).isoformat()}, {}, send
        )
        == "duplicate"
    )
