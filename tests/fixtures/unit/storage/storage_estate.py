"""Test dependencies for storage estate."""

import json
from dataclasses import replace
from unittest.mock import Mock

import pytest

from omk.owner.storage import storage_estate as owner
from tests.fixtures.unit.owner.operator_commands import config


@pytest.fixture
def controller(tmp_path, monkeypatch):
    cfg, path = config(tmp_path)
    cfg = replace(
        cfg,
        servers={
            "dj2": tmp_path / "first",
            "second": tmp_path / "second",
            "future": tmp_path / "future",
        },
    )
    path.write_text(
        'schema=1\n[servers.dj2]\nroot="../first"\n[servers.second]\nroot="../second"\n[servers.future]\nroot="../future"\n'
    )
    state = {"generation": 1, "calls": [], "worker": 0}
    file = cfg.private / "storage.toml"
    file.write_text(
        'schema=1\n[volumes.auth]\nvolume="auth-volume"\nlabel="omkality.project"\nowner="owned"\n'
    )
    file.chmod(0o600)
    monkeypatch.setattr(
        owner.owner_volumes, "document", lambda *a: {"dj2": {}, "second": {}}
    )
    monkeypatch.setattr(owner.backups, "local_engine", Mock())
    monkeypatch.setattr(
        owner.admin_storage,
        "targets",
        lambda config, server: (
            {"world": "world-" + server},
            [
                (role, server + "-" + role, {"created": "date"})
                for role in ["source", "store"]
            ],
        ),
    )

    def docker(*args, **kw):
        state["calls"].append((args, kw))
        assert args[0] == "volume"
        return json.dumps(
            [
                {
                    "Name": "auth-volume",
                    "CreatedAt": state["generation"],
                    "Labels": {"omkality.project": "owned"},
                }
            ]
        )

    monkeypatch.setattr(owner.backups, "docker", docker)

    def worker(values, limits, policy):
        state["worker"] += 1
        return {
            "schema": 1,
            "read_only": True,
            "resources": [
                {
                    "id": e["id"],
                    "role": e["role"],
                    "categories": {
                        "active_world" if e["role"] == "source" else e["role"]: {
                            "apparent_bytes": 100,
                            "allocated_bytes": 4096,
                        }
                    },
                }
                for e in values
            ],
            "filesystems": [
                {
                    "resources": [e["id"] for e in values],
                    "total_bytes": 220 * 1024**3,
                    "available_bytes": 100 * 1024**3,
                }
            ],
        }

    monkeypatch.setattr(owner, "worker", worker)
    return cfg, path, state, worker


@pytest.fixture
def metrics_controller(controller, monkeypatch):
    cfg, _, state, _ = controller
    file = cfg.private / "storage.toml"
    file.write_text(
        file.read_text()
        + '\n[volumes.metrics]\nvolume="metrics-volume"\nlabel="omkality.project"\nowner="owned"\n'
    )

    def docker(*args, **kw):
        state["calls"].append((args, kw))
        assert args[:2] == ("volume", "inspect")
        return json.dumps(
            [
                {
                    "Name": args[2],
                    "CreatedAt": (
                        state["generation"] if args[2] == "metrics-volume" else 1
                    ),
                    "Labels": {"omkality.project": "owned"},
                }
            ]
        )

    monkeypatch.setattr(owner.backups, "docker", docker)
    return controller
