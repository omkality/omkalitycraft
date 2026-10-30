"""Real commands on the disposable DJ2 server; never targets a deployed world.

Protocol actors exercise server logic, not rendering, physics or mod compatibility.
Lab-only shortened timers and back permissions are not a production policy.
"""

import json
import time
from contextlib import ExitStack

from omk.forge_player import LabPlayer

FIRST = "omk_game_test"
SECOND = "omk_other_test"
ORIGIN = (128.5, 241.0, 128.5)
HOME = (8.5, 241.0, 8.5)
WARP = (40.5, 241.0, 40.5)
SPAWN = (24.5, 241.0, 24.5)


def _contains(player, key):
    return any(key in json.dumps(message) for message in tuple(player.messages))


def _response(player, command, key):
    player.messages.clear()
    player.command(command)
    try:
        player.wait(lambda: _contains(player, key))
    except RuntimeError as error:
        raise RuntimeError(
            "No expected response for "
            + command
            + "; "
            + str(error)
            + "; received "
            + json.dumps(list(player.messages))[:1800]
        ) from None


def _near(player, position):
    return player.position is not None and all(
        abs(player.position[i] - position[i]) < 1 for i in range(3)
    )


def _place(player, name, position, console):
    console("tp " + name + " " + " ".join(map(str, position)))
    player.wait(lambda: _near(player, position))


def _hold(player, position, duration):
    deadline = time.monotonic() + duration
    while time.monotonic() < deadline:
        player.check()
        if not _near(player, position):
            raise RuntimeError("Unexpected early teleport")
        time.sleep(0.05)


def _begin(player, command):
    started = time.monotonic()
    _response(player, command, "stand_still")
    return started


def _finish(player, target, started, label, expect, origin=ORIGIN):
    _hold(player, origin, 1.1)
    player.wait(lambda: _near(player, target), timeout=10)
    expect(time.monotonic() - started >= 2.0, label)


def _cancel_movement(first, console, expect):
    _place(first, FIRST, ORIGIN, console)
    _begin(first, "/home one")
    moved = (130.5, 241.0, 128.5)
    first.move(*moved)
    time.sleep(0.2)
    # Server echo confirms the received movement, not the actor's prediction.
    console("tp " + FIRST + " " + FIRST)
    first.wait(lambda: _near(first, moved))
    first.wait(lambda: _contains(first, "stand_still_failed"))
    _hold(first, moved, 3.2)
    expect(True, "home_cross_block_movement_cancels_warmup")

    _place(first, FIRST, ORIGIN, console)
    _begin(first, "/home one")
    first.move(128.7, 241.0, 128.5)
    time.sleep(0.2)
    console("tp " + FIRST + " " + FIRST)
    first.wait(lambda: abs(first.position[0] - 128.7) < 0.05)
    first.wait(lambda: _near(first, HOME))
    expect(True, "home_movement_within_same_block_does_not_cancel_stock_ftb")

    _place(first, FIRST, ORIGIN, console)
    _response(first, "/home one", "cant_use_now_cooldown")
    _hold(first, ORIGIN, 0.8)
    expect(True, "successful_home_starts_cooldown")
    # Cooldown is measured after completion, not at request time.
    time.sleep(10)
    console("gamemode 0 " + FIRST)
    first.wait(lambda: first.health is not None)
    hp = first.health
    _begin(first, "/home one")
    console("effect " + FIRST + " minecraft:instant_damage 1 0 true")
    first.wait(lambda: first.health < hp)
    first.wait(lambda: _contains(first, "stand_still_failed"))
    _hold(first, ORIGIN, 3.2)
    expect(True, "home_health_loss_cancels_warmup")
    console("gamemode 1 " + FIRST)
    started = _begin(first, "/home one")
    _finish(first, HOME, started, "cancelled_home_does_not_consume_cooldown", expect)


