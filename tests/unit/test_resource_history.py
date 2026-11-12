import copy
import json
import os
import sys
from collections import namedtuple
from pathlib import Path

import pytest

from omk.resource_history import healthy, settings
from omk.resource_metrics import LinuxMetrics, read, validate_config
from omk.resource_store import MIB, ResourceStore, hourly_report, validate_sample

BOOT = "11111111-1111-4111-8111-111111111111"


def config():
    return {
        "schema": 1,
        "host": "fixture",
        "disks": ["vda"],
        "interfaces": ["eth0"],
        "filesystems": {"project": "project"},
        "services": {"dj2": {"cgroup": "omk-dj2", "release": "dj2-2.23.4"}},
    }


def sample(at=1000, sequence=1, metrics=None, **extra):
    return {
        "schema": 1,
        "at": at,
        "collector": "a" * 32,
        "sequence": sequence,
        "host": "fixture",
        "host_boot": BOOT,
        "config_sha256": "b" * 64,
        "interval_seconds": 30,
        "releases": {"dj2": "dj2-2.23.4"},
        "metrics": {"host.memory.used_bytes": 100} if metrics is None else metrics,
        "issues": [],
        "sources": {},
        **extra,
    }


@pytest.fixture
def inputs(tmp_path, monkeypatch):
    host, cgroups, storage = (tmp_path / k for k in ("host", "cgroups", "storage"))
    group = cgroups / "omk-dj2"
    for p in (host, group, storage / "project"):
        p.mkdir(parents=True)
    files = {
        host / "boot_id": BOOT,
        host / "stat": "cpu 100 0 50 800 20 0 10 20 99 0\ncpu0 0\ncpu1 0\n",
        host
        / "meminfo": "MemTotal: 10000 kB\nMemAvailable: 6000 kB\nSwapTotal: 2000 kB\nSwapFree: 1800 kB\n",
        host / "vmstat": "pswpin 0\npswpout 2\npgmajfault 5\noom_kill 0\n",
        host / "diskstats": "8 0 vda 10 0 100 20 20 0 300 40 0 50 60\n",
        host / "netdev": "header\neth0: 100 1 0 0 0 0 0 0 200 2 0 0 0 0 0 0\n",
        group / "cpu.stat": "usage_usec 1000000\nthrottled_usec 100\n",
        group / "memory.events": "oom_kill 0\n",
        group / "memory.current": "1024\n",
        group / "memory.swap.current": "0\n",
        group / "memory.max": "4096\n",
        group / "io.stat": "8:0 rbytes=100 wbytes=200 rios=1 wios=2\n",
        group / "cgroup.events": "populated 1\nfrozen 0\n",
    }
    for kind in ("cpu", "memory", "io"):
        files[host / ("pressure-" + kind)] = (
            "some avg10=1.25 avg60=0.00 avg300=0.00 total=10\n"
        )
    for p, raw in files.items():
        p.write_text(raw, encoding="ascii")
    stats = namedtuple("Stats", "f_blocks f_frsize f_bavail f_bfree f_favail")(
        100, 4096, 20, 22, 1000
    )
    monkeypatch.setattr(os, "statvfs", lambda _: stats, raising=False)
    return (
        LinuxMetrics(config(), host=host, cgroups=cgroups, storage=storage),
        host,
        group,
    )


def test_host_memory_available_not_free_and_first_counter_has_no_rate(inputs):
    collector, _, _ = inputs
    data = collector.sample(1)
    assert data["issues"] == []
    assert data["interval_seconds"] is None
    assert data["metrics"]["host.memory.used_bytes"] == 4000 * 1024
    assert data["metrics"]["host.swap.used_bytes"] == 200 * 1024
    assert data["metrics"]["fs.project.available_bytes"] == 20 * 4096
    assert data["metrics"]["host.pressure.cpu.some_pct"] == 1.25
    assert "host.cpu.busy_pct" not in data["metrics"]
    assert "service.dj2.cpu_cores" not in data["metrics"]


def test_cpu_steal_separate_guest_excluded_and_one_core_not_total_pct(inputs):
    collector, host, group = inputs
    collector.sample(1)
    (host / "stat").write_text("cpu 120 0 60 840 30 0 10 40 999 0\ncpu0 0\ncpu1 0\n")
    (group / "cpu.stat").write_text("usage_usec 11000000\nthrottled_usec 500100\n")
    result = collector.sample(11)["metrics"]
    assert result["host.cpu.busy_pct"] == 30
    assert result["host.cpu.steal_pct"] == 20
    assert result["host.cpu.iowait_pct"] == 10
    assert result["service.dj2.cpu_cores"] == 1
    assert result["service.dj2.throttled_seconds_per_second"] == 0.05


