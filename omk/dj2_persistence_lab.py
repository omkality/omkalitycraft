"""Mute persistence checks on the owned, disposable DJ2 server only."""

import time
from contextlib import ExitStack

from omk.dj2_commands_lab import FIRST, SECOND, _contains, _response
from omk.forge_player import LabPlayer


def _muted(actor, observer, stage, expect):
    observer.messages.clear()
    actor.messages.clear()
    actor.chat("OmkPersistBlockedChat")
    actor.wait(lambda: _contains(actor, "commands.mute.muted"))
    for command in [
        "/me OmkPersistBlockedAction",
        "/tell " + FIRST + " OmkPersistBlockedPrivate",
    ]:
        _response(actor, command, "commands.mute.muted")
    time.sleep(0.2)
    expect(
        not any(
            _contains(observer, value)
            for value in [
                "OmkPersistBlockedChat",
                "OmkPersistBlockedAction",
                "OmkPersistBlockedPrivate",
            ]
        ),
        "mute_blocks_chat_and_commands_" + stage,
    )


def _unmuted(actor, observer, stage, expect):
    observer.messages.clear()
    actor.chat("OmkPersistAllowedChat")
    observer.wait(lambda: _contains(observer, "OmkPersistAllowedChat"))
    actor.command("/tell " + FIRST + " OmkPersistAllowedPrivate")
    observer.wait(lambda: _contains(observer, "OmkPersistAllowedPrivate"))
    expect(True, "unmuted_chat_and_private_message_work_" + stage)


def prepare_mute_restart(client, session, session2, mods, console, expect):
    console("ranks add " + FIRST + " moderator")
    with LabPlayer(client, session, 25576, mods) as moderator:
        with LabPlayer(client, session2, 25576, mods) as actor:
            _unmuted(actor, moderator, "before_sanction", expect)
            moderator.command("/mute " + SECOND)
            time.sleep(0.3)
            _muted(actor, moderator, "before_disconnect", expect)
        # An orderly disconnect must save the same UUID's persisted mute state.
        with LabPlayer(client, session2, 25576, mods) as actor:
            _muted(actor, moderator, "after_reconnect", expect)
        expect(True, "muted_player_disconnected_before_safe_server_restart")


def verify_mute_restart(client, session, session2, mods, expect):
    with ExitStack() as stack:
        moderator = stack.enter_context(LabPlayer(client, session, 25576, mods))
        actor = stack.enter_context(LabPlayer(client, session2, 25576, mods))
        _muted(actor, moderator, "after_full_server_restart", expect)
        moderator.command("/unmute " + SECOND)
        time.sleep(0.3)
        # Wait for a positive chat delivery rather than infer it from a command.
        _unmuted(actor, moderator, "after_restart_unmute", expect)
        _response(moderator, "/op " + FIRST, "commands.generic.permission")
        expect(True, "moderator_unmute_survives_restart_without_op")
    with (
        LabPlayer(client, session, 25576, mods) as moderator,
        LabPlayer(client, session2, 25576, mods) as actor,
    ):
        _unmuted(actor, moderator, "after_unmuted_reconnect", expect)
