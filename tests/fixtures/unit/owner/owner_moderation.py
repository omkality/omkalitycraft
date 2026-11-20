"""Test dependencies for owner moderation."""

import json

from omk.labs.recovery.recovery_console import ConsoleConfig
from tests.fixtures.unit.owner.operator_commands import config

UID = "12345678-1234-1234-1234-123456789abc"


def setup(tmp_path, monkeypatch):
    _, path = config(tmp_path)
    monkeypatch.setattr(
        "omk.owner.admin_maintenance.credential",
        lambda *a: (ConsoleConfig(25577, "rcon.json"), "synthetic-private-password"),
    )
    return path


def reply(text, **overrides):
    parts = text.split()
    return "OMK_MODERATION_V1 " + json.dumps(
        {
            "command": parts[2],
            "nonce": parts[3],
            "uuid": parts[4],
            "ok": True,
            "effect": "applied",
            "expires_at": None if parts[2] == "kick" else 2000000000,
            "error": None,
            **overrides,
        }
    )
