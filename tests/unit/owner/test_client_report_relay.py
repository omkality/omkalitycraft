import json
import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from omk.cli import main
from omk.observability.incidents import MAX_REPORT_BYTES
from omk.observability.report_store import ReportStore
from omk.owner.client_report_relay import ReportRelay
from tests.fixtures.unit.owner.operator_commands import config


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
