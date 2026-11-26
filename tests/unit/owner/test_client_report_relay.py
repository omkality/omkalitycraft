import json
import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from omk.cli import main
from omk.observability.incidents import MAX_REPORT_BYTES
from omk.observability.report_store import ReportStore
from omk.owner.client_report_relay import ReportRelay
from tests.fixtures.unit.launcher.client_incidents import report as incident_report
from tests.fixtures.unit.owner.operator_commands import config


def test_client_report_inspect_reads_only_bounded_hints(tmp_path, capsys):
    settings, path = config(tmp_path, auth=False)
    detail = """---- Minecraft Crash Report ----
Description: Rendering entity in world

java.lang.NullPointerException: private-command /not-an-action
    at example.renderer.EntityRenderer.render(EntityRenderer.java:42)

-- Entity being rendered --
Details:
    Entity Type: minecraft:pig (example.entity.Pig)
    Entity UUID: 12345678-9012-3456-7890-123456789012
    Entity's Block location: World: (-128,63,15), Chunk: (at 0,3,15 in -8,0)

-- Affected level --
Details:
    Level dimension: -1
    Level spawn location: World: (0,64,0), Chunk: (at 0,4,0 in 0,0)
"""
    requested = incident_report(detail=detail)
    other = incident_report(detail="not the selected event")
    store = ReportStore(settings.reports_root)
    for entry in (requested, other):
        store.ingest(entry, player=entry["player"], token="test-report-token")
    before = store.path.read_bytes()
    args = ["admin", "--config", str(path), "reports", "inspect", "--id"]
    assert main([*args, requested["id"]]) == 0
    output = capsys.readouterr().out
    result = json.loads(output)
    assert result["report_id"] == requested["id"]
    assert result["player"] == requested["player"]
    assert result["diagnostic"]["category"] == "rendering_entity"
    assert result["diagnostic"]["exception"] == "java.lang.NullPointerException"
    assert result["diagnostic"]["level_dimension"] == -1
    assert result["diagnostic"]["subject"] == {
        "registry_id": "minecraft:pig",
        "block": [-128, 63, 15],
        "entity_uuid": "12345678901234567890123456789012",
    }
    assert len(result["diagnostic"]["stack_signature"]) == 64
    assert "private-command" not in output
    assert "EntityRenderer.java" not in output
    assert other["id"] not in output
    assert not (settings.private / "report-exports").exists()
    assert store.path.read_bytes() == before

    assert main([*args, "../world"]) == 1
    assert json.loads(capsys.readouterr().out)["ok"] is False


def test_client_report_inspect_empty_inbox_has_no_new_database(tmp_path, capsys):
    settings, path = config(tmp_path, auth=False)
    assert (
        main(["admin", "--config", str(path), "reports", "inspect", "--id", "a" * 32])
        == 1
    )
    result = json.loads(capsys.readouterr().out)
    assert result["ok"] is False and result["error_type"] == "ValueError"
    assert not settings.reports_root.exists()


@pytest.mark.skipif(os.name != "posix", reason="The SSH relay runs on the VPS")
def test_client_report_browse_and_export_share_only_the_selected_report(
    tmp_path, capsys
):
    settings, config_path = config(tmp_path, auth=False)
    directory = tmp_path / "owner-relay"
    directory.mkdir()
    directory.chmod(0o750)
    args = ["admin", "--config", str(config_path), "reports"]
    relay = ["--windows-relay-dir", str(directory)]
    assert main([*args, "browse", *relay]) == 0
    assert json.loads(capsys.readouterr().out)["reports"] == []
    assert not list(directory.iterdir())

    report = {
        "schema": 1,
        "id": uuid4().hex,
        "player": uuid4().hex,
        "occurred_at": datetime.now(UTC).isoformat(),
        "pack": "dj2",
        "pack_version": "2.23.4",
        "minecraft": "1.12.2",
        "platform": "linux",
        "launcher": "0.3.6",
        "memory_mb": 8192,
        "exit_code": 1,
        "kind": "minecraft_crash",
        "detail": "Synthetic crash report",
    }
    store = ReportStore(settings.reports_root)
    store.ingest(report, player=report["player"], token="test-token", name="TestPlayer")
    assert main([*args, "browse", *relay]) == 0
    listing = json.loads(capsys.readouterr().out)
    assert listing["directory"] == str(directory)
    assert [row["id"] for row in listing["reports"]] == [report["id"]]
    assert listing["reports"][0]["name"] == "TestPlayer"
    assert "detail" not in listing["reports"][0]
    assert not list(directory.iterdir())

    assert main([*args, "export", "--id", uuid4().hex, *relay]) == 1
    capsys.readouterr()
    assert main([*args, "export", "--id", "../arbitrary", *relay]) == 1
    capsys.readouterr()
    assert not list(directory.iterdir())

    assert main([*args, "export", "--id", report["id"], *relay]) == 0
    export = directory / f"client-crash-{report['id']}.json"
    assert json.loads(capsys.readouterr().out)["report_file"] == str(export)
    assert export.stat().st_mode & 0o777 == 0o640
    assert json.loads(export.read_bytes()) == store.get(report["id"])

    assert main([*args, "export", "--id", report["id"]]) == 0
    native_export = settings.private / "report-exports" / f"{report['id']}.json"
    assert json.loads(capsys.readouterr().out)["report_file"] == str(native_export)
    assert native_export.stat().st_mode & 0o777 == 0o600


@pytest.mark.skipif(os.name != "posix", reason="The SSH relay runs on the VPS")
def test_relay_rejects_unrestricted_and_linked_directories(tmp_path):
    report = {"id": "a" * 32}
    tmp_path.chmod(0o755)
    with pytest.raises(PermissionError):
        ReportRelay(tmp_path).publish(report["id"], report)
    relay = tmp_path / "relay"
    relay.mkdir()
    relay.chmod(0o750)
    link = tmp_path / "link"
    link.symlink_to(relay)
    with pytest.raises(PermissionError):
        ReportRelay(link).publish(report["id"], report)
    with pytest.raises(ValueError, match="too large"):
        ReportRelay(relay).publish(
            report["id"], {**report, "detail": "a" * MAX_REPORT_BYTES}
        )
    assert not list(relay.iterdir())
