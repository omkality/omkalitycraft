import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from omk.accounts.drasl import DraslError
from omk.cli import main
from omk.labs.accounts.operator_lab import _cleanup
from omk.owner.admin import (
    AdminError,
    create_invite,
    load_operator_config,
    operator_login,
    server_diagnostics,
)
from tests.fixtures.unit.owner.operator_commands import config

__all__ = ["config"]


def test_playtime_cli_uses_owner_binding_without_drasl_login(
    tmp_path, monkeypatch, capsys
):
    settings, path = config(tmp_path)
    player = "7d714b9e-996b-4d72-ab5a-f3e38b3ffb26"
    query = Mock(return_value={"ok": True, "ticks": 72007})
    monkeypatch.setattr("omk.game.player_time.saved_playtime", query)
    login = Mock(side_effect=AssertionError("must not read management credentials"))
    monkeypatch.setattr("omk.owner.admin._credential", login)
    assert main(["admin", "--config", str(path), "playtime", "dj2", player]) == 0
    query.assert_called_once_with(settings, "dj2", player)
    login.assert_not_called()
    assert json.loads(capsys.readouterr().out) == {"ok": True, "ticks": 72007}
    events = (settings.private / "audit.jsonl").read_text()
    assert '"operation": "playtime"' in events and player not in events


def test_server_export_requires_explicit_operator_allowlist_and_is_read_only(tmp_path):
    settings, _ = config(tmp_path)
    logs = tmp_path / "server/logs"
    logs.mkdir(parents=True)
    source = logs / "latest.log"
    source.write_text("server exception fixture\n")
    before = source.stat().st_mtime_ns
    result = server_diagnostics(settings, "dj2")
    assert Path(result["archive"]).is_relative_to(settings.private)
    assert source.stat().st_mtime_ns == before
    with pytest.raises(AdminError, match="allowlist"):
        server_diagnostics(settings, "gtnh")


def test_non_admin_login_never_saves_management_credentials(tmp_path, monkeypatch):
    settings, _ = config(tmp_path)
    monkeypatch.setattr(
        "omk.owner.admin.DraslClient.login",
        lambda *a: {"user": {"isAdmin": False}, "apiToken": "not-an-admin-token"},
    )
    with pytest.raises(AdminError, match="not an administrator"):
        operator_login(settings, "player", "not-saved-password")
    assert not settings.auth_file.exists()


@pytest.mark.parametrize("show_code", [False, True])
def test_cli_only_includes_invitation_code_when_requested(
    tmp_path, monkeypatch, capsys, show_code
):
    settings, path = config(tmp_path)
    login = {"user": {"isAdmin": True}, "apiToken": "fixture_admin_token_1234"}
    monkeypatch.setattr("omk.owner.admin.DraslClient.login", lambda *a: login)
    monkeypatch.setattr(
        "omk.owner.admin.getpass.getpass", lambda *a: "fixture-operator-password"
    )
    assert main(["admin", "--config", str(path), "login", "--username", "admin"]) == 0
    login_output = capsys.readouterr().out
    request = Mock(
        return_value={
            "code": "secret-invite-code",
            "url": "do-not-echo",
            "createdAt": "today",
        }
    )
    monkeypatch.setattr("omk.owner.admin.DraslClient.request", request)
    command = ["admin", "--config", str(path), "access", "invite"]
    if show_code:
        command.append("--show-code")
    assert main(command) == 0
    output = capsys.readouterr().out
    audit = (settings.private / "audit.jsonl").read_text()
    expected_code = "secret-invite-code" if show_code else None
    assert json.loads(output).get("code") == expected_code
    assert ("secret-invite-code" in output) is show_code
    assert "secret-invite-code" not in audit
    for secret in [login["apiToken"], "fixture-operator-password"]:
        assert (
            secret not in login_output and secret not in output and secret not in audit
        )
    assert (
        "secret-invite-code"
        in next((settings.private / "invitations").glob("invite-*.json")).read_text()
    )
    assert "fixture-operator-password" not in settings.auth_file.read_text()


