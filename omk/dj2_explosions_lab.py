"""TNT block damage controls, exclusively in the harness's fresh lab world."""

import time

from omk.dj2_claims_lab import _block
from omk.dj2_commands_lab import FIRST, SECOND, _place


def _tnt(console, x, y, z):
    # Fixed position/fuse avoid depending on gravity in this server-only test.
    result = console(
        f"summon minecraft:tnt {x} {y} {z} "
        '{Fuse:1s,NoGravity:1b,Motion:[0.0d,0.0d,0.0d],Tags:["omklabtnt"]}'
    )
    if "Object successfully summoned" not in result:
        raise RuntimeError("Could not summon lab TNT")
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        # Wait for the actual entity to disappear, not just an arbitrary delay.
        result = console("testfor @e[type=minecraft:tnt,tag=omklabtnt]")
        if "found nothing" in result or "cannot be found" in result:
            return
        time.sleep(0.1)
    raise RuntimeError("Lab TNT did not finish its explosion")


def check_tnt_claims(first, second, console, expect):
    for name, actor in ((FIRST, first), (SECOND, second)):
        console("gamemode 1 " + name)
        _place(actor, name, (24.5, 241.0, 24.5), console)
    console("fill 4 241 4 20 245 12 minecraft:air")
    console("fill 36 241 36 44 245 44 minecraft:air")
    console("setblock 40 241 40 minecraft:wool")
    expect(_block(console, 40, 241, 40, "wool"), "tnt_unclaimed_target_exists")
    _tnt(console, 40.5, 242.5, 40.5)
    expect(_block(console, 40, 241, 40, "air"), "tnt_destroys_unclaimed_block_control")

    console("setblock 8 241 8 minecraft:wool")
    _tnt(console, 8.5, 242.5, 8.5)
    expect(
        _block(console, 8, 241, 8, "wool"),
        "ftb_default_claim_prevents_tnt_block_damage_inside_claim",
    )
    # x=15 belongs to the owner's chunk; x=16 is the adjacent unclaimed chunk.
    console("setblock 15 241 8 minecraft:wool")
    console("setblock 16 241 8 minecraft:wool")
    _tnt(console, 16.0, 242.5, 8.5)
    expect(
        _block(console, 15, 241, 8, "wool") and _block(console, 16, 241, 8, "air"),
        "ftb_tnt_at_claim_border_preserves_claimed_and_breaks_unclaimed_block",
    )
