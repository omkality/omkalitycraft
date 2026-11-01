"""Real death/Shift recovery, restricted to the spawn lab's fresh world."""

import time

from omk.dj2_claims_lab import _block
from omk.dj2_commands_lab import FIRST, SECOND, _place, _response

GRAVE = "tombmanygraves:grave_block"
ITEM = '{id:"minecraft:diamond",Count:17,tag:{display:{Name:"Grave recovery control"}}}'


def _grave(console, x, z):
    return "Successfully found" in console(f"testforblock {x} 241 {z} {GRAVE}")


def _items(console, name):
    return "Found" in console(f"testfor {name} {{Inventory:[{ITEM}]}}")


def _one_grave(owner, outsider, console, expect, x, z, label):
    console(f"fill {x-3} 240 {z-3} {x+3} 240 {z+3} minecraft:bedrock")
    console(f"fill {x-3} 241 {z-3} {x+3} 245 {z+3} minecraft:air")
    _place(outsider, FIRST, (x + 3.5, 241, z + 3.5), console)
    owner.sneak(False)
    console("gamemode 0 " + SECOND)
    console("gamerule keepInventory false")
    console("clear " + SECOND)
    console(
        "replaceitem entity " + SECOND + " slot.hotbar.0 minecraft:diamond 17 0 "
        '{display:{Name:"Grave recovery control"}}'
    )
    expect(_items(console, SECOND), label + "_death_inventory_has_exact_marker")
    _place(owner, SECOND, (x + 0.5, 241, z + 0.5), console)
    console("kill " + SECOND)
    owner.wait(lambda: owner.health is not None and owner.health <= 0)
    expect(_grave(console, x, z), label + "_real_death_creates_grave_inside_claim")
    owner.respawn()
    owner.wait(lambda: owner.health is not None and owner.health > 0)
    expect(not _items(console, SECOND), label + "_respawn_does_not_restore_items_early")
    _place(owner, SECOND, (x + 3.5, 241, z + 3.5), console)
    # Even the land owner cannot obtain the visitor's grave contents.
    outsider.sneak(True)
    _place(outsider, FIRST, (x + 0.5, 241, z + 0.5), console)
    time.sleep(1)
    expect(
        _grave(console, x, z) and not _items(console, FIRST),
        label + "_outsider_shift_cannot_take_grave",
    )
    outsider.sneak(False)
    _place(outsider, FIRST, (x + 3.5, 241, z + 3.5), console)
    _place(owner, SECOND, (x + 0.5, 241, z + 0.5), console)
    time.sleep(1)
    expect(
        _grave(console, x, z) and not _items(console, SECOND),
        label + "_owner_without_shift_keeps_grave_control",
    )
    owner.sneak(True)
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline and _grave(console, x, z):
        owner.move(x + 0.51, 241, z + 0.5)
        time.sleep(0.15)
    expect(
        _block(console, x, 241, z, "air") and _items(console, SECOND),
        label + "_owner_shift_restores_exact_items_and_removes_grave",
    )
    owner.sneak(False)
    console("clear " + SECOND)
    console("gamemode 1 " + SECOND)


def check_graves(first, second, console, expect):
    # FIRST owns the ordinary claim; SECOND is an unrelated visitor in both cases.
    _place(first, FIRST, (616.5, 241, 8.5), console)
    first.command("/chunks claim")
    _response(first, "/chunks info", "omklab")
    _one_grave(second, first, console, expect, 616, 8, "foreign_claim_grave")
    _place(first, FIRST, (80.5, 241, 80.5), console)
    _response(first, "/chunks info", "OmkalityCraft spawn")
    _one_grave(second, first, console, expect, 80, 80, "server_spawn_grave")
