"""Real inventory transfers in disposable claimed/unclaimed DJ2 containers."""

import time

from omk.dj2_commands_lab import FIRST, SECOND, _place

# This DJ2 serializes Count as TAG_Int, verified from the real fixture chunk.
ITEM = '{Slot:0b,id:"minecraft:iron_ingot",Count:1,Damage:0s}'


def _stock(console, point, block):
    xyz = " ".join(map(str, point))
    console(f"setblock {xyz} minecraft:air")
    console(f"setblock {xyz} {block} 0 replace {{Items:[{ITEM}]}}")
    if "Successfully found" not in console(
        f"testforblock {xyz} {block} -1 {{Items:[{ITEM}]}}"
    ):
        raise RuntimeError("Container fixture was not created with its item")


def _open(actor, point, kind):
    actor.open_windows.clear()
    actor.use_block(*point)
    actor.wait(lambda: bool(actor.open_windows))
    window = actor.open_windows[-1]
    if window["type"] != kind:
        raise RuntimeError("Unexpected fixture container type: " + window["type"])
    return window["id"]


def _take(actor, window_id, action, console, name, point, block):
    actor.transactions.clear()
    actor.shift_click(window_id, 0, action, item_id=265, count=1)
    # The real pack transferred the item even when the actor did not observe a
    # positive vanilla confirmation. Test authoritative state, not prediction.
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        actor.check()
        if _empty(console, point, block) and _has_item(console, name):
            return [
                accepted
                for wid, aid, accepted in tuple(actor.transactions)
                if (wid, aid) == (window_id, action)
            ]
        time.sleep(0.1)
    raise RuntimeError("Fixture transfer did not reach server inventory")


def _has_item(console, name):
    result = console(f'testfor {name} {{Inventory:[{{id:"minecraft:iron_ingot"}}]}}')
    if "Found " in result:
        return True
    if "did not match" in result:
        return False
    raise RuntimeError("Unknown inventory assertion response: " + result[-500:])


def _empty(console, point, block):
    xyz = " ".join(map(str, point))
    return "Successfully found" in console(
        f"testforblock {xyz} {block} -1 {{Items:[]}}"
    )


def _deny_open(actor, point):
    actor.open_windows.clear()
    actor.use_block(*point)
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        actor.check()
        if actor.open_windows:
            raise RuntimeError("Non-owner opened a claimed container")
        time.sleep(0.05)


def check_container_transfers(first, second, console, expect, report):
    # Both actors remain non-OP. Survival prevents creative inventory mechanics
    # from invalidating the transfer/duplication controls.
    for name in (FIRST, SECOND):
        console("gamemode 0 " + name)
        console("clear " + name)
    console("fill 16 240 16 31 240 31 minecraft:stone")
    console("fill 16 241 16 31 244 31 minecraft:air")
    confirmations = report["inventory_confirmations"] = []
    for label, block, kind in [
        ("vanilla_chest", "minecraft:chest", "minecraft:chest"),
        ("iron_chest", "ironchest:iron_chest", "forge:ironchest"),
    ]:
        outside = (26, 241, 24)
        inside = (10, 241, 8)
        _place(second, SECOND, (24.5, 241.0, 24.5), console)
        console("clear " + SECOND)
        expect(not _has_item(console, SECOND), label + "_attacker_starts_without_item")
        _stock(console, outside, block)
        previous_window = _open(second, outside, kind)
        accepted = _take(second, previous_window, 1, console, SECOND, outside, block)
        confirmations.append(
            {"container": label, "case": "unclaimed", "accepted": accepted}
        )
        second.close_window(previous_window)
        expect(
            _empty(console, outside, block) and _has_item(console, SECOND),
            label + "_unclaimed_transfer_positive_control",
        )

        console("clear " + SECOND)
        _place(second, SECOND, (8.5, 241.0, 8.5), console)
        _place(first, FIRST, (8.5, 241.0, 8.5), console)
        _stock(console, inside, block)
        _deny_open(second, inside)
        expect(True, label + "_claimed_open_denied_to_non_owner")
        # Sending a valid click with a previously closed window ID must not
        # grant access. It is not an exhaustive malicious-packet audit.
        second.shift_click(previous_window, 0, 2, item_id=265, count=1)
        time.sleep(0.5)
        xyz = " ".join(map(str, inside))
        expect(
            not _has_item(console, SECOND)
            and "Successfully found"
            in console(f"testforblock {xyz} {block} -1 {{Items:[{ITEM}]}}"),
            label + "_closed_window_click_does_not_steal_claimed_item",
        )

        console("clear " + FIRST)
        window_id = _open(first, inside, kind)
        accepted = _take(first, window_id, 1, console, FIRST, inside, block)
        confirmations.append(
            {"container": label, "case": "owner", "accepted": accepted}
        )
        first.close_window(window_id)
        expect(
            _empty(console, inside, block) and _has_item(console, FIRST),
            label + "_claimed_owner_transfer_positive_control",
        )
        # Replay after closing must neither refill the source nor duplicate the
        # single item. The NBT count assertion observes the actual server state.
        first.shift_click(window_id, 0, 1, item_id=265, count=1)
        time.sleep(0.5)
        expect(
            _empty(console, inside, block)
            and "Found "
            in console(
                f'testfor {FIRST} {{Inventory:[{{id:"minecraft:iron_ingot",Count:1}}]}}'
            )
            and "removing 1 items"
            in console("clear " + FIRST + " minecraft:iron_ingot"),
            label + "_closed_window_replay_preserves_single_item_count",
        )
