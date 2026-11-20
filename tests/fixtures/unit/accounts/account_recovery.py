"""Test dependencies for account recovery."""

import copy
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest

from omk.accounts import account_recovery as recovery
from omk.labs.recovery.recovery_console import ConsoleConfig
from omk.owner.admin import _write_private
from tests.fixtures.unit.owner.operator_commands import config


@pytest.fixture
def setup(tmp_path, monkeypatch):
    cfg, path = config(tmp_path)
    cfg = replace(cfg, recovery_consoles={"dj2": ConsoleConfig(25577, "rcon.json")})
    _write_private(
        cfg.private / "rcon.json", cfg.private, {"password": "private-rcon-secret"}
    )
    account, operator = str(uuid4()), str(uuid4())
    players = [
        {"uuid": str(uuid4()), "name": "player" + str(i), "userUuid": account}
        for i in range(2)
    ]
    user = {
        "uuid": account,
        "username": "test_player",
        "isAdmin": False,
        "isLocked": False,
        "players": players,
    }
    calls, passwords = [], []

    def request(method, route, payload=None, token=None):
        calls.append((method, route, copy.deepcopy(payload)))
        if method == "PATCH":
            user.update({k: v for k, v in payload.items() if k == "isLocked"})
            if "password" in payload:
                passwords.append(payload["password"])
        return (
            [copy.deepcopy(user)] if route.endswith("/users") else copy.deepcopy(user)
        )

    client = Mock(request=Mock(side_effect=request))
    monkeypatch.setattr(
        recovery, "_operator", lambda _: (client, "admin-secret", operator)
    )
    console = Mock()
    console.online.return_value = {}
    console.remaining.return_value = 0
    monkeypatch.setattr(recovery, "RecoveryConsole", lambda *a: console)
    return SimpleNamespace(
        config=cfg,
        path=path,
        user=user,
        account=account,
        players=players,
        calls=calls,
        passwords=passwords,
        client=client,
        console=console,
    )