def _prepare_teleports(first, console):
    console("ranks setp player command.ftbutilities.rtp true")
    for name, point in [(FIRST, HOME), (SECOND, WARP)]:
        console("gamemode 1 " + name)
        console(
            "fill "
            + f"{int(point[0])-3} 240 {int(point[2])-3} "
            + f"{int(point[0])+3} 240 {int(point[2])+3} minecraft:stone"
        )
    console("gamerule naturalRegeneration false")
    console("gamerule doMobSpawning false")
    console("setworldspawn 24 241 24")
    console("setwarp omk_lab 40 241 40 0")
    console("fill 124 240 124 134 240 134 minecraft:stone")
    console("fill 20 240 20 28 240 28 minecraft:stone")
    _place(first, FIRST, HOME, console)
    _response(first, "/sethome one", "ftbutilities.lang.homes.set")
    for group in ["homes", "spawn", "warps", "tpa", "back", "rtp"]:
        console(f"ranks setp player ftbutilities.{group}.warmup 3s")
        console(f"ranks setp player ftbutilities.{group}.cooldown 10s")
    console("ranks setp player ftbutilities.back.home true")
    # Basic smoke used home; ensure its existing 10s cooldown has elapsed.
    time.sleep(10)


def _teleports(first, second, console, expect, report):
    _prepare_teleports(first, console)
    _cancel_movement(first, console, expect)
    for command, target, label in [
        ("/spawn", SPAWN, "spawn"),
        ("/warp omk_lab", WARP, "warp"),
    ]:
        _place(first, FIRST, ORIGIN, console)
        started = _begin(first, command)
        _finish(first, target, started, label + "_warmup_then_real_teleport", expect)
        _place(first, FIRST, ORIGIN, console)
        _response(first, command, "cant_use_now_cooldown")
        _hold(first, ORIGIN, 0.8)
        expect(True, label + "_cooldown_denies_repeat")
    _tpa(first, second, console, expect)
    _back(first, console, expect)
    _rtp(first, console, expect, report)
    _tpa_expiry(first, second, console, expect)


def _tpa(first, second, console, expect):
    _place(first, FIRST, ORIGIN, console)
    _place(second, SECOND, WARP, console)
    _response(first, "/tpa " + SECOND, "tpa.request_sent")
    _response(second, "/tpaccept " + FIRST, "tpa.request_accepted")
    started = time.monotonic()
    _place(second, SECOND, SPAWN, console)
    _finish(
        first, SPAWN, started, "tpa_uses_target_position_at_warmup_completion", expect
    )
    _response(first, "/tpa " + SECOND, "cant_use_now_cooldown")
    expect(_near(second, SPAWN), "tpa_target_stays_in_place_and_requester_has_cooldown")


def _back(first, console, expect):
    # Back to home origin, permitted only by the explicit lab override above.
    _place(first, FIRST, WARP, console)
    started = _begin(first, "/back")
    _finish(
        first, ORIGIN, started, "back_warmup_then_real_teleport", expect, origin=WARP
    )
    first.wait(lambda: _contains(first, "teleporting"))
    _response(first, "/back", "ftbutilities.lang.warps.no_dp")
    expect(True, "back_is_single_use_without_infinite_permission")
    console("ranks setp player ftbutilities.homes.cooldown 0s")
    _begin(first, "/home one")
    first.wait(lambda: _near(first, HOME))
    _response(first, "/back", "cant_use_now_cooldown")
    expect(True, "back_cooldown_denies_repeat_even_with_new_valid_history")
    console("ranks setp player ftbutilities.homes.cooldown 10s")


def _rtp(first, console, expect, report):
    _place(first, FIRST, ORIGIN, console)
    started = _begin(first, "/rtp")
    _hold(first, ORIGIN, 1.1)
    first.wait(lambda: not _near(first, ORIGIN), timeout=40)
    distance = (first.position[0] ** 2 + first.position[2] ** 2) ** 0.5
    expect(
        6 <= distance <= 14 and time.monotonic() - started >= 2,
        "rtp_warmup_and_destination_in_lab_range",
    )
    report["rtp_destination"] = list(first.position[:3])
    _response(first, "/rtp", "cant_use_now_cooldown")
    expect(True, "rtp_cooldown_denies_repeat")


def _tpa_expiry(first, second, console, expect):
    time.sleep(10)
    _place(first, FIRST, ORIGIN, console)
    _response(first, "/tpa " + FIRST, "tpa.cant_request")
    _response(first, "/tpa " + SECOND, "tpa.request_sent")
    _response(first, "/tpa " + SECOND, "tpa.cant_request")
    _hold(first, ORIGIN, 31.5)
    _response(second, "/tpaccept " + FIRST, "tpa.no_request")
    expect(True, "tpa_rejects_self_duplicate_and_expired_30_second_request")


