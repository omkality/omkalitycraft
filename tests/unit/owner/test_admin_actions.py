"""Acceptance for the owner action query, incident correlation and snapshot binding."""

import hashlib
import json
from argparse import ArgumentParser
from pathlib import Path

from omk.owner.admin import add_admin_commands, run_admin
from tests.fixtures.unit.owner.action_history import action_case, action_history
from tests.fixtures.unit.owner.chat_history import ACTOR, BOOT, START

__all__ = ["action_case", "action_history"]

WINDOW = ["--from", "2026-11-27T15:00:00+03:00", "--until", "2026-11-27T12:00:12Z"]
AREA = ["--area", "-40", "60", "-40", "40", "80", "40"]


def _run(path, *options, area=None):
    parser = ArgumentParser()
    add_admin_commands(parser.add_subparsers(required=True))
    return run_admin(
        parser.parse_args(
            [
                "admin",
                "--config",
                str(path),
                "action-history",
                "--server",
                "dj2",
                "--dimension",
                "0",
                *WINDOW,
                *(AREA if area is None else area),
                *options,
            ]
        )
    )


def test_action_filters_and_gaps_are_independent(action_history):
    _, path = action_history
    result = _run(path, "--player", ACTOR.replace("-", ""))
    assert result["ok"], result
    assert [row["actor"]["name"] for row in result["entries"]] == ["OldNick", "NewNick"]
    assert result["coverage"]["reported_dropped"] == 1
    assert result["coverage"]["observed_sequence_gaps"] == 2
    assert result["coverage"]["incomplete_segments"] == 1
    assert result["coverage"]["unclean_previous_boots"] == [BOOT]
    assert result["coverage"]["uncovered_ms"] == [
        [START + 4000, START + 8000],
        [START + 11000, START + 12000],
    ]
    all_actions = _run(path)
    assert all_actions["matches"] == 3
    assert all_actions["entries"][1]["actor"] == {"kind": "automation"}
    assert "PRIVATE_TEXT" not in json.dumps(all_actions)


def test_action_exports_are_bounded_and_validate_the_area(action_history):
    config, path = action_history
    result = _run(path, "--limit", "1", "--export")
    assert result["ok"] and result["more_matches"]
    output = Path(result["export"])
    assert output == config.private / "action-export.json"
    assert len(json.loads(output.read_text(encoding="utf8"))["entries"]) == 1
    assert not _run(path, area=["--area", "20", "0", "0", "10", "100", "50"])["ok"]
    assert not _run(path, "--limit", "1001")["ok"]
    assert not _run(path, "--incident", "incident.json")["ok"]


def test_case_persists_verified_snapshot_and_minimal_context_after_source_rotation(
    action_case,
):
    config, path, args, source, record = action_case
    result = _run(path, *args)
    assert result["ok"], result
    output = Path(result["evidence"])
    assert output == config.private / "action-evidence" / "fixture-case"
    assert not _run(path, *args)["ok"]
    for file in source.iterdir():
        file.unlink()
    source.rmdir()
    with (output / "archive.zip").open("rb") as stream:
        assert (
            hashlib.file_digest(stream, "sha256").hexdigest()
            == record["result"]["sha256"]
        )
    content = (output / "incident.json").read_text(encoding="utf8")
    value = json.loads(content)
    assert value["backup"]["runtime_sha256"] == record["source"]["runtime_sha256"]
    assert value["incident"]["frames"] == ["net.example.Fixture.tick"]
    assert value["incident"]["tps"] == 17.5
    assert value["history"]["matches"] == 3
    assert "PRIVATE_" not in content


def test_case_rejects_mismatched_location_or_damaged_snapshot(action_case):
    config, path, args, source, _ = action_case
    wrong = _run(path, *args, area=["--area", "3", "60", "0", "5", "80", "10"])
    assert not wrong["ok"] and "location" in wrong["error"]
    archive = source / "archive.zip"
    original = archive.read_bytes()
    archive.write_bytes(bytes([original[0] ^ 1]) + original[1:])
    bad = _run(path, *args)
    assert not bad["ok"] and bad["error_type"] == "ValueError"
    assert not list((config.private / "action-evidence").iterdir())
