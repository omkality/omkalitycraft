import copy
import json

import pytest

from omk.game_metrics import GameMetrics, validate_snapshot
from omk.resource_metrics import validate_config
from omk.resource_store import validate_sample


def entry():
    return {
        "mount": "dj2",
        "profile": "dj2-test",
        "core_version": "0.3.7",
        "max_age_seconds": 30,
    }


def snapshot(**changes):
    ring = {"samples": 100, "mean_ms": 12.5, "p95_ms": 20, "max_ms": 40}
    return {
        "schema": 1,
        "profile": "dj2-test",
        "core_version": "0.3.7",
        "boot": "a" * 32,
        "sequence": 1,
        "sampled_at_ms": 100000,
        "uptime_ms": 300000,
        "running": True,
        "online": 2,
        "ticks_total": 6000,
        "observed_tps": None,
        "interval_ms": None,
        "tick": ring,
        "heap_used_bytes": 100,
        "heap_committed_bytes": 200,
        "heap_max_bytes": 300,
        "gc_collections_total": 2,
        "gc_millis_total": 50,
        "dimension_count": 2,
        "dimensions_truncated": False,
        "dimensions": {"0": ring, "-18000": ring},
        **changes,
    }


@pytest.fixture
def feed(tmp_path):
    path = tmp_path / "dj2"
    path.mkdir()

    def write(value):
        (path / "current.json").write_text(json.dumps(value), encoding="ascii")

    return GameMetrics({"dj2": entry()}, root=tmp_path), write


def test_real_shape_gauges_negative_dimension_and_no_fabricated_first_tps(feed):
    reader, write = feed
    write(snapshot())
    result = reader.sample(100000)
    assert not result["issues"]
    assert result["metrics"]["game.dj2.online"] == 2
    assert result["metrics"]["game.dj2.dimension.-18000.p95_ms"] == 20
    assert "game.dj2.observed_tps" not in result["metrics"]
    assert "game.dj2.gc_millis_per_second" not in result["metrics"]
    assert result["games"]["dj2"]["boot"] == "a" * 32


def test_gc_rates_use_producer_uptime_and_repeated_file_not_double_count(feed):
    reader, write = feed
    write(snapshot())
    reader.sample(100000)
    write(
        snapshot(
            sequence=2,
            sampled_at_ms=110000,
            uptime_ms=310000,
            gc_millis_total=100,
            gc_collections_total=4,
            observed_tps=15,
            interval_ms=10000,
        )
    )
    result = reader.sample(110500)
    assert result["metrics"]["game.dj2.gc_millis_per_second"] == 5
    assert result["metrics"]["game.dj2.gc_collections_per_second"] == 0.2
    assert result["metrics"]["game.dj2.observed_tps"] == 15
    assert "game.dj2.gc_millis_per_second" not in reader.sample(120000)["metrics"]


def test_stale_missing_wrong_profile_and_stop_are_distinct(feed):
    reader, write = feed
    assert reader.sample(100000)["issues"] == ["game.dj2:unavailable"]
    write(snapshot())
    assert reader.sample(130001)["issues"] == ["game.dj2:stale"]
    assert reader.sample(130001)["metrics"] == {}
    write(snapshot(profile="other"))
    assert reader.sample(100000)["issues"] == ["game.dj2:unavailable"]
    write(snapshot(running=False))
    result = reader.sample(100000)
    assert result["metrics"] == {"game.dj2.running": 0, "game.dj2.age_seconds": 0}
    assert not result["issues"]


def test_restart_and_stale_gap_never_bridge_gc_rates(feed):
    reader, write = feed
    write(snapshot())
    reader.sample(100000)
    assert reader.sample(130001)["issues"]
    write(
        snapshot(
            sequence=2, sampled_at_ms=140000, uptime_ms=340000, gc_millis_total=200
        )
    )
    assert "game.dj2.gc_millis_per_second" not in reader.sample(140000)["metrics"]
    write(snapshot(boot="b" * 32, sampled_at_ms=150000, gc_millis_total=20))
    assert "game.dj2.gc_millis_per_second" not in reader.sample(150000)["metrics"]


@pytest.mark.parametrize(
    "changes",
    [
        {"sequence": 0},
        {"sequence": True},
        {"online": -1},
        {"online": True},
        {"online": 10001},
        {"observed_tps": 21, "interval_ms": 1000},
        {"observed_tps": float("nan"), "interval_ms": 1000},
        {"heap_used_bytes": 201},
        {"heap_max_bytes": 199},
        {"gc_millis_total": -1},
        {"profile": "wrong"},
        {"core_version": "9.9.9"},
        {"dimensions_truncated": True},
        {"dimensions": {"../x": {}}},
        {"unexpected": "secret"},
    ],
)
def test_invalid_snapshot_does_not_echo_input(changes):
    with pytest.raises(ValueError) as error:
        validate_snapshot(snapshot(**changes), entry())
    assert "secret" not in str(error.value)


@pytest.mark.parametrize(
    "changes",
    [
        {"sequence": 1, "online": 3},
        {"sequence": 2, "uptime_ms": 1},
        {"sequence": 1, "sampled_at_ms": 120000},
    ],
)
def test_same_boot_regression_or_mutated_sequence_is_unavailable(feed, changes):
    reader, write = feed
    write(snapshot())
    reader.sample(100000)
    write(snapshot(**changes))
    assert reader.sample(120000)["issues"] == ["game.dj2:unavailable"]


def test_unknown_gc_and_empty_tick_window_remain_unknown(feed):
    reader, write = feed
    empty = {"samples": 0, "mean_ms": None, "p95_ms": None, "max_ms": None}
    write(
        snapshot(
            gc_millis_total=None,
            gc_collections_total=None,
            heap_max_bytes=None,
            tick=empty,
        )
    )
    result = reader.sample(100000)
    assert not result["issues"]
    assert result["metrics"]["game.dj2.tick.samples"] == 0
    assert "game.dj2.tick.mean_ms" not in result["metrics"]
    assert "game.dj2.gc_millis_total" not in result["metrics"]


def test_future_and_oversized_file_not_accepted(feed):
    reader, write = feed
    write(snapshot(sampled_at_ms=106000))
    assert reader.sample(100000)["issues"]
    write(snapshot(padding="x" * 65536))
    assert reader.sample(100000)["issues"]


def test_optional_config_preserves_existing_schema():
    value = {
        "schema": 1,
        "host": "test",
        "disks": [],
        "interfaces": [],
        "filesystems": {},
        "services": {},
    }
    assert validate_config(copy.deepcopy(value)) == value
    value["games"] = {"dj2": entry()}
    assert validate_config(value) == value
    for key, bad in (
        ("mount", "../secret"),
        ("max_age_seconds", True),
        ("max_age_seconds", 0),
        ("profile", "secret\n"),
    ):
        wrong = copy.deepcopy(value)
        wrong["games"]["dj2"][key] = bad
        with pytest.raises(ValueError):
            validate_config(wrong)


def test_snapshot_metadata_can_be_saved_without_raw_payload(feed):
    from tests.unit.test_resource_history import sample  # noqa: PLC0415

    reader, write = feed
    write(snapshot())
    game = reader.sample(100000)
    data = sample(metrics=game["metrics"], games=game["games"])
    assert json.loads(validate_sample(data))["games"] == game["games"]
    data["games"]["dj2"]["secret"] = "not-allowed"
    with pytest.raises(ValueError):
        validate_sample(data)