def _rtp_limits(first, console, expect):
    console("worldborder center 0 0")
    console("worldborder set 4")
    _place(first, FIRST, HOME, console)
    _begin(first, "/rtp")
    first.wait(lambda: _contains(first, "ftbutilities.lang.rtp.fail"))
    _hold(first, HOME, 0.5)
    _response(first, "/rtp", "cant_use_now_cooldown")
    expect(True, "rtp_respects_too_small_border_but_failed_search_consumes_cooldown")
    console("worldborder set 60000000")
    console("setworldspawn 0 241 0")
    # The 8..12 test annulus fits in loaded chunks. Modded block callbacks make
    # even vanilla fill expensive, so keep this fixture to 1089 solid blocks.
    output = console("fill -16 245 -16 16 245 16 minecraft:magma")
    if "1089 blocks filled" not in output:
        raise RuntimeError("Magma fixture was not loaded: " + output[-600:])
    console("ranks setp player ftbutilities.rtp.cooldown 0s")
    _place(first, FIRST, ORIGIN, console)
    _begin(first, "/rtp")
    first.wait(lambda: not _near(first, ORIGIN), timeout=40)
    x, y, z = first.position[:3]
    found = console(f"testforblock {int(x // 1)} 245 {int(z // 1)} minecraft:magma")
    expect(
        247 <= y <= 248 and "Successfully found" in found,
        "stock_ftb_rtp_accepts_damage_surface_magma_not_safe_to_release",
    )
    console("ranks setp player ftbutilities.rtp.cooldown 10s")
    console("ranks setp player command.ftbutilities.rtp false")
    _response(first, "/rtp", "commands.generic.permission")
    expect(True, "unsafe_stock_rtp_can_be_disabled_with_exact_permission_node")


def _moderation(first, second, console, expect, guarded=False):
    console("ranks add " + FIRST + " moderator")
    _response(first, "/sethome four", "ftbutilities.lang.homes.limit")
    expect(True, "moderator_inherits_three_home_limit_without_op")
    for command in [
        "/op " + FIRST,
        "/fly",
        "/god",
        "/gamemode 1",
        "/give " + FIRST + " diamond",
        "/setwarp denied",
        "/home list " + SECOND,
        "/ranks add " + FIRST + " admin",
        "/ranks setp moderator command.op true",
        "/nbtedit player " + SECOND,
        "/ban-ip 127.0.0.1",
        "/worldborder set 100",
        "/chunks unclaim_everything",
        "/inv view " + SECOND,
        "/reload",
    ]:
        _response(first, command, "commands.generic.permission")
    expect(True, "moderator_denied_gameplay_advantages_and_permission_escalation")
    _mute_checks(first, second, console, expect, guarded)
    first.command("/kick " + SECOND + " omk_lab_kick")
    first.wait(lambda: second.error is not None)
    expect("omk_lab_kick" in second.error, "moderator_kick_without_op")


def _mute_checks(first, second, console, expect, guarded):
    second.messages.clear()
    first.messages.clear()
    second.chat("OmkLabChatBeforeMute")
    first.wait(lambda: _contains(first, "OmkLabChatBeforeMute"))
    first.command("/mute " + SECOND)
    time.sleep(0.3)
    second.messages.clear()
    second.chat("OmkLabChatBlocked")
    second.wait(lambda: _contains(second, "commands.mute.muted"))
    time.sleep(0.4)
    expect(
        not _contains(first, "OmkLabChatBlocked"),
        "moderator_mute_blocks_public_chat",
    )
    # Characterize the stock mod, rather than call its partial mute complete.
    # Vanilla command messages do not pass through Forge ServerChatEvent.
    for command, marker in [
        ("/me OmkLabMutedAction", "OmkLabMutedAction"),
        ("/tell " + FIRST + " OmkLabMutedTell", "OmkLabMutedTell"),
        ("/msg " + FIRST + " OmkLabMutedPrivate", "OmkLabMutedPrivate"),
        ("/w " + FIRST + " OmkLabMutedWhisper", "OmkLabMutedWhisper"),
    ]:
        first.messages.clear()
        if guarded:
            _response(second, command, "commands.mute.muted")
            time.sleep(0.2)
            expect(
                not _contains(first, marker),
                "muted_command_blocked_" + command.split()[0][1:],
            )
        else:
            second.command(command)
            first.wait(lambda key=marker: _contains(first, key))
    if not guarded:
        expect(True, "stock_ftb_mute_leaves_vanilla_me_and_private_message_bypass")
    else:
        _response(second, "/sethome mutecheck", "ftbutilities.lang.homes.set")
        expect(True, "muted_player_keeps_non_chat_home_commands")
    first.command("/unmute " + SECOND)
    time.sleep(0.3)
    second.chat("OmkLabChatAfterUnmute")
    first.wait(lambda: _contains(first, "OmkLabChatAfterUnmute"))
    expect(True, "moderator_unmute_restores_chat")
    second.command("/me OmkLabUnmutedAction")
    first.wait(lambda: _contains(first, "OmkLabUnmutedAction"))
    second.command("/tell " + FIRST + " OmkLabUnmutedPrivate")
    first.wait(lambda: _contains(first, "OmkLabUnmutedPrivate"))
    expect(True, "unmute_restores_vanilla_action_and_private_message_commands")
    if guarded:
        _chat_permission_check(first, second, console, expect)


