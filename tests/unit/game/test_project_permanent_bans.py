from omk.game import (
    project_moderation as moderation,
    project_permanent_bans as permanent,
)
from tests.fixtures.unit.game.project_moderation import UUID, project
from tests.fixtures.unit.game.project_permanent_bans import ACCOUNT, drasl

__all__ = ["drasl", "project"]


def _ban(drasl, *, confirmed=True):
    return moderation.run(
        drasl.project.path,
        "ban",
        "firstjoin",
        confirmed=confirmed,
        duration="perm",
        reason="Доступ закрыт",
    )


def test_permanent_ban_locks_and_revokes_offline_account_and_unbans(drasl):
    drasl.project.online.clear()
    drasl.fails.add("beta")
    old = moderation._read(drasl.project.root)
    result = _ban(drasl)
    assert result["ok"] and result["expires_at"] is None
    assert result["unreachable"] == ["beta"] and drasl.drained == ["alpha"]
    assert drasl.user["isLocked"]
    assert drasl.calls == [
        {
            "isLocked": True,
            "resetApiToken": True,
            "resetMinecraftToken": True,
        }
    ]
    assert moderation._read(drasl.project.root) == old
    active, recent = moderation.player_moderation(drasl.project.root, UUID)
    assert active[0].expires is None and active[0].reason == "Доступ закрыт"
    assert [(event.kind, event.expires) for event in recent] == [("ban", None)]
    assert _ban(drasl)["ok"] and len(drasl.calls) == 1
    assert moderation.run(drasl.project.path, "unban", "FirstJoin")["ok"]
    assert not drasl.user["isLocked"] and drasl.calls[-1] == {"isLocked": False}
    active, recent = moderation.player_moderation(drasl.project.root, UUID)
    assert not active
    assert [event.kind for event in recent] == ["unban", "ban"]


def test_own_operator_or_foreign_lock_is_preserved_and_confirmation_required(drasl):
    assert _ban(drasl, confirmed=False)["error"] == "invalid_request"
    drasl.caller = ACCOUNT
    assert _ban(drasl)["error"] == "operator_account"
    drasl.caller = "32345678-1234-4234-8234-123456789abc"
    drasl.user["isLocked"] = True
    assert _ban(drasl)["error"] == "account_locked"
    assert (
        moderation.run(drasl.project.path, "unban", "FirstJoin")["error"]
        == "not_banned"
    )
    assert not drasl.calls and drasl.user["isLocked"]


def test_lost_drasl_reply_keeps_ownership_and_only_records_confirmed_changes(drasl):
    drasl.lose_reply = True
    outcome = _ban(drasl)
    assert not outcome["ok"] and outcome["effect"] == "unknown"
    _, staged = permanent.load(drasl.project.root)
    assert not staged.entries
    assert next(iter(staged.bans.values())).stage == "locking"
    drasl.lose_reply = False
    assert _ban(drasl)["ok"]
    _, history = moderation.player_moderation(drasl.project.root, UUID)
    assert len(history) == 1 and history[0].kind == "ban"


def test_perm_is_for_bans_and_keeps_existing_temporary_restrictions(drasl):
    assert (
        moderation.run(drasl.project.path, "mute", "FirstJoin", duration="perm")[
            "error"
        ]
        == "invalid_request"
    )
    assert moderation.run(
        drasl.project.path,
        "ban",
        "FirstJoin",
        duration="10m",
        confirmed=True,
    )["ok"]
    assert _ban(drasl)["error"] == "already_banned"
    assert not drasl.calls
