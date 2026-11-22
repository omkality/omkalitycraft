"""Test dependencies for world cutover worker."""

import json

import pytest

from omk.worlds import world_cutover_worker as cutover
from omk.worlds.reset import resource_reset_runtime as runtime
from omk.worlds.reset.dimension_reset import layout
from tests.fixtures.unit.backups.ftb_restore_authority import records
from tests.fixtures.unit.worlds.resource_reset_inventory import sample
from tests.fixtures.unit.worlds.resource_reset_runtime import (
    prepared as prepared_runtime,
)
from tests.fixtures.unit.worlds.resource_reset_stage import data

__all__ = ["data", "records", "sample"]


@pytest.fixture
def prepared(data):
    return prepared_runtime.__wrapped__(data)


@pytest.fixture
def full_world_exchange(data, monkeypatch):
    request = data[0]
    request.update(dimension=0, position="auto", reset=layout(0, all_worlds=True))
    return exchange.__wrapped__(prepared_runtime.__wrapped__(data), monkeypatch)


@pytest.fixture
def exchange(prepared, monkeypatch):
    request, source, storage, target = prepared
    runtime.execute({**request, "action": "runtime-stage"}, source, storage, target)
    request = {
        "schema": 1,
        "action": "plan",
        "operation": "e" * 32,
        "runtime": {**request, "action": "runtime-verify"},
        "expected": None,
        "write_lease": None,
    }
    control = source.parent / "control"
    control.mkdir()
    value = {
        "schema": 1,
        "operation": request["operation"],
        "stage": "planned",
        "write_lease": None,
    }
    (control / "lease.json").write_text(json.dumps(value))
    monkeypatch.setattr(cutover, "CONTROL", control)
    expected = cutover.execute(request, source, storage, target)
    value.update(stage="applying", write_lease="f" * 32)
    (control / "lease.json").write_text(json.dumps(value))
    return (
        {**request, "expected": expected, "write_lease": "f" * 32},
        source,
        storage,
        target,
    )
