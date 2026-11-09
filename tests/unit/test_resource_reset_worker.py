from unittest.mock import Mock

import pytest

from omk import resource_reset_worker as worker
from omk.resource_reset_preflight import settings


def request():
    return {
        "schema": 1,
        "action": "inspect",
        "world": "world",
        "dimension": -18000,
        "world_max_bytes": 1024,
    }


def test_worker_refuses_non_linux_without_accessing_source(monkeypatch):
    inspect = Mock()
    monkeypatch.setattr(worker, "inspect_resource", inspect)
    monkeypatch.setattr(worker.sys, "platform", "win32")
    with pytest.raises(ValueError, match="Linux"):
        worker.execute(request())
    inspect.assert_not_called()


@pytest.mark.parametrize(
    "change",
    [
        {"schema": True},
        {"schema": 2},
        {"action": "apply"},
        {"action": "plan"},
        {"world": "../world"},
        {"world": "other/world"},
        {"world": ""},
        {"world": 123},
        {"world_max_bytes": 0},
        {"world_max_bytes": 1024**4 + 1},
        {"world_max_bytes": True},
        {"extra": "unreviewed"},
    ],
)
def test_request_contract_is_strict_before_source_access(monkeypatch, change):
    inspect = Mock()
    monkeypatch.setattr(worker, "inspect_resource", inspect)
    monkeypatch.setattr(worker.sys, "platform", "linux")
    with pytest.raises(ValueError, match="request"):
        worker.execute({**request(), **change})
    inspect.assert_not_called()


def test_valid_request_uses_explicit_source_and_budget(tmp_path, monkeypatch):
    inspect = Mock(return_value={"can_apply": False})
    monkeypatch.setattr(worker, "inspect_resource", inspect)
    monkeypatch.setattr(worker.sys, "platform", "linux")
    assert worker.execute(request(), tmp_path) == {"can_apply": False}
    inspect.assert_called_once_with(tmp_path, "world", -18000, world_max_bytes=1024)


def test_preflight_request_keeps_readonly_inspection_and_checks_same_save(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(worker.sys, "platform", "linux")
    monkeypatch.setattr(
        worker,
        "inspect_resource",
        Mock(return_value={"world_inventory_sha256": "a" * 64}),
    )
    proof = {"world_inventory_sha256": "a" * 64, "ready_for_start": False}
    preflight = Mock(return_value=proof)
    monkeypatch.setattr(worker, "preflight", preflight)
    query = {**request(), "action": "preflight", "options": settings({})}
    assert worker.execute(query, tmp_path)["preflight"] == proof
    preflight.assert_called_once_with(
        tmp_path, "world", -18000, options=settings({}), world_max_bytes=1024
    )
    proof["world_inventory_sha256"] = "b" * 64
    with pytest.raises(ValueError, match="changed"):
        worker.execute(query, tmp_path)


def test_preflight_options_are_validated_before_reading_source(monkeypatch):
    monkeypatch.setattr(worker.sys, "platform", "linux")
    inspect = Mock()
    monkeypatch.setattr(worker, "inspect_resource", inspect)
    with pytest.raises(ValueError):
        worker.execute({**request(), "action": "preflight", "options": {}})
    inspect.assert_not_called()
