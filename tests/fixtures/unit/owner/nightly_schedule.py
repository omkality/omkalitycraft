"""Test dependencies for nightly schedule."""

import hashlib
from datetime import UTC, datetime, timedelta

import pytest

from omk.deployment import ingress
from omk.owner import (
    admin_backups as backups,
    admin_maintenance as maintenance,
)
from omk.owner.admin import AdminError
from omk.owner.maintenance import nightly_schedule as schedule
from tests.fixtures.unit.owner import (
    nightly_cycle as cycle_fixture,
    owner_maintenance,
)

cycle_flow = cycle_fixture.flow


@pytest.fixture
def flow(cycle_flow, monkeypatch):
    value = cycle_flow
    value.clock["value"] = datetime(2026, 11, 12, tzinfo=UTC)
    value.env.update(
        OMK_NIGHTLY_SCHEDULE_ENABLED="true",
        OMK_NIGHTLY_TIMEZONE="UTC",
        OMK_NIGHTLY_LOCAL_TIME="00:10",
    )

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return (
                value.clock["value"].astimezone(tz)
                if tz
                else value.clock["value"].replace(tzinfo=None)
            )

    for module in (backups, maintenance, ingress, owner_maintenance):
        monkeypatch.setattr(module, "datetime", Clock)
    value.point["finished"] = (value.clock["value"] - timedelta(seconds=60)).isoformat()
    docker = backups.docker
    stop = maintenance.console_stop

    def engine_docker(*a, **kw):
        if a[0] == "start":
            value.clock["value"] += timedelta(milliseconds=1)
        return docker(*a, **kw)

    def engine_stop(*a, **kw):
        stop(*a, **kw)
        value.point["finished"] = value.clock["value"].isoformat()

    monkeypatch.setattr(backups, "docker", engine_docker)
    monkeypatch.setattr(maintenance, "console_stop", engine_stop)
    ready = value.console.ready

    def current_boot(adapter, *, boot=None):
        result = ready(adapter)
        actual = hashlib.sha256(value.state["started"].encode()).hexdigest()[:32]
        if boot is not None and actual != boot:
            raise AdminError("boot changed")
        return {**result, "boot": actual}

    monkeypatch.setattr(value.console, "ready", current_boot)
    return value


def arm(flow):
    result, _wait = schedule.tick(flow.cfg, "dj2", flow.env)
    assert result["phase"] == "armed"
    return schedule.read(flow.cfg, "dj2")


def due(flow, record):
    flow.clock["value"] = schedule.instant(record["window"]["warnings"][0]["at_utc"])


def reach(flow, phase):
    for _ in range(100):
        result, wait = schedule.tick(flow.cfg, "dj2", flow.env)
        if result["phase"] == phase:
            return result
        assert result["ok"], result
        flow.clock["value"] += timedelta(seconds=wait)
    pytest.fail("Calendar phase was not reached")