@pytest.mark.parametrize("error", [OSError("disk full"), AdminError("unsafe ACL")])
def test_failed_invitation_save_revokes_only_the_new_invitation(
    tmp_path, monkeypatch, error
):
    settings, _ = config(tmp_path)
    monkeypatch.setattr(
        "omk.owner.admin._credential", lambda _: "fixture_admin_token_1234"
    )
    request = Mock(return_value={"code": "new-unused-invite"})
    monkeypatch.setattr("omk.owner.admin.DraslClient.request", request)
    monkeypatch.setattr(
        "omk.owner.admin._write_private", Mock(side_effect=error)
    )
    with pytest.raises(AdminError, match="revoked"):
        create_invite(settings)
    assert request.call_args.args[:2] == (
        "DELETE",
        "/drasl/api/v3/invites/new-unused-invite",
    )


def test_operator_private_paths_cannot_escape_config_folder(tmp_path):
    private = tmp_path / ".omk-admin"
    private.mkdir(mode=0o700)
    path = private / "operator.toml"
    path.write_text('schema=1\n[auth]\nsession_file="../outside.json"\n')
    with pytest.raises(AdminError, match="inside"):
        load_operator_config(path)
    assert not (tmp_path / "outside.json").exists()


def test_operator_errors_do_not_echo_configuration_or_response_contents(
    tmp_path, monkeypatch, capsys
):
    _, path = config(tmp_path)
    monkeypatch.setattr("omk.owner.admin.getpass.getpass", lambda *a: "password-value")
    monkeypatch.setattr(
        "omk.owner.admin.DraslClient.login",
        Mock(side_effect=ValueError("secret response content")),
    )
    assert main(["admin", "--config", str(path), "login", "--username", "admin"]) == 1
    output = capsys.readouterr().out
    assert "secret response content" not in output and "password-value" not in output
    assert json.loads(output)["error_type"] == "ValueError"


def test_operator_lab_always_cleans_owned_auth_after_api_cleanup_failure(monkeypatch):
    monkeypatch.setattr(
        "omk.labs.accounts.operator_lab._stop_api",
        Mock(side_effect=OSError("stop failed")),
    )
    stream = Mock()
    stream.close.side_effect = OSError("collector failed")
    run = Mock(return_value=Mock(returncode=0))
    monkeypatch.setattr("omk.labs.accounts.operator_lab.subprocess.run", run)
    assert not _cleanup(
        None, stream, ["docker", "compose", "--project-name", "owned-test"]
    )
    assert run.called


@pytest.mark.parametrize("error", [DraslError(404), OSError("private network details")])
def test_failed_revoke_never_marks_file_or_reports_success(
    tmp_path, monkeypatch, capsys, error
):
    settings, path = config(tmp_path)
    file = settings.private / "invitation.json"
    value = {
        "schema": 1,
        "origin": settings.auth_origin,
        "code": "private-fixture-code",
    }
    file.write_text(json.dumps(value), encoding="utf-8")
    file.chmod(0o600)
    before = file.read_bytes()
    monkeypatch.setattr("omk.owner.admin._credential", lambda _: "fixture-admin-token")
    monkeypatch.setattr("omk.owner.admin.DraslClient.request", Mock(side_effect=error))
    assert (
        main(
            [
                "admin",
                "--config",
                str(path),
                "access",
                "revoke-invite",
                "--invitation-file",
                str(file),
            ]
        )
        == 1
    )
    output = capsys.readouterr().out
    result = json.loads(output)
    assert not result["ok"] and file.read_bytes() == before
    assert (
        "private-fixture-code" not in output and "private network details" not in output
    )
    assert "fixture-admin-token" not in (settings.private / "audit.jsonl").read_text()
    if isinstance(error, DraslError):
        assert "already used, revoked or not found" in result["error"]
        assert "no account was blocked" in result["error"]
