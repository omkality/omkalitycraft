"""Test dependencies for admin storage."""

import json
from copy import deepcopy

import pytest

from omk.owner import admin_storage as owner
from omk.owner.admin import AdminError
from tests.fixtures.unit.owner.operator_commands import config


@pytest.fixture
def controller(tmp_path, monkeypatch):
    cfg, path = config(tmp_path)
    target = {"world": "world", "data_volume": "source", "store_volume": "store"}
    state = {"calls": [], "engine": 0, "generation": 1, "lost": False}
    report = {
        "schema": 1,
        "resources": [],
        "filesystems": [{"roles": ["source", "store"], "available_bytes": 200}],
        "read_only": True,
        "metadata_only": True,
        "host_disk_complete": False,
    }

    def engine():
        state["engine"] += 1

    def source(config, server):
        if server not in config.servers:
            raise AdminError("Server is not in the operator allowlist")
        return dict(target)

    def volume(target, store=False):
        return {
            "created": state["generation"],
            "name": target["store_volume" if store else "data_volume"],
        }

    def docker(*args, **kw):
        state["calls"].append((args, kw))
        if state["lost"]:
            raise AdminError("Docker unavailable")
        return json.dumps({"ok": True, "result": deepcopy(report)})

    monkeypatch.setattr(owner.backups, "local_engine", engine)
    monkeypatch.setattr(owner.backups, "target_for", source)
    monkeypatch.setattr(owner.backups, "volume", volume)
    monkeypatch.setattr(owner.backups, "docker", docker)
    return cfg, path, state, report
