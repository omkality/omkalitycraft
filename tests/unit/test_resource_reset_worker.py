from unittest.mock import Mock

import pytest

from omk import resource_reset_worker as worker


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
