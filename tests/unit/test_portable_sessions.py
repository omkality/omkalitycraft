import json
import os
import stat
from pathlib import Path

import pytest

from launcher.accounts import AccountError, AccountService
from launcher.session import SessionStoreError
from launcher.storage import FileSessionStore
from omk.drasl import DraslError
from omk.lab import skin_fixture
from tests.fakes import FakeDrasl


@pytest.fixture
def account(tmp_path: Path) -> AccountService:
    return AccountService(
        FakeDrasl(), FileSessionStore(tmp_path / "userdata" / "session.json")
    )


def test_registration_password_exists_before_any_network_request(
    account: AccountService,
) -> None:
    registration = account.prepare_registration("test_player", "test-invitation")
    assert len(registration.password) >= 32
    assert registration.password not in repr(registration)
    assert account.client.calls == []
    result = account.register(registration)
    assert result.remembered
    assert ("register_requests_management_token", False) in account.client.calls


def test_portable_file_contains_only_game_session(account: AccountService) -> None:
    registration = account.prepare_registration("test_player", "test-invitation")
    result = account.register(registration)
    data = account.store.path.read_text(encoding="utf-8")
    assert registration.password not in data
    assert account.client.management_token not in data
    assert set(json.loads(data)) == {
        "schema",
        "origin",
        "username",
        "player_uuid",
        "player_name",
        "access_token",
        "client_token",
    }
    assert result.session.access_token not in repr(result)
    if os.name != "nt":
        assert stat.S_IMODE(account.store.path.stat().st_mode) == 0o600


def test_restore_refreshes_without_password(account: AccountService) -> None:
    original = account.login("test_player", "test-password").session
    account.client.calls.clear()
    restored = AccountService(account.client, account.store).restore()
    assert restored.session.player_uuid == original.player_uuid
    assert restored.session.access_token != original.access_token
    assert account.client.calls == [("refresh", None)]


def test_network_failure_preserves_session_file(account: AccountService) -> None:
    account.login("test_player", "test-password")
    before = account.store.path.read_bytes()
    account.client.refresh_error = TimeoutError("test")
    with pytest.raises(TimeoutError):
        account.restore()
    assert account.store.path.read_bytes() == before


@pytest.mark.parametrize("status", [400, 401, 403])
def test_revoked_session_is_forgotten(account: AccountService, status: int) -> None:
    account.login("test_player", "test-password")
    account.client.refresh_error = DraslError(status)
    assert account.restore() is None
    assert not account.store.path.exists()
    assert account.current is None


def test_server_failure_does_not_log_player_out(account: AccountService) -> None:
    account.login("test_player", "test-password")
    account.client.refresh_error = DraslError(503)
    with pytest.raises(DraslError):
        account.restore()
    assert account.store.path.exists()


def test_another_origin_never_receives_saved_tokens(account: AccountService) -> None:
    account.login("test_player", "test-password")
    other = FakeDrasl()
    other.base_url = "https://another-auth.example"
    with pytest.raises(AccountError):
        AccountService(other, account.store).restore()
    assert other.calls == []


def test_corrupt_file_error_does_not_echo_content(tmp_path: Path) -> None:
    path = tmp_path / "session.json"
    path.write_text("secret-invalid-json", encoding="utf-8")
    with pytest.raises(SessionStoreError) as error:
        FileSessionStore(path).load()
    assert "secret-invalid-json" not in str(error.value)


def test_failed_atomic_replace_keeps_previous_file(
    account: AccountService, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = account.login("test_player", "test-password")
    before = account.store.path.read_bytes()

    def deny_replace(*args: object) -> None:
        raise PermissionError("test")

    monkeypatch.setattr(os, "replace", deny_replace)
    with pytest.raises(SessionStoreError):
        account.store.save(result.session)
    assert account.store.path.read_bytes() == before
    assert list(account.store.path.parent.glob(".session-*.tmp")) == []


def test_readonly_storage_keeps_only_current_in_memory_session(
    account: AccountService, monkeypatch: pytest.MonkeyPatch
) -> None:
    def deny_save(*args: object) -> None:
        raise SessionStoreError("test")

    monkeypatch.setattr(account.store, "save", deny_save)
    result = account.login("test_player", "test-password")
    assert not result.remembered
    assert account.current == result.session
    assert not account.store.path.exists()


def test_skin_uses_game_token_and_rejects_non_skin_data(
    account: AccountService,
) -> None:
    account.login("test_player", "test-password")
    with pytest.raises(AccountError):
        account.upload_skin(b"not-a-png", "classic")
    account.upload_skin(skin_fixture(), "slim")
    assert ("upload_skin", "slim") in account.client.calls


def test_management_token_is_not_persisted_after_password_change(
    account: AccountService,
) -> None:
    account.login("test_player", "old-test-password")
    account.change_password("old-test-password", "new-test-password")
    assert account.client.management_token not in account.store.path.read_text(
        encoding="utf-8"
    )
    assert (
        "update_user",
        {"password", "resetApiToken", "resetMinecraftToken"},
    ) in account.client.calls


def test_forget_device_does_not_claim_remote_revocation(
    account: AccountService,
) -> None:
    account.login("test_player", "test-password")
    account.client.calls.clear()
    account.forget()
    assert account.client.calls == []
    assert not account.store.path.exists()


def test_all_sessions_revocation_is_separate_from_forgetting(
    account: AccountService,
) -> None:
    account.login("test_player", "test-password")
    account.revoke_all("test-password")
    assert ("signout", "test_player") in account.client.calls
    assert (
        "update_user",
        {"resetApiToken", "resetMinecraftToken"},
    ) in account.client.calls
    assert account.current is None
    assert not account.store.path.exists()
