"""Test dependencies for player time."""

import hashlib
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from omk.game import (
    player_time as owner,
    player_time_reader as reader,
)
from omk.owner.admin import AdminError

PLAYER = "7d714b9e-996b-4d72-ab5a-f3e38b3ffb26"


@pytest.fixture
def source(tmp_path, monkeypatch):
    root = tmp_path / "server"
    (root / "world/stats").mkdir(parents=True)
    jar = b"only a unit runtime fixture"
    (root / "forge.jar").write_bytes(jar)
    monkeypatch.setattr(
        reader,
        "runtime_pin",
        lambda: {"path": "forge.jar", "sha256": hashlib.sha256(jar).hexdigest()},
    )
    return root


@pytest.fixture
def controller(tmp_path, monkeypatch):
    cfg = SimpleNamespace(private=tmp_path)
    monkeypatch.setattr(owner.backups, "local_engine", lambda: None)
    monkeypatch.setattr(
        owner.backups, "target_for", lambda *a: {"release": "dj2-candidate"}
    )
    monkeypatch.setattr(owner.maintenance, "binding", lambda *a: {})
    state = {"running": True, "identity": "stable"}
    monkeypatch.setattr(owner.maintenance, "snapshot", lambda *a: dict(state))
    worker = Mock(
        return_value={
            "schema": 1,
            "player_uuid": PLAYER,
            "source": "forge112_saved_stat_play_one_minute",
            "available": False,
            "reason": "no_saved_statistics",
        }
    )
    monkeypatch.setattr(owner, "_worker", worker)
    return cfg, state, worker


@pytest.fixture
def transport(monkeypatch):
    calls = []
    state = {}
    data = {
        "schema": 1,
        "player_uuid": PLAYER,
        "source": "forge112_saved_stat_play_one_minute",
        "available": False,
        "reason": "no_saved_statistics",
    }

    def docker(*args, **kwargs):
        calls.append((args, kwargs))
        if args[0] == "run":
            label = args[args.index("--label") + 1]
            state["operation"] = label.split("=", 1)[1]
            if state.get("timeout"):
                raise AdminError("helper timeout")
            return state.get("response", json.dumps({"ok": True, "data": data}))
        if args[0] == "inspect":
            if state.get("auto_removed"):
                return "[]\n"
            return json.dumps(
                [
                    {
                        "Id": "a" * 64,
                        "Config": {
                            "Image": owner.backups.IMAGE,
                            "Labels": {
                                owner.LABEL: state.get("owner", state["operation"])
                            },
                        },
                    }
                ]
            )
        return ""

    monkeypatch.setattr(owner.backups, "docker", docker)
    return calls, state, data