def _chat_permission_check(first, second, console, expect):
    console("ranks setp " + SECOND + " ftbutilities.chat.speak false")
    first.messages.clear()
    _response(second, "/me OmkLabRankMuted", "commands.mute.muted")
    expect(
        not _contains(first, "OmkLabRankMuted"),
        "chat_command_guard_honors_ftb_chat_speak_permission",
    )
    console("ranks setp " + SECOND + " ftbutilities.chat.speak none")
    second.command("/me OmkLabRankRestored")
    first.wait(lambda: _contains(first, "OmkLabRankRestored"))
    expect(True, "clearing_chat_speak_override_restores_command")


def run_command_checks(
    client,
    session,
    session2,
    mods,
    console,
    expect,
    report,
    suite="full",
    mute_guard=False,
):
    with ExitStack() as stack:
        first = stack.enter_context(LabPlayer(client, session, 25576, mods))
        second = stack.enter_context(LabPlayer(client, session2, 25576, mods))
        if suite == "rtp":
            _prepare_teleports(first, console)
            _rtp_limits(first, console, expect)
            return False
        if suite == "full":
            _teleports(first, second, console, expect, report)
        _moderation(first, second, console, expect, guarded=mute_guard)
    with LabPlayer(client, session, 25576, mods) as first:
        # Native ban keys by authenticated UUID; no OP is granted anywhere.
        with LabPlayer(client, session2, 25576, mods) as second:
            first.command("/ban " + SECOND + " omk_lab_ban")
            first.wait(lambda: second.error is not None)
            expect(
                "banned" in second.error.lower(), "ban_disconnect_is_explicitly_a_ban"
            )
        try:
            with LabPlayer(client, session2, 25576, mods):
                pass
        except (RuntimeError, ValueError) as error:
            expect(
                "banned" in str(error).lower() or "login was refused" in str(error),
                "moderator_ban_denies_authenticated_rejoin",
            )
        else:
            raise RuntimeError("Banned player rejoined")
        first.command("/pardon " + SECOND)
        time.sleep(0.5)
        with LabPlayer(client, session2, 25576, mods):
            expect(True, "moderator_pardon_allows_authenticated_rejoin")
        if suite == "moderation":
            return False
        _rtp_limits(first, console, expect)
        console("ranks setp player ftbutilities.homes.cooldown 0s")
        _place(first, FIRST, ORIGIN, console)
        _begin(first, "/home one")
        first.wait(lambda: _near(first, HOME))
        console("ranks setp player ftbutilities.homes.cooldown 1h")
        _response(first, "/home one", "cant_use_now_cooldown")
    with LabPlayer(client, session, 25576, mods) as first:
        _response(first, "/home one", "cant_use_now_cooldown")
        expect(True, "home_cooldown_survives_same_server_reconnect")
    return True


def check_after_restart(client, session, mods, expect):
    with LabPlayer(client, session, 25576, mods) as first:
        # The stock mod does not persist cooldown timestamps. Record this as an
        # explicit limitation, not a successful persistence/security guarantee.
        _begin(first, "/home one")
        expect(True, "stock_ftb_home_cooldown_resets_on_full_server_restart")
        _response(first, "/fly", "commands.generic.permission")
        _response(first, "/banlist", "commands.banlist.players")
        expect(True, "moderator_permissions_persist_without_op_after_restart")
