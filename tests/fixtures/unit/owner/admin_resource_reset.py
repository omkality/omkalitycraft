"""Test dependencies for admin resource reset."""

import copy
from unittest.mock import Mock

import pytest

from omk.owner import admin_resource_reset as owner
from tests.fixtures.unit.owner.operator_commands import config

TARGET = {
    "data_volume": "source",
    "store_volume": "store-not-mounted",
    "world": "world",
}


def reply():
    return {
        "schema": 1,
        "adapter": "dj2-ftb5.4-jed1.6-inspection-v1",
        "world": "world",
        "resource_identity": {"dimension": "-18000"},
        "world_inventory_sha256": "a" * 64,
        "world_changes": False,
        "reset_plan": False,
        "can_apply": False,
        "backup_verified": False,
    }


@pytest.fixture
def controller(tmp_path, monkeypatch):
    settings, path = config(tmp_path)
    checkpoint = {"container": "owned-stopped-checkpoint"}
    monkeypatch.setattr(
        owner.backups, "target_for", Mock(return_value=copy.deepcopy(TARGET))
    )
    monkeypatch.setattr(owner.backups, "local_engine", Mock())
    monkeypatch.setattr(owner.backups, "checkpoint", Mock(return_value=checkpoint))
    fake_worker = Mock(return_value=reply())
    monkeypatch.setattr(owner, "worker", fake_worker)
    return settings, path, fake_worker
