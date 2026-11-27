import json
import os
import subprocess
import sys
from argparse import ArgumentParser

from omk.owner.admin import add_admin_commands, run_admin
from tests.fixtures.unit.owner.chat_history import (
    ACTOR,
    BOOT,
    RECIPIENT,
    START,
    chat_history,
)

__all__ = ["chat_history"]

WINDOW = ["--from", "2026-11-27T15:00:00+03:00", "--until", "2026-11-27T12:00:12Z"]


def _run(path, *options, server="dj2", window=None):
    parser = ArgumentParser()
    add_admin_commands(parser.add_subparsers(required=True))
    return run_admin(
        parser.parse_args(
            ["admin", "--config", str(path), "chat-history", "--server", server]
            + (WINDOW if window is None else window)
            + list(options)
        )
    )


def _texts(result, *, matches_only=True):
    return [
        row["message"]["text"]
        for row in result["entries"]
        if row["match"] or not matches_only
    ]


def test_search_historical_names_and_context(chat_history):
    _settings, path, _directory = chat_history
    result = _run(path, "--player", "oldNICK", "--context", "1")
    assert result["ok"]
    assert _texts(result) == ['Русский, "quote", 🍵', "first DM"]
    assert _texts(result, matches_only=False)[-1] == "OldNick appears only in text"
    assert "renamed" in _texts(_run(path, "--player", ACTOR.replace("-", "")))


def test_search_recipient_distinguishes_offline_and_real_dispatch(chat_history):
    _settings, path, _directory = chat_history
    accepted = _run(path, "--recipient", RECIPIENT, "--channel", "private")
    assert _texts(accepted) == ["first DM"]
    matching_label = _run(path, "--recipient", "Other")
    assert _texts(matching_label) == ["first DM", "offline"]
    assert [row["message"]["outcome"] for row in matching_label["entries"]] == [
        "sent",
        "rejected",
    ]


def test_search_exposes_unclean_tail_sequence_gaps_and_dropped_messages(chat_history):
    _settings, path, _directory = chat_history
    result = _run(path, "--limit", "1")
    assert result["more_matches"]
    assert result["coverage"] == {
        "requested_ms": [START, START + 12_000],
        "uncovered_ms": [
            [START + 4000, START + 8000],
            [START + 11_000, START + 12_000],
        ],
        "incomplete_segments": 1,
        "truncated_messages": 1,
        "observed_sequence_gaps": 1,
        "reported_dropped": 1,
        "latest_boot_open": False,
        "unclean_previous_boots": [BOOT],
    }


def test_chat_export_is_private_and_replaces_only_its_previous_revision(chat_history):
    settings, path, _directory = chat_history
    dest = settings.private / "chat-export.json"
    first = _run(path, "--channel", "public", "--export")
    assert dest.samefile(first["export"])
    assert json.loads(dest.read_text(encoding="utf-8"))["matches"] == 3
    _run(path, "--channel", "private", "--recipient", RECIPIENT, "--export")
    assert _texts(json.loads(dest.read_text(encoding="utf-8"))) == ["first DM"]
    if os.name != "nt":
        assert dest.stat().st_mode & 0o777 == 0o600


def test_chat_search_rejects_unknown_server_and_naive_time(chat_history):
    _settings, path, _directory = chat_history
    assert not _run(path, server="../other")["ok"]
    wrong_window = ["--from", "2026-11-27T12:00", "--until", "2026-11-27T12:00:12Z"]
    assert not _run(path, window=wrong_window)["ok"]


def test_console_without_utf8_still_outputs_valid_json(chat_history):
    _settings, path, _directory = chat_history
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from omk.cli import main; raise SystemExit(main())",
            "admin",
            "--config",
            str(path),
            "chat-history",
            "--server",
            "dj2",
            *WINDOW,
        ],
        capture_output=True,
        check=True,
        encoding="ascii",
        env={**os.environ, "PYTHONIOENCODING": "ascii"},
        timeout=15,
    )
    assert _texts(json.loads(result.stdout))[0] == 'Русский, "quote", 🍵'
