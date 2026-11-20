"""Test dependencies for client incidents."""

from uuid import uuid4


def report(player=None, **updates):
    return {
        "schema": 1,
        "id": uuid4().hex,
        "player": player or uuid4().hex,
        "occurred_at": "2026-10-30T12:00:00+00:00",
        "pack": "dj2",
        "pack_version": "test",
        "minecraft": "1.12.2",
        "platform": "windows-x64",
        "launcher": "test",
        "memory_mb": 6144,
        "exit_code": 1,
        "kind": "minecraft_crash",
        "detail": "java.lang.TestException\n at example.main(Test.java:12)",
        **updates,
    }
