"""Synthetic transcript rows with stable account IDs and two boot sessions."""

import json
from datetime import UTC, datetime

import pytest

from tests.fixtures.unit.owner.operator_commands import config

START = int(datetime(2026, 11, 27, 12, tzinfo=UTC).timestamp() * 1000)
BOOT = "a" * 32
NEXT_BOOT = "b" * 32
ACTOR = "772bf91f-41c3-4c8b-bc6d-fdf556f7fa8c"
RECIPIENT = "7090206f-aba4-43dc-80b2-99cbfab8d0ff"


def control(boot, kind, second, *, dropped=0):
    return {
        "schema": 1,
        "kind": kind,
        "at_ms": START + 1000 * second,
        "server": "dj2",
        "profile": "omkalitycraft.dj2",
        "core_version": "0.3.17",
        "boot": boot,
        "dropped": dropped,
        "retention_days": 90,
        "budget_bytes": 256 * 1024**2,
    }


def message(boot, sequence, second, text, *, name="OldNick", recipient=None, **fields):
    return {
        "schema": 1,
        "kind": "message",
        "at_ms": START + 1000 * second,
        "server": "dj2",
        "profile": "omkalitycraft.dj2",
        "core_version": "0.3.17",
        "boot": boot,
        "sequence": sequence,
        "channel": "private" if recipient else "public",
        "outcome": "sent",
        "actor": {
            "kind": "player",
            "uuid": ACTOR,
            "name": name,
            "display": name,
            "nickname": None,
        },
        "recipient": (
            {
                "kind": "player",
                "uuid": RECIPIENT,
                "name": recipient,
                "display": recipient,
                "nickname": None,
            }
            if recipient
            else None
        ),
        "target": None,
        "text": text,
        "truncated": False,
        **fields,
    }


def write_segment(root, boot, second, rows, *, tail=b""):
    path = root / f"chat-{START + 1000 * second:013d}-{boot}-000000001.jsonl"
    with path.open("xb") as stream:
        for row in rows:
            stream.write(json.dumps(row).encode("utf-8") + b"\n")
        stream.write(tail)
    path.chmod(0o600)
    return path


@pytest.fixture
def chat_history(tmp_path):
    settings, path = config(tmp_path, auth=False)
    directory = settings.private / "chat-history" / "dj2"
    directory.parent.mkdir(mode=0o700)
    directory.mkdir(mode=0o700)
    write_segment(
        directory,
        BOOT,
        0,
        [
            control(BOOT, "start", 0),
            message(BOOT, 1, 1, 'Русский, "quote", 🍵'),
            message(BOOT, 3, 3, "first DM", recipient="Other"),
            message(BOOT, 4, 4, "OldNick appears only in text", name="SomeoneElse"),
            control(BOOT, "checkpoint", 4, dropped=1),
        ],
        tail=b'{"interrupted":',
    )
    write_segment(
        directory,
        NEXT_BOOT,
        8,
        [
            control(NEXT_BOOT, "start", 8),
            message(NEXT_BOOT, 1, 9, "renamed", name="NewNick"),
            message(
                NEXT_BOOT,
                2,
                10,
                "offline",
                name="NewNick",
                channel="private",
                outcome="rejected",
                target="Other",
                truncated=True,
            ),
            control(NEXT_BOOT, "stop", 11),
        ],
    )
    return settings, path, directory
