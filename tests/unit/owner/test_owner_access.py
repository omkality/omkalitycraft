import os
import subprocess
from unittest.mock import Mock

import pytest

from omk.owner.admin import AdminError, _read_json, _write_private, load_operator_config
from omk.owner.owner_access import (
    ADMINISTRATORS,
    CREATOR_OWNER,
    OWNER_RIGHTS,
    SYSTEM,
    _validate_windows_acl,
)
from omk.owner.panels.owner_console import run
from tests.fixtures.unit.owner.operator_commands import config

OWNER = "S-1-5-21-111-222-333-1001"


@pytest.mark.parametrize(
    "sid,flags",
    [
        (OWNER, 0),
        (SYSTEM, 0),
        (ADMINISTRATORS, 0),
        (OWNER_RIGHTS, 0),
        (CREATOR_OWNER, 8),
    ],
)
def test_private_windows_policy_accepts_owner_and_privileged_system_entries(sid, flags):
    _validate_windows_acl(OWNER, OWNER, [(0, flags, 0x1F01FF, sid)])


@pytest.mark.parametrize(
    "owner,entries",
    [
        (OWNER, None),
        ("S-1-5-21-111-222-333-1002", []),
        (OWNER, [(0, 0, 1, "S-1-1-0")]),
        (OWNER, [(0, 0, 1, "S-1-5-32-545")]),
        (OWNER, [(0, 8, 1, "S-1-5-11")]),
        (OWNER, [(0, 0, 1, CREATOR_OWNER)]),
        (OWNER, [(9, 0, 1, OWNER)]),
    ],
)
def test_private_windows_policy_refuses_shared_unknown_or_foreign_access(
    owner, entries
):
    with pytest.raises(PermissionError, match="Owner-only"):
        _validate_windows_acl(owner, OWNER, entries)


@pytest.mark.skipif(os.name == "nt", reason="POSIX identity boundary")
def test_posix_operator_config_requires_the_same_os_owner(tmp_path, monkeypatch):
    _, path = config(tmp_path)
    actual = os.geteuid()
    monkeypatch.setattr("omk.owner.owner_access.os.geteuid", lambda: actual + 1)
    with pytest.raises(AdminError, match="Owner-only"):
        load_operator_config(path)


@pytest.mark.skipif(os.name == "nt", reason="POSIX root traversal boundary")
def test_owner_journal_subfolder_inside_private_root_keeps_existing_workflows(tmp_path):
    settings, _ = config(tmp_path)
    folder = settings.private / "journals"
    folder.mkdir(mode=0o755)
    path = folder / "record.json"
    _write_private(path, settings.private, {"retained": True})
    assert _read_json(path, settings.private) == {"retained": True}
    assert not path.stat().st_mode & 0o077


def _share_fixture(path):
    # Grant Everyone read access on this disposable path only.
    subprocess.run(
        ["icacls.exe", str(path), "/grant", "*S-1-1-0:R"],
        capture_output=True,
        check=True,
        timeout=15,
    )


@pytest.mark.skipif(os.name != "nt", reason="Native NTFS ACL enforcement")
@pytest.mark.parametrize("target", ["directory", "config", "credential", "destination"])
def test_native_windows_rejects_shared_acl_before_reading_or_sending_commands(
    tmp_path, monkeypatch, target
):
    settings, path = config(tmp_path)
    if target == "destination":
        folder = settings.private / "shared-child"
        folder.mkdir()
        _share_fixture(folder)
        destination = folder / "not-written.json"
        with pytest.raises(AdminError, match="Owner-only"):
            _write_private(destination, settings.private, {"must_not_be_written": True})
        assert not destination.exists()
        return
    secret = settings.private / "rcon.json"
    _write_private(
        secret, settings.private, {"password": "disposable-fixture-password"}
    )
    destination = {"directory": settings.private, "config": path, "credential": secret}[
        target
    ]
    _share_fixture(destination)
    if target == "credential":
        with pytest.raises(AdminError, match="Owner-only"):
            _read_json(secret, settings.private)
    else:
        transport = Mock(
            side_effect=AssertionError("No credentials or RCON before access check")
        )
        monkeypatch.setattr("omk.owner.admin_maintenance.credential", transport)
        value = run(path, "dj2", "save", confirmed=True)
        assert not value["ok"] and value["effect"] == "none" and value["output"] == ""
        assert value["error"] == "invalid_configuration"
        transport.assert_not_called()