def test_disk_sector_unit_latency_and_network_rates(inputs):
    collector, host, _ = inputs
    collector.sample(1)
    (host / "diskstats").write_text("8 0 vda 20 0 120 70 40 0 340 100 2 550 60\n")
    (host / "netdev").write_text("eth0: 300 1 0 2 0 0 0 0 700 2 1 0 0 0 0 0\n")
    result = collector.sample(11)["metrics"]
    assert result["disk.vda.read_bytes_per_second"] == 1024
    assert result["disk.vda.write_bytes_per_second"] == 2048
    assert result["disk.vda.read_mean_ms"] == 5
    assert result["disk.vda.write_mean_ms"] == 3
    assert result["disk.vda.busy_pct"] == 5
    assert result["net.eth0.tx_bytes_per_second"] == 50
    assert result["net.eth0.rx_drops_per_second"] == 0.2


@pytest.mark.parametrize(
    "change", ["gap", "host-reboot", "backwards", "counter-reset", "new-instance"]
)
def test_never_average_across_gap_restart_or_counter_reset(inputs, change):
    collector, host, group = inputs
    collector.sample(10)
    now = 40
    if change == "gap":
        now = 500
    elif change == "backwards":
        now = 9
    elif change == "host-reboot":
        (host / "boot_id").write_text("22222222-2222-4222-8222-222222222222")
    elif change == "counter-reset":
        (group / "cpu.stat").write_text("usage_usec 1\nthrottled_usec 0\n")
    else:
        (group / "new-container").mkdir()
    assert "service.dj2.cpu_cores" not in collector.sample(now)["metrics"]


def test_missing_source_does_not_masquerade_as_idle_or_bridge_gap(inputs):
    collector, _, group = inputs
    collector.sample(1)
    (group / "cpu.stat").unlink()
    data = collector.sample(31)
    assert "service.dj2:unavailable" in data["issues"]
    assert "service.dj2.memory_bytes" not in data["metrics"]
    (group / "cpu.stat").write_text("usage_usec 100000000\nthrottled_usec 100\n")
    assert "service.dj2.cpu_cores" not in collector.sample(61)["metrics"]


def test_missing_cpu_line_is_partial_data_not_collector_failure(inputs):
    collector, host, _ = inputs
    (host / "stat").write_text("not cpu\n")
    data = collector.sample(1)
    assert "host.cpu:unavailable" in data["issues"]
    assert data["metrics"]["service.dj2.memory_bytes"] == 1024


@pytest.mark.parametrize(
    "bad", ["../../secret", "/secret", "a//b", "a/../b", "a/./b", "a\\b", "", None]
)
def test_cgroup_path_allowlist(bad):
    value = config()
    value["services"]["dj2"]["cgroup"] = bad
    with pytest.raises(ValueError, match="Invalid service"):
        validate_config(value)


@pytest.mark.parametrize(
    "field,value",
    [
        ("disks", ["vda"] * 33),
        ("interfaces", ["x\npassword"]),
        ("schema", True),
        ("host", "my secret"),
        ("filesystems", {"data": "../../secret"}),
        ("services", {"dj2": {"cgroup": "omk-dj2", "release": "password=secret"}}),
    ],
)
def test_config_rejects_values_without_echo(field, value):
    data = config()
    data[field] = value
    with pytest.raises(ValueError) as error:
        validate_config(data)
    assert "secret" not in str(error.value)


def test_unlisted_private_files_never_read(inputs):
    collector, host, group = inputs
    (host / "environ").write_text("password=must-not-read")
    (group / "secret").write_text("password=must-not-read")
    assert "must-not-read" not in json.dumps(collector.sample(1))


@pytest.mark.skipif(
    sys.platform != "linux", reason="Linux pseudo files and filesystem links"
)
def test_nonblocking_reader_rejects_fifo_links_and_oversized(tmp_path):
    pipe = tmp_path / "pipe"
    os.mkfifo(pipe)
    with pytest.raises(ValueError, match="regular"):
        read(pipe)
    big = tmp_path / "big"
    big.write_bytes(b"0" * (MIB + 1))
    with pytest.raises(ValueError, match="bound"):
        read(big)
    linked = tmp_path / "linked"
    linked.symlink_to(big)
    with pytest.raises(ValueError, match="Linked"):
        read(linked)


