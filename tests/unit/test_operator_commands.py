import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from omk.admin import (
    AdminError,
    create_invite,
    load_operator_config,
    operator_login,
    server_diagnostics,
)
from omk.cli import main
from omk.operator_lab import _cleanup


def config(tmp_path):
    private = tmp_path / ".omk-admin"
    private.mkdir(mode=0o700)
    path = private / "operator.toml"
    path.write_text(
        'schema=1\n[auth]\norigin="http://127.0.0.1:1"\n[servers.dj2]\nroot="../server"\n'
    )
    return load_operator_config(path), path


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
        "omk.admin.DraslClient.login",
        lambda *a: {"user": {"isAdmin": False}, "apiToken": "not-an-admin-token"},
    )
    with pytest.raises(AdminError, match="not an administrator"):
        operator_login(settings, "player", "not-saved-password")
    assert not settings.auth_file.exists()


def test_cli_outputs_only_private_invitation_path_not_code_token_or_password(
    tmp_path, monkeypatch, capsys
):
    settings, path = config(tmp_path)
    login = {"user": {"isAdmin": True}, "apiToken": "fixture_admin_token_1234"}
    monkeypatch.setattr("omk.admin.DraslClient.login", lambda *a: login)
    monkeypatch.setattr(
        "omk.admin.getpass.getpass", lambda *a: "fixture-operator-password"
    )
    assert main(["admin", "--config", str(path), "login", "--username", "admin"]) == 0
    request = Mock(
        return_value={
            "code": "secret-invite-code",
            "url": "do-not-echo",
            "createdAt": "today",
        }
    )
    monkeypatch.setattr("omk.admin.DraslClient.request", request)
    assert main(["admin", "--config", str(path), "access", "invite"]) == 0
    output = capsys.readouterr().out
    audit = (settings.private / "audit.jsonl").read_text()
    for secret in [
        login["apiToken"],
        "fixture-operator-password",
        "secret-invite-code",
    ]:
        assert secret not in output and secret not in audit
    assert (
        "secret-invite-code"
        in next((settings.private / "invitations").glob("invite-*.json")).read_text()
    )
    assert "fixture-operator-password" not in settings.auth_file.read_text()


def test_failed_invitation_save_revokes_only_the_new_invitation(tmp_path, monkeypatch):
    settings, _ = config(tmp_path)
    monkeypatch.setattr("omk.admin._credential", lambda _: "fixture_admin_token_1234")
    request = Mock(return_value={"code": "new-unused-invite"})
    monkeypatch.setattr("omk.admin.DraslClient.request", request)
    monkeypatch.setattr(
        "omk.admin._write_private", Mock(side_effect=OSError("disk full"))
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
    monkeypatch.setattr("omk.admin.getpass.getpass", lambda *a: "password-value")
    monkeypatch.setattr(
        "omk.admin.DraslClient.login",
        Mock(side_effect=ValueError("secret response content")),
    )
    assert main(["admin", "--config", str(path), "login", "--username", "admin"]) == 1
    output = capsys.readouterr().out
    assert "secret response content" not in output and "password-value" not in output
    assert json.loads(output)["error_type"] == "ValueError"


def test_operator_lab_always_cleans_owned_auth_after_api_cleanup_failure(monkeypatch):
    monkeypatch.setattr(
        "omk.operator_lab._stop_api", Mock(side_effect=OSError("stop failed"))
    )
    stream = Mock()
    stream.close.side_effect = OSError("collector failed")
    run = Mock(return_value=Mock(returncode=0))
    monkeypatch.setattr("omk.operator_lab.subprocess.run", run)
    assert not _cleanup(
        None, stream, ["docker", "compose", "--project-name", "owned-test"]
    )
    assert run.called
