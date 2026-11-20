import os
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from omk.accounts.drasl import DraslClient, DraslError
from omk.game import project_moderation as moderation
from tests.fixtures.unit.game.project_moderation import UUID, project

__all__ = ["UUID", "project"]

OTHER = "32345678-1234-4234-8234-123456789abc"


def test_one_record_covers_player_absent_from_other_server_and_unban(project):
    result = moderation.run(
        project.path,
        "ban",
        "firstjoin",
        duration="10m",
        reason="Причина",
        confirmed=True,
    )
    assert (result["ok"], result["expires_at"], result["unreachable"]) == (
        True,
        1_800_000_600,
        [],
    )
    first_store, entries = moderation._read(project.root)
    assert entries == {
        ("ban", UUID): moderation.Restriction(
            "ban", UUID, "FirstJoin", 1_800_000_000, 1_800_000_600, "Причина"
        )
    }
    assert moderation.initialize(project.root) == (first_store, False)

    project.online.clear()
    assert moderation.run(project.path, "unban", "FirstJoin")["ok"]
    assert moderation._read(project.root) == (first_store, {})


def test_mute_keeps_longer_expiry_and_does_not_need_stopped_server(project):
    project.online.pop("beta")
    first = moderation.run(project.path, "mute", "FirstJoin", duration="1h")
    second = moderation.run(project.path, "mute", "FirstJoin", duration="30m")
    assert first["ok"] and second["ok"]
    assert second["expires_at"] == first["expires_at"]
    assert first["unreachable"] == ["beta"]


@pytest.mark.parametrize("failure", ["confirmation", "realm", "ambiguous"])
def test_wrong_scope_identity_or_confirmation_refuses_before_write(project, failure):
    if failure == "realm":
        project.proof["beta"] = OTHER
    elif failure == "ambiguous":
        project.online["beta"] = {OTHER: "FirstJoin"}
    result = moderation.run(
        project.path,
        "ban",
        "FirstJoin",
        duration="10m",
        confirmed=failure != "confirmation",
    )
    assert not result["ok"] and result["effect"] == "none"
    assert moderation._read(project.root)[1] == {}


def test_registered_profile_can_be_banned_before_any_first_join(project, monkeypatch):
    project.online.clear()
    with project.path.open("a", encoding="utf-8") as config:
        config.write('\n[auth]\norigin="http://127.0.0.1:25586"\n')
    profile = Mock(return_value=(UUID, "FirstJoin"))
    monkeypatch.setattr(
        moderation, "_client", lambda _config: SimpleNamespace(game_profile=profile)
    )
    result = moderation.run(
        project.path, "ban", "firstjoin", duration="10m", confirmed=True
    )
    profile.assert_called_once_with("firstjoin")
    assert result["ok"] and sorted(result["unreachable"]) == ["alpha", "beta"]
    assert ("ban", UUID) in moderation._read(project.root)[1]


def test_drasl_uuid_wins_and_conflicting_online_identity_refuses(project, monkeypatch):
    with project.path.open("a", encoding="utf-8") as config:
        config.write('\n[auth]\norigin="http://127.0.0.1:25586"\n')
    profile = Mock(return_value=(OTHER, "FirstJoin"))
    monkeypatch.setattr(
        moderation, "_client", lambda _config: SimpleNamespace(game_profile=profile)
    )
    assert (
        moderation.run(project.path, "mute", "FirstJoin", duration="1m")["error"]
        == "inconsistent_servers"
    )
    profile.return_value = None
    assert (
        moderation.run(project.path, "mute", "FirstJoin", duration="1m")["error"]
        == "profile_not_found"
    )
    assert moderation._read(project.root)[1] == {}


def test_invalid_store_and_concurrent_writer_cannot_be_overwritten(project):
    with moderation._lock(project.root):
        assert (
            moderation.run(project.path, "mute", "FirstJoin", duration="1h")["effect"]
            == "none"
        )
    file = project.root / moderation.DIRECTORY / moderation.STATE
    file.write_bytes(b"bad data\n")
    assert (
        moderation.run(project.path, "mute", "FirstJoin", duration="1h")["effect"]
        == "none"
    )
    assert file.read_bytes() == b"bad data\n"
    if os.name != "nt":
        assert file.stat().st_mode & 0o077 == 0


def test_drasl_identity_lookup_validates_profile_and_endpoint(monkeypatch):
    client = DraslClient("http://127.0.0.1:25586")
    request = Mock(return_value={"id": UUID.replace("-", ""), "name": "FirstJoin"})
    monkeypatch.setattr(client, "request", request)
    assert client.game_profile("firstjoin") == (UUID, "FirstJoin")
    request.assert_called_once_with(
        "GET", "/account/users/profiles/minecraft/firstjoin"
    )
    request.return_value["name"] = "Other"
    with pytest.raises(DraslError, match="502"):
        client.game_profile("firstjoin")
    request.side_effect = DraslError(404)
    assert client.game_profile("firstjoin") is None