def test_store_reopen_aggregate_missing_not_zero_and_no_double_count(tmp_path):
    root = tmp_path / "history"
    with ResourceStore(root, reserve_mib=16) as store:
        assert store.append(sample())
        assert not store.append(sample())
        assert store.append(
            sample(1030, 2, {"host.memory.used_bytes": 300, "host.cpu.busy_pct": 80})
        )
    with ResourceStore(root, reserve_mib=16) as store:
        assert not store.append(
            sample(1030, 2, {"host.memory.used_bytes": 300, "host.cpu.busy_pct": 80})
        )
        assert store.db.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    report = hourly_report(root / "history.sqlite3", since=1, until=3600)
    assert report["resolution"] == "whole_hour"
    assert report["hours"][0]["samples"] == 2
    gauges = report["hours"][0]["metrics"]
    assert gauges["host.memory.used_bytes"] == {
        "count": 2,
        "min": 100,
        "max": 300,
        "mean": 200,
    }
    assert gauges["host.cpu.busy_pct"]["count"] == 1


def test_clock_backwards_identity_conflict_and_config_separation(tmp_path):
    with ResourceStore(tmp_path / "h", reserve_mib=16) as store:
        store.append(sample())
        with pytest.raises(ValueError, match="conflict"):
            store.append(sample(metrics={"x": 9}))
        with pytest.raises(ValueError, match="clock"):
            store.append(sample(900, 2))
        store.append(sample(1030, 2, config_sha256="c" * 64))
        assert store.db.execute("SELECT COUNT(*) FROM hours").fetchone()[0] == 2


def test_age_retention_and_capacity_eviction_preserve_recent_and_hour_peaks(tmp_path):
    root = tmp_path / "h"
    with ResourceStore(
        root, database_mib=4, detail_days=1, hourly_days=2, reserve_mib=16
    ) as store:
        gauges = {"host.metric_" + str(i): i for i in range(800)}
        for i in range(240):
            store.append(sample(1000 + i, i + 1, gauges))
        assert store.db.execute("SELECT COUNT(*) FROM samples").fetchone()[0] < 240
        assert (
            store.db.execute("SELECT MAX(sequence) FROM samples").fetchone()[0] == 240
        )
        assert store.db.execute("SELECT count FROM hours").fetchone()[0] == 240
        assert store.database.stat().st_size <= 4 * MIB
        store.append(sample(1000 + 86400 + 500, 241))
        assert store.db.execute("SELECT COUNT(*) FROM samples").fetchone()[0] == 1
        assert store.db.execute("SELECT COUNT(*) FROM hours").fetchone()[0] == 2
        store.append(sample(1000 + 3 * 86400, 242))
        assert store.db.execute("SELECT COUNT(*) FROM hours").fetchone()[0] == 2
        assert store.db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_writer_lock_and_no_other_files_pruned(tmp_path):
    root = tmp_path / "h"
    with ResourceStore(root, reserve_mib=16) as store:
        store.append(sample())
        with pytest.raises(OSError):
            ResourceStore(root, reserve_mib=16)
    other = root / "operator-do-not-delete.txt"
    other.write_text("private")
    with pytest.raises(ValueError, match="Unexpected"):
        ResourceStore(root, reserve_mib=16)
    assert other.read_text() == "private"


def test_low_space_fails_before_sample_and_preserves_history(tmp_path, monkeypatch):
    import omk.resource_store as module  # noqa: PLC0415

    with ResourceStore(tmp_path / "h", reserve_mib=16) as store:
        store.append(sample())
        original = store.database.read_bytes()
        usage = namedtuple("Usage", "total used free")(100 * MIB, 99 * MIB, MIB)
        monkeypatch.setattr(module.shutil, "disk_usage", lambda _: usage)
        with pytest.raises(OSError, match="reserve"):
            store.append(sample(1030, 2))
        assert store.database.read_bytes() == original


def test_bad_sample_or_excess_cardinality_cannot_write(tmp_path):
    with ResourceStore(tmp_path / "h", reserve_mib=16) as store:
        for value in (float("nan"), float("inf"), -1, True, "password=secret"):
            with pytest.raises(ValueError):
                store.append(sample(metrics={"host.cpu": value}))
        with pytest.raises(ValueError):
            store.append(sample(metrics={"x" + str(i): i for i in range(1025)}))
        assert store.db.execute("SELECT COUNT(*) FROM samples").fetchone()[0] == 0


