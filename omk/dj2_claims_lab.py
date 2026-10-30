"""Block placement/container access on fresh lab chunks, using FTB protection."""

import time

from omk.dj2_commands_lab import FIRST, SECOND, _place


def _block(console, x, y, z, expected):
    return "Successfully found" in console(
        f"testforblock {x} {y} {z} minecraft:{expected}"
    )


def _open_chest(actor, point):
    actor.open_windows.clear()
    actor.use_block(*point)
    actor.wait(lambda: bool(actor.open_windows))
    window = actor.open_windows[-1]
    if window["slots"] != 27:
        raise RuntimeError("Expected a single vanilla chest window")
    actor.close_window(window["id"])


def check_claim_interactions(first, second, console, expect):
    console("fill 16 240 16 31 240 31 minecraft:stone")
    console("fill 16 241 16 31 244 31 minecraft:air")
    _place(second, SECOND, (24.5, 241.0, 24.5), console)
    for name, actor in [(SECOND, second), (FIRST, first)]:
        console("replaceitem entity " + name + " slot.hotbar.0 minecraft:stone 64")
        actor.select_hotbar(0)
    second.use_block(25, 240, 24)
    time.sleep(0.5)
    expect(
        _block(console, 25, 241, 24, "stone"),
        "non_owner_places_block_in_unclaimed_chunk_positive_control",
    )
    console("setblock 26 241 24 minecraft:chest")
    _open_chest(second, (26, 241, 24))
    expect(True, "non_owner_opens_unclaimed_chest_positive_control")

    _place(second, SECOND, (8.5, 241.0, 8.5), console)
    _place(first, FIRST, (8.5, 241.0, 8.5), console)
    console("setblock 9 241 8 minecraft:air")
    second.use_block(9, 240, 8)
    time.sleep(0.5)
    expect(
        _block(console, 9, 241, 8, "air"), "ftb_claim_blocks_non_owner_block_placement"
    )
    first.use_block(9, 240, 8)
    time.sleep(0.5)
    expect(
        _block(console, 9, 241, 8, "stone"), "ftb_claim_allows_owner_block_placement"
    )

    console("setblock 10 241 8 minecraft:chest")
    second.open_windows.clear()
    second.use_block(10, 241, 8)
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        second.check()
        if second.open_windows:
            raise RuntimeError("Non-owner opened protected chest")
        time.sleep(0.05)
    expect(True, "ftb_claim_blocks_non_owner_chest_open")
    _open_chest(first, (10, 241, 8))
    expect(True, "ftb_claim_allows_owner_chest_open")
