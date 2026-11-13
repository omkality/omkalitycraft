import hashlib

import pytest

from omk.resource_store import ResourceStore, hours_with_players_report
from tests.unit.test_resource_history import sample


def metrics(online=None, running=1, cpu=10):
    result = {"host.cpu.busy_pct": cpu}
    if running is not None:
        result["game.dj2.running"] = running
    if online is not None:
        result["game.dj2.online"] = online
    return result


def test_whole_hour_not_active_only_mean_or_exact_window(tmp_path):
    with ResourceStore(tmp_path / "h", reserve_mib=16) as store:
        store.append(sample(100, 1, metrics(0, cpu=10)))
        store.append(sample(130, 2, metrics(2, cpu=90)))
        store.append(
            sample(160, 3, metrics(running=None, cpu=50), issues=["game.dj2:stale"])
        )
    report = hours_with_players_report(store.database, game="dj2", since=115, until=125)
    assert report["resolution"] == "whole_hour"
    assert report["selection"] == "whole_hour_groups_with_observed_players"
    assert report["requested_since"] == 115 and report["requested_until"] == 125
    row = report["hours"][0]
    assert row["metrics"]["host.cpu.busy_pct"]["mean"] == 50
    assert row["metrics"]["host.cpu.busy_pct"]["max"] == 90
    assert row["player_observation"] == {
        "online_readings": 2,
        "missing_online_readings": 1,
        "peak_online": 2,
    }


def test_idle_stopped_and_missing_are_distinct(tmp_path):
    with ResourceStore(tmp_path / "h", reserve_mib=16) as store:
        for i, value in enumerate(
            (metrics(1), metrics(0), metrics(running=0), metrics(running=None))
        ):
            store.append(sample(1000 + i * 3600, i + 1, value))
    report = hours_with_players_report(store.database, game="dj2", since=1, until=15000)
    assert report["selection_counts"] == {
        "players_observed": 1,
        "no_players_observed": 1,
        "stopped_only": 1,
        "unknown": 1,
    }
    assert report["scanned_hour_groups"] == 4 and len(report["hours"]) == 1


def test_partial_zero_online_is_unknown(tmp_path):
    with ResourceStore(tmp_path / "h", reserve_mib=16) as store:
        store.append(sample(1000, 1, metrics(0)))
        store.append(
            sample(1030, 2, metrics(running=None), issues=["game.dj2:unavailable"])
        )
    report = hours_with_players_report(store.database, game="dj2", since=1, until=3600)
    assert report["hours"] == [] and report["selection_counts"]["unknown"] == 1
    assert report["selection_counts"]["no_players_observed"] == 0


def test_hourly_presence_survives_detail_retention_and_read_is_non_mutating(tmp_path):
    with ResourceStore(
        tmp_path / "h", detail_days=7, hourly_days=180, reserve_mib=16
    ) as store:
        store.append(sample(1000, 1, metrics(3)))
        store.append(sample(1000 + 179 * 86400 + 500, 2, metrics(0)))
        assert (
            store.db.execute("SELECT count(*) FROM samples WHERE at=1000").fetchone()[0]
            == 0
        )
    before = hashlib.sha256(store.database.read_bytes()).hexdigest()
    report = hours_with_players_report(store.database, game="dj2", since=1, until=3600)
    assert report["hours"][0]["player_observation"]["peak_online"] == 3
    assert hashlib.sha256(store.database.read_bytes()).hexdigest() == before
    assert not (store.root / "history.sqlite3-journal").exists()


def test_host_config_and_game_labels_are_not_combined(tmp_path):
    with ResourceStore(tmp_path / "h", reserve_mib=16) as store:
        store.append(sample(1000, 1, metrics(2)))
        store.append(sample(1030, 2, metrics(0), config_sha256="c" * 64))
        store.append(sample(1060, 3, metrics(4), host="another"))
    report = hours_with_players_report(store.database, game="dj2", since=1, until=3600)
    assert report["scanned_hour_groups"] == 3 and len(report["hours"]) == 2
    assert {row["host"] for row in report["hours"]} == {"fixture", "another"}
    missing = hours_with_players_report(
        store.database, game="gtnh", since=1, until=3600
    )
    assert missing["hours"] == [] and missing["selection_counts"]["unknown"] == 3


def test_scan_limit_is_applied_before_selection(tmp_path):
    with ResourceStore(tmp_path / "h", reserve_mib=16) as store:
        store.append(sample(1000, 1, metrics(0)))
        store.append(sample(4600, 2, metrics(5)))
    report = hours_with_players_report(
        store.database, game="dj2", since=1, until=7200, max_rows=1
    )
    assert report["hours"] == [] and report["truncated"]
    assert report["scanned_hour_groups"] == 1


@pytest.mark.parametrize("game", [None, True, "", "DJ2", "../dj2", "a" * 49])
def test_invalid_game_is_rejected_before_database_open(tmp_path, game):
    with pytest.raises(ValueError, match="game label"):
        hours_with_players_report(tmp_path / "missing.db", game=game, since=1, until=2)
    assert not (tmp_path / "missing.db").exists()


def test_fractional_online_cannot_claim_player_activity(tmp_path):
    with ResourceStore(tmp_path / "h", reserve_mib=16) as store:
        store.append(sample(1000, 1, metrics(0.5)))
        store.append(sample(4600, 2, metrics(0.5, running=0)))
    report = hours_with_players_report(store.database, game="dj2", since=1, until=7200)
    assert report["hours"] == [] and report["selection_counts"]["unknown"] == 2