def test_readonly_report_intersects_hour_is_bounded_and_never_creates_missing(tmp_path):
    root = tmp_path / "h"
    with ResourceStore(root, reserve_mib=16) as store:
        store.append(sample())
        store.append(sample(4600, 2))
    database = root / "history.sqlite3"
    before = database.read_bytes()
    report = hourly_report(database, since=999, until=7200, max_rows=1)
    assert len(report["hours"]) == 1
    assert report["truncated"]
    assert database.read_bytes() == before
    with pytest.raises(ValueError):
        hourly_report(root / "missing", since=1, until=100)
    assert not (root / "missing").exists()


def test_report_payload_byte_bound(tmp_path):
    root = tmp_path / "h"
    gauges = {"host.metric_" + str(i): i for i in range(800)}
    with ResourceStore(root, reserve_mib=16) as store:
        for i in range(8):
            store.append(sample(1000 + 3600 * i, i + 1, gauges))
    report = hourly_report(
        root / "history.sqlite3", since=1, until=40000, max_bytes=65536
    )
    assert report["truncated"]
    assert 0 < len(report["hours"]) < 8


@pytest.mark.skipif(sys.platform != "linux", reason="Linux private modes")
def test_private_permissions_and_linked_database_rejected(tmp_path):
    root = tmp_path / "h"
    with ResourceStore(root, reserve_mib=16) as store:
        store.append(sample())
    assert root.stat().st_mode & 0o777 == 0o700
    assert all(p.stat().st_mode & 0o777 == 0o600 for p in root.iterdir())
    destination = tmp_path / "outside"
    (root / "history.sqlite3").rename(destination)
    (root / "history.sqlite3").symlink_to(destination)
    before = destination.read_bytes()
    with pytest.raises(ValueError):
        ResourceStore(root, reserve_mib=16)
    assert destination.read_bytes() == before


@pytest.mark.parametrize(
    "key,value",
    [
        ("INTERVAL_SECONDS", "0"),
        ("INTERVAL_SECONDS", "9"),
        ("DATABASE_MIB", "3"),
        ("DETAIL_DAYS", "31"),
        ("RESERVE_MIB", "secret"),
        ("HOURLY_DAYS", "-1"),
        ("DATABASE_MIB", "４"),
        ("INTERVAL_SECONDS", "30\n"),
        ("HOURLY_DAYS", "1"),
    ],
)
def test_bad_env_rejected_without_echo(key, value):
    with pytest.raises(ValueError) as error:
        settings({"OMK_METRICS_" + key: value})
    assert "secret" not in str(error.value)


def test_defaults_and_deployment_example_schema():
    assert settings({}) == {
        "interval_seconds": 30,
        "database_mib": 64,
        "detail_days": 7,
        "hourly_days": 180,
        "reserve_mib": 1024,
    }
    root = Path(__file__).resolve().parents[2]
    value = json.loads((root / "deploy/metrics/config.example.json").read_text())
    assert validate_config(value) == value
    original = sample()
    assert json.loads(validate_sample(copy.deepcopy(original))) == original


def test_health_requires_recent_commit_not_just_database_file(tmp_path):
    path = tmp_path / "h" / "history.sqlite3"
    assert not healthy(path, now=1000, interval=30)
    with ResourceStore(path.parent, reserve_mib=16) as store:
        assert not healthy(path, now=1000, interval=30)
        store.append(sample())
        assert healthy(path, now=1090, interval=30)
        assert not healthy(path, now=1091, interval=30)
        assert not healthy(path, now=999, interval=30)


def test_io_counters_and_child_epoch_inode_reset(inputs):
    collector, _, group = inputs
    child = group / "same-container-name"
    child.mkdir()
    first = collector.sample(1)
    (group / "io.stat").write_text("8:0 rbytes=200 wbytes=500 rios=3 wios=8\n")
    second = collector.sample(11)
    assert second["metrics"]["service.dj2.io.wbytes_per_second"] == 30
    # Keep the old inode alive elsewhere so the new name gets a different inode.
    child.rename(group / "old")
    child.mkdir()
    third = collector.sample(21)
    assert third["sources"]["dj2"] != first["sources"]["dj2"]
    assert "service.dj2.io.wbytes_per_second" not in third["metrics"]
