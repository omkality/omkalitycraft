"""Characterize compound inventories and permission revocation in the owned lab."""

import time

from omk.dj2_claims_lab import _block
from omk.dj2_commands_lab import FIRST, SECOND, _place, _response
from omk.dj2_inventory_lab import ITEM, _empty, _has_item, _open, _stock, _take


def _probe_take(actor, window, slot, console, point, block):
    actor.shift_click(window, slot, 2, item_id=265, count=1)
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        actor.check()
        if _empty(console, point, block) and _has_item(console, SECOND):
            return True
        time.sleep(0.1)
    xyz = " ".join(map(str, point))
    if _has_item(console, SECOND) or "Successfully found" not in console(
        f"testforblock {xyz} {block} -1 {{Items:[{ITEM}]}}"
    ):
        raise RuntimeError("Unexpected item loss or ambiguous inventory state")
    return False


def _window_or_none(actor, point):
    actor.open_windows.clear()
    actor.use_block(*point)
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        actor.check()
        if actor.open_windows:
            return actor.open_windows[-1]
        time.sleep(0.05)
    return None


def _double_chest(first, second, console, expect, report, guarded):
    console("fill 12 240 4 28 240 12 minecraft:stone")
    console("fill 12 241 4 28 244 12 minecraft:air")
    _place(second, SECOND, (24.5, 241.0, 8.5), console)
    _stock(console, (23, 241, 8), "minecraft:chest")
    console("setblock 24 241 8 minecraft:chest")
    window = _open(second, (24, 241, 8), "minecraft:chest")
    expect(
        second.open_windows[-1]["slots"] == 54, "unclaimed_double_chest_has_54_slots"
    )
    _take(second, window, 1, console, SECOND, (23, 241, 8), "minecraft:chest")
    second.close_window(window)
    expect(True, "unclaimed_double_chest_transfer_from_opposite_half_control")
    console("clear " + SECOND)
    _place(second, SECOND, (18.5, 241.0, 8.5), console)
    _stock(console, (15, 241, 8), "minecraft:chest")
    # The outsider really places the other half on unclaimed terrain; the
    # console creates only the owner's chest and the laboratory platform.
    console("replaceitem entity " + SECOND + " slot.hotbar.0 minecraft:chest")
    second.select_hotbar(0)
    second.use_block(16, 240, 8)
    time.sleep(0.5)
    expect(
        _block(console, 16, 241, 8, "chest"),
        "non_owner_places_unclaimed_chest_next_to_claimed_half",
    )
    opened = _window_or_none(second, (16, 241, 8))
    if opened:
        expect(opened["slots"] == 54, "boundary_chest_forms_real_compound_inventory")
    taken = _probe_take(
        second,
        opened["id"] if opened else window,
        0,
        console,
        (15, 241, 8),
        "minecraft:chest",
    )
    report["claim_edge_observations"]["double_chest"] = {
        "opened": opened is not None,
        "item_taken": taken,
    }
    expect(
        not taken if guarded else True,
        (
            "guard_blocks_boundary_double_chest_theft"
            if guarded
            else (
                "stock_boundary_double_chest_allows_theft_from_claimed_half"
                if taken
                else "stock_boundary_double_chest_denies_theft_from_claimed_half"
            )
        ),
    )
    if opened:
        second.close_window(opened["id"])
    # Owner control includes the two halves on different chunks as well.
    console("clear " + SECOND)
    console("blockdata 15 241 8 {Items:[]}")
    console("setblock 15 241 8 minecraft:air")
    _stock(console, (15, 241, 8), "minecraft:chest")
    _place(first, FIRST, (14.5, 241.0, 8.5), console)
    console("replaceitem entity " + FIRST + " slot.hotbar.0 minecraft:air")
    owned = _open(first, (15, 241, 8), "minecraft:chest")
    _take(first, owned, 1, console, FIRST, (15, 241, 8), "minecraft:chest")
    first.close_window(owned)
    expect(True, "owner_can_use_boundary_double_chest_positive_control")


def _join(first, second):
    _response(first, "/team status " + SECOND + " invited", "commands.team.status.set")
    second.command("/team join omklab")
    # Member notifications use FTB's client UI channel, not ordinary chat.
    # Query the actual resulting relation instead of waiting for that UI.
    _response(first, "/team status " + SECOND, "ftblib.lang.team_status.member")


def _revocation(first, second, console, expect, report, guarded):
    point = (10, 241, 8)
    for label, block, kind in [
        ("vanilla_chest", "minecraft:chest", "minecraft:chest"),
        ("iron_chest", "ironchest:iron_chest", "forge:ironchest"),
    ]:
        _join(first, second)
        _place(second, SECOND, (8.5, 241.0, 8.5), console)
        console("clear " + SECOND)
        console("blockdata 10 241 8 {Items:[]}")
        _stock(console, point, block)
        control = _open(second, point, kind)
        _take(second, control, 1, console, SECOND, point, block)
        second.close_window(control)
        expect(True, label + "_team_member_transfer_positive_control")
        console("clear " + SECOND)
        _stock(console, point, block)
        active = _open(second, point, kind)
        second.closed_windows.clear()
        first.command("/team kick " + SECOND)
        _response(first, "/team status " + SECOND, "ftblib.lang.team_status.none")
        if guarded:
            second.wait(lambda active=active: active in tuple(second.closed_windows))
        taken = _probe_take(second, active, 0, console, point, block)
        closed = active in tuple(second.closed_windows)
        report["claim_edge_observations"][label + "_revocation"] = {
            "closed_by_server": closed,
            "item_taken_after_kick": taken,
        }
        expect(
            not taken if guarded else True,
            label
            + (
                "_guard_closes_revoked_member_container"
                if guarded
                else (
                    "_stock_open_container_allows_transfer_after_team_kick"
                    if taken
                    else "_stock_open_container_denies_transfer_after_team_kick"
                )
            ),
        )
        second.close_window(active)


def check_claim_edges(first, second, console, expect, report, *, guarded=False):
    report["claim_edge_observations"] = {}
    for name in (FIRST, SECOND):
        console("gamemode 0 " + name)
        console("clear " + name)
    _double_chest(first, second, console, expect, report, guarded)
    _revocation(first, second, console, expect, report, guarded)
