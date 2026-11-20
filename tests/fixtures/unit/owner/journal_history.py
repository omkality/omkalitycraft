"""Test dependencies for journal history."""

import hashlib
import json
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from omk.owner.admin import _write_private
from omk.owner.maintenance import (
    journal_history as history,
    nightly_cycle as cycle,
)
from tests.fixtures.unit.owner import nightly_cycle as cycle_fixture

cycle_flow = cycle_fixture.flow


@pytest.fixture
def flow(cycle_flow, monkeypatch):
    monkeypatch.setattr(
        history.shutil, "disk_usage", lambda _: SimpleNamespace(free=10**12)
    )
    r = cycle.run(cycle_flow.cfg, server="dj2", environment=cycle_flow.env)
    cycle_flow.root = cycle.read(cycle_flow.cfg, r["operation"])
    cycle_flow.env.update(
        OMK_JOURNAL_ARCHIVE_ENABLED="true", OMK_JOURNAL_ARCHIVE_KEEP_CYCLES="1"
    )
    clone(cycle_flow, cycle_flow.root, 1)
    cycle_flow.actions.clear()
    return cycle_flow


def clone(flow, root, offset):
    result = None
    ids = {
        v: hashlib.sha256((v + str(offset)).encode()).hexdigest()[:32]
        for v in [root["operation"], *root["children"].values()]
    }
    for area, r in history.scope(flow.cfg, root):
        raw = json.dumps(r)
        for old, new in ids.items():
            raw = raw.replace(old, new)
        value = json.loads(raw)
        for key in ("created_at", "updated_at"):
            value[key] = (
                datetime.fromisoformat(r[key]) + timedelta(days=offset)
            ).isoformat()
        _write_private(
            history.path(flow.cfg, area, value["operation"]), flow.cfg.private, value
        )
        if area == "nightly":
            result = value
    return result
