"""List active project moderation for the owner's restrictions panel."""

import time
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from omk.game import project_moderation as moderation
from omk.game.project_permanent_bans import load
from omk.owner.admin import load_operator_config


class Profile(BaseModel):
    """Summarize active bans and mutes for one profile."""

    model_config = ConfigDict(extra="forbid", strict=True)
    profile: UUID
    player: str = Field(pattern=r"^[A-Za-z0-9_]{1,16}$")
    ban_until: int | None = None
    permanent: bool = False
    lock_pending: bool = False
    mute_until: int | None = None


class Snapshot(BaseModel):
    """Return the private project-wide restriction inventory."""

    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: Literal[1] = 1
    action: Literal["owner.project-restrictions"] = "owner.project-restrictions"
    ok: bool
    profiles: list[Profile] = Field(default_factory=list, max_length=2300)


def run(path):
    """Group current restrictions by profile UUID without querying the game servers."""
    try:
        config = load_operator_config(path)
        with moderation._lock(config.private):
            _, entries = moderation._read(config.private)
            _, permanent = load(config.private)
        now = int(time.time())
        profiles = {}
        for entry in sorted(entries.values(), key=lambda e: e.created, reverse=True):
            if entry.expires is None or entry.expires <= now:
                continue
            if entry.uuid not in profiles:
                profiles[entry.uuid] = Profile(
                    profile=UUID(entry.uuid), player=entry.player
                )
            profile = profiles[entry.uuid]
            if entry.kind == "ban":
                profile.ban_until = entry.expires
            else:
                profile.mute_until = entry.expires
        for uid, ban in permanent.bans.items():
            profile = profiles.setdefault(
                str(uid), Profile(profile=uid, player=ban.player)
            )
            profile.player = ban.player
            profile.permanent = True
            profile.lock_pending = ban.stage != "active"
            profile.ban_until = None
        return Snapshot(
            ok=True,
            profiles=sorted(
                profiles.values(), key=lambda r: (r.player.casefold(), r.profile)
            ),
        ).model_dump(mode="json")
    except OSError, RuntimeError, ValueError:
        return Snapshot(ok=False).model_dump(mode="json")
