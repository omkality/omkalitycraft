from datetime import UTC, datetime, timedelta

import pytest

from omk.admin import AdminError
from omk.nightly_policy import next_window, settings


def test_default_calendar_and_warning_times():
    policy = settings({})
    window = next_window(policy, datetime(2026, 11, 12, 0, tzinfo=UTC))
    assert window["restart_utc"] == "2026-11-12T02:00:00+00:00"
    assert window["restart_local"] == "2026-11-12T05:00:00+03:00"
    assert window["warnings"][0] == {
        "seconds_before": 600,
        "at_utc": "2026-11-12T01:50:00+00:00",
    }
    instant = datetime.fromisoformat(window["restart_utc"])
    assert all(
        datetime.fromisoformat(row["at_utc"])
        == instant - timedelta(seconds=row["seconds_before"])
        for row in window["warnings"]
    )


@pytest.mark.parametrize(
    "now,day",
    [
        ("2026-11-12T01:50:00+00:00", "2026-11-12"),
        ("2026-11-12T01:50:00.000001+00:00", "2026-11-13"),
        ("2026-11-12T02:00:00+00:00", "2026-11-13"),
    ],
)
def test_missed_first_warning_never_causes_immediate_catchup(now, day):
    assert next_window(settings({}), datetime.fromisoformat(now))["local_date"] == day


def test_midnight_warning_can_be_on_previous_local_day():
    policy = settings({"OMK_NIGHTLY_LOCAL_TIME": "00:05"})
    window = next_window(policy, datetime.fromisoformat("2026-11-12T20:00:00+00:00"))
    assert window["local_date"] == "2026-11-13"
    assert window["warnings"][0]["at_utc"] == "2026-11-12T20:55:00+00:00"


def test_dst_spring_nonexistent_time_skips_day():
    policy = settings(
        {"OMK_NIGHTLY_TIMEZONE": "Europe/Warsaw", "OMK_NIGHTLY_LOCAL_TIME": "02:30"}
    )
    window = next_window(policy, datetime(2026, 3, 29, tzinfo=UTC))
    assert window["restart_local"] == "2026-03-30T02:30:00+02:00"
    assert window["nonexistent_local_time"] == "skip"


def test_dst_autumn_chooses_only_first_occurrence():
    policy = settings(
        {"OMK_NIGHTLY_TIMEZONE": "Europe/Warsaw", "OMK_NIGHTLY_LOCAL_TIME": "02:30"}
    )
    first = next_window(policy, datetime(2026, 10, 24, 23, tzinfo=UTC))
    assert first["restart_utc"] == "2026-10-25T00:30:00+00:00"
    # Second 02:30 is not a second restart, even when its warning is still ahead.
    second = next_window(policy, datetime(2026, 10, 25, 1, tzinfo=UTC))
    assert second["local_date"] == "2026-10-26"


@pytest.mark.parametrize(
    "key,value",
    [
        ("LOCAL_TIME", "5:00"),
        ("LOCAL_TIME", "24:00"),
        ("LOCAL_TIME", "00:60"),
        ("LOCAL_TIME", "12:00\n"),
        ("LOCAL_TIME", None),
        ("TIMEZONE", "../../secret"),
        ("TIMEZONE", "/etc/localtime"),
        ("TIMEZONE", "Europe//Moscow"),
        ("TIMEZONE", "DoesNotExist"),
        ("WARNINGS_SECONDS", "0"),
        ("WARNINGS_SECONDS", "3601"),
        ("WARNINGS_SECONDS", "600,600"),
        ("WARNINGS_SECONDS", "10,60"),
        ("WARNINGS_SECONDS", "600, 60"),
        ("WARNINGS_SECONDS", ""),
        ("WARNINGS_SECONDS", "600,300,200,100,60,30,20,10,1"),
        ("WARNINGS_SECONDS", "６００"),
        ("WARNINGS_SECONDS", None),
    ],
)
def test_bad_overrides_fail_without_echoing_value(key, value):
    with pytest.raises(AdminError) as error:
        settings({"OMK_NIGHTLY_" + key: value})
    if isinstance(value, str) and len(value) > 8:
        assert value not in str(error.value)


@pytest.mark.parametrize(
    "policy",
    [None, {}, {"local_time": "05:00", "timezone": "UTC", "warnings_seconds": [True]}],
)
def test_invalid_direct_policy_rejected(policy):
    with pytest.raises(AdminError):
        next_window(policy)


def test_naive_clock_rejected_and_utc_override_used():
    with pytest.raises(AdminError, match="aware"):
        next_window(settings({}), datetime(2026, 11, 12))
    policy = settings(
        {
            "OMK_NIGHTLY_TIMEZONE": "UTC",
            "OMK_NIGHTLY_LOCAL_TIME": "23:59",
            "OMK_NIGHTLY_WARNINGS_SECONDS": "1",
        }
    )
    assert (
        next_window(policy, datetime(2026, 11, 12, tzinfo=UTC))["restart_local"]
        == "2026-11-12T23:59:00+00:00"
    )
