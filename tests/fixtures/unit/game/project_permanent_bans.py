"""Synthetic Drasl account and consoles for permanent project bans."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from omk.game import project_permanent_bans as permanent
from tests.fixtures.unit.game.project_moderation import UUID, project

__all__ = ["project"]
ACCOUNT = "22345678-1234-4234-8234-123456789abc"


@pytest.fixture
def drasl(project, monkeypatch):
    user = {
        "uuid": ACCOUNT,
        "username": "FirstJoin",
        "isLocked": False,
        "players": [{"uuid": UUID, "name": "FirstJoin", "userUuid": ACCOUNT}],
    }
    state = SimpleNamespace(
        project=project,
        user=user,
        calls=[],
        drained=[],
        fails=set(),
        lose_reply=False,
        caller="32345678-1234-4234-8234-123456789abc",
    )

    def request(method, path, payload=None, token=None):
        assert token == "test operator token"
        if method == "GET":
            return [deepcopy(user)] if path == permanent.USERS else deepcopy(user)
        assert method == "PATCH" and path == f"{permanent.USERS}/{ACCOUNT}"
        state.calls.append(payload.copy())
        user["isLocked"] = payload["isLocked"]
        if state.lose_reply:
            raise OSError("simulated lost response")

    def console(server, _password):
        def disconnect(profiles):
            assert profiles == {UUID: "FirstJoin"}
            if server in state.fails:
                raise OSError("simulated offline server")
            state.drained.append(server)

        return SimpleNamespace(disconnect=disconnect)

    monkeypatch.setattr(
        permanent,
        "_operator",
        lambda _: (
            SimpleNamespace(request=request),
            "test operator token",
            state.caller,
        ),
    )
    monkeypatch.setattr(permanent, "credential", lambda _, server: (server, "test"))
    monkeypatch.setattr(permanent, "RecoveryConsole", console)
    return state
