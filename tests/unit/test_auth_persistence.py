import hashlib
import io
import json
import sqlite3
import tarfile
import tomllib
from unittest.mock import Mock

import pytest

from omk.auth_config import configure, render_config
from omk.auth_restore_quarantine import quarantine
from omk.auth_state_archive import restore, snapshot


def state(root):
    root.mkdir()
    with sqlite3.connect(root / "drasl.db") as db:
        db.execute("CREATE TABLE example (value TEXT)")
        db.execute("INSERT INTO example VALUES ('retained')")
    (root / "key.pkcs8").write_bytes(b"unit-fixture-private-key")
    (root / "skin").mkdir()
    (root / "skin" / "player.png").write_bytes(b"unit-fixture-texture")


def test_offline_snapshot_restores_database_textures_and_key_to_new_target(tmp_path):
    original, target = tmp_path / "original", tmp_path / "restored"
    state(original)
    target.mkdir()
    archive = tmp_path / "state.tar"
    result = snapshot(original, archive)
    assert result["sqlite_integrity"]
    assert restore(target, archive)["quarantine_required"]
    with sqlite3.connect(target / "drasl.db") as db:
        assert db.execute("SELECT value FROM example").fetchall() == [("retained",)]
    assert (target / "key.pkcs8").read_bytes() == (original / "key.pkcs8").read_bytes()
    assert (target / "skin/player.png").read_bytes() == b"unit-fixture-texture"
    with pytest.raises(ValueError, match="empty"):
        restore(target, archive)
    with pytest.raises(ValueError, match="exists"):
        snapshot(original, archive)


def test_corrupt_snapshot_does_not_write_to_restore_target(tmp_path):
    source, target = tmp_path / "original", tmp_path / "restored"
    state(source)
    target.mkdir()
    archive = tmp_path / "state.tar"
    snapshot(source, archive)
    with archive.open("r+b") as file:
        file.seek(2000)
        file.write(b"corrupt")
    with pytest.raises(ValueError, match="digest"):
        restore(target, archive)
    assert list(target.iterdir()) == []


@pytest.mark.parametrize(
    "kind", ["traversal", "absolute", "symlink", "hardlink", "duplicate", "backslash"]
)
def test_unsafe_members_rejected_even_with_matching_archive_digest(tmp_path, kind):
    archive = tmp_path / "state.tar"
    with tarfile.open(archive, "w") as tar:
        item = tarfile.TarInfo(
            {
                "traversal": "../escape",
                "absolute": "/escape",
                "backslash": "dir\\escape",
            }.get(kind, "entry")
        )
        item.size = 3
        if kind in {"symlink", "hardlink"}:
            item.type = tarfile.SYMTYPE if kind == "symlink" else tarfile.LNKTYPE
            item.linkname = "../escape"
        tar.addfile(item, io.BytesIO(b"bad"))
        if kind == "duplicate":
            tar.addfile(item, io.BytesIO(b"bad"))
    archive.with_suffix(".json").write_text(
        json.dumps(
            {
                "schema": 1,
                "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
                "files": {},
            }
        )
    )
    target = tmp_path / "target"
    target.mkdir()
    with pytest.raises(ValueError, match="Unsafe"):
        restore(target, archive)
    assert list(target.iterdir()) == []


def test_database_integrity_failure_never_publishes_snapshot(tmp_path):
    source = tmp_path / "source"
    state(source)
    (source / "drasl.db").write_bytes(b"not a SQLite database")
    archive = tmp_path / "state.tar"
    with pytest.raises(sqlite3.DatabaseError):
        snapshot(source, archive)
    assert not archive.exists()


@pytest.mark.parametrize(
    "env",
    [
        {"OMK_AUTH_URL": "http://example.org"},
        {"OMK_AUTH_URL": "https://owner:secret@example.org"},
        {"OMK_AUTH_ADMIN": "bad admin"},
        {"OMK_AUTH_INTERNAL_PORT": "80"},
        {"OMK_AUTH_TOKEN_EXPIRE_SECONDS": "0"},
        {"OMK_AUTH_TOKEN_STALE_SECONDS": "2592000"},
    ],
)
def test_invalid_auth_environment_is_rejected(env):
    with pytest.raises(ValueError):
        render_config(env)


def test_generated_config_has_expiry_invites_and_no_overwrite(tmp_path, monkeypatch):
    monkeypatch.setenv("OMK_AUTH_URL", "https://auth.example.org")
    monkeypatch.setenv("OMK_AUTH_INTERNAL_PORT", "25443")
    output = tmp_path / "auth.toml"
    configure(output)
    doc = tomllib.loads(output.read_text())
    assert doc["BaseURL"] == "https://auth.example.org"
    assert doc["ListenAddress"] == "0.0.0.0:25443"
    assert doc["TokenExpireSec"] == 2592000
    assert doc["StateDirectory"] == "/var/lib/drasl"
    assert doc["RegistrationUsernamePassword"]["CreateNewPlayer"]["RequireInvite"]
    with pytest.raises(FileExistsError):
        configure(output)


def test_quarantine_rotates_owner_last_and_keeps_other_accounts_locked():
    client = Mock()
    client.user.return_value = {
        "uuid": "owner",
        "username": "owner",
        "isAdmin": True,
        "isLocked": False,
    }
    client.login.return_value = {"apiToken": "new-owner-token"}
    client.request.side_effect = [
        {},
        [{"uuid": "owner"}, {"uuid": "player"}],
        {"isLocked": True},
        [{"code": "stale-invite"}],
        None,
    ]
    assert (
        quarantine(client, "old-owner-token", "new-owner-password")[
            "credentials_rotated"
        ]
        == 2
    )
    calls = client.request.call_args_list
    assert calls[2].args[2]["isLocked"] is True
    assert calls[2].args[2]["resetMinecraftToken"] is True
    assert calls[4].args[0] == "DELETE"
    client.update_user.assert_called_once_with(
        "old-owner-token",
        {
            "password": "new-owner-password",
            "resetApiToken": True,
            "resetMinecraftToken": True,
        },
    )


def test_quarantine_failure_does_not_rotate_owner_or_claim_success():
    client = Mock()
    client.user.return_value = {"uuid": "owner", "isAdmin": True, "isLocked": False}
    client.request.side_effect = [
        {},
        [{"uuid": "owner"}, {"uuid": "player"}],
        {"isLocked": False},
    ]
    with pytest.raises(ValueError, match="lock"):
        quarantine(client, "old-token", "new-password")
    client.update_user.assert_not_called()
