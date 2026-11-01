"""Functional AE2/EnderIO recovery checks, only inside a fresh DJ2 recovery lab."""

import hashlib
import re
import time

from omk.dj2_commands_lab import FIRST, _place, _response
from omk.forge_player import LabPlayer
from omk.recovery_nbt_lab import chunk_level
from omk.recovery_preflight_lab import preflight

MINIMUM, MAXIMUM = (160, 241, 160), (171, 243, 164)
PINS = {
    "ae2-uel-v0.56.4.jar": "3505d2e31e9c48a0c96ca058fcde8a6a50b7d673e13af488a398878d6d33b698",
    "EnderIO-1.12.2-5.3.72.jar": "9b5e7756af35a191de8bc8f010c0f7c7ffc2e1e056a69ec265d1dd5ce90d19b4",
}
CELL = '{id:"appliedenergistics2:storage_cell_1k",Count:1b,Damage:0s}'
DIAMOND = 'id:"minecraft:diamond",Count:7b,Damage:0s,tag:{display:{Name:"ME recovery fixture"}}'
STONE = '{Inventory:[{Slot:1,id:"minecraft:stone",Count:1}]}'


def validate_mod_systems(args):
    if args.runtime != "linux-docker" or args.edge_cases or args.full_backup_return:
        raise ValueError(
            "Mod systems require Linux Docker without other recovery suites"
        )
    for name, expected in PINS.items():
        with (args.server_source / "mods" / name).open("rb") as source:
            if hashlib.file_digest(source, "sha256").hexdigest() != expected:
                raise ValueError("Unpinned mod systems fixture artifact: " + name)


def found(console, point, block, nbt="{}", *, data=-1):
    return "Successfully found" in console(f"testforblock {point} {block} {data} {nbt}")


def wait_found(console, point, block, nbt, expect, label):
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        if found(console, point, block, nbt):
            expect(True, label)
            return
        time.sleep(0.5)
    raise RuntimeError(label)


def cell_nbt(count):
    return (
        "{inv:{item1:{tag:{ic:"
        + str(count)
        + 'L,"#0":{id:"minecraft:diamond",tag:{display:{Name:"ME recovery fixture"}}}}}}}'
    )


def bank_energy(text):
    matches = re.findall(r"\benergyStored:([0-9]{1,10})(?:,|})", text)
    if len(matches) != 1 or not 0 <= int(matches[0]) <= 500000:
        raise ValueError("Missing, ambiguous or invalid fixture bank energy")
    return int(matches[0])


def seed(console, expect, report):
    console("fill 160 240 160 173 240 165 minecraft:bedrock")
    console("fill 160 241 160 173 244 165 minecraft:air")
    # Initial NBT before AE2 joins a grid. Re-loading an already live grid via
    # blockdata is invalid in AE2 and would invalidate the baseline fixture.
    console(
        "setblock 162 241 162 appliedenergistics2:chest 0 replace {inv:{item1:"
        + CELL
        + "}}"
    )
    console("setblock 161 241 162 appliedenergistics2:creative_energy_cell")
    console(
        "setblock 162 242 162 minecraft:hopper 0 replace {Items:[{Slot:0b,"
        + DIAMOND
        + "}]}"
    )
    wait_found(
        console,
        "162 241 162",
        "appliedenergistics2:chest",
        cell_nbt(7),
        expect,
        "baseline_ae2_ingests_seven_named_diamonds_via_hopper",
    )
    console(
        "setblock 168 241 162 enderio:block_cap_bank 2 replace {energyStored:500000,maxInput:1234,maxOutput:2345}"
    )
    console(
        "setblock 169 241 162 enderio:block_cap_bank 2 replace {maxInput:1234,maxOutput:2345}"
    )
    console("setblock 170 241 162 thermalexpansion:machine")
    console(
        'blockdata 170 241 162 {Energy:0,Inventory:[{Slot:0,id:"minecraft:cobblestone",Count:1,Damage:0s}]}'
    )
    wait_found(
        console,
        "170 241 162",
        "thermalexpansion:machine",
        STONE,
        expect,
        "baseline_furnace_smelts_using_enderio_multiblock_power",
    )
    wait_found(
        console,
        "170 241 162",
        "thermalexpansion:machine",
        "{Energy:20000}",
        expect,
        "baseline_furnace_buffer_full_before_energy_snapshot",
    )
    energies = [bank_energy(console(f"blockdata {x} 241 162 {{}}")) for x in (168, 169)]
    expect(
        0 < energies[0] == energies[1] < 250000,
        "baseline_bank_network_balances_energy_between_two_blocks",
    )
    report["mod_system_bank_energy"] = energies
    console(
        'setblock 172 241 162 minecraft:chest 2 replace {Items:[{Slot:0b,id:"minecraft:iron_ingot",Count:3}]}'
    )


def damage(console, expect):
    # Same block type survives, but its inventory is empty: not only missing
    # blocks. Each new tile is allowed to join its network before restoration.
    console("setblock 162 241 162 minecraft:air")
    console(
        "setblock 162 241 162 appliedenergistics2:chest 0 replace {inv:{item1:"
        + CELL
        + "}}"
    )
    for x in (168, 169):
        console(f"setblock {x} 241 162 minecraft:air")
    for x in (168, 169):
        console(f"setblock {x} 241 162 enderio:block_cap_bank 2")
    console("blockdata 170 241 162 {Energy:0,Inventory:[]}")
    console(
        'blockdata 172 241 162 {Items:[{Slot:0b,id:"minecraft:gold_ingot",Count:5}]}'
    )
    expect(
        found(
            console,
            "162 241 162",
            "appliedenergistics2:chest",
            '{inv:{item1:{id:"appliedenergistics2:storage_cell_1k"}}}',
        )
        and not found(console, "162 241 162", "appliedenergistics2:chest", cell_nbt(7)),
        "ae2_same_type_storage_really_emptied",
    )
    for x in (168, 169):
        expect(
            bank_energy(console(f"blockdata {x} 241 162 {{}}")) == 0,
            f"bank_{x}_really_empty",
        )


def restored(console, expect, report, prefix):
    expect(
        found(console, "162 241 162", "appliedenergistics2:chest", cell_nbt(7)),
        prefix + "ae2_cell_named_contents_restored",
    )
    for x, energy in zip((168, 169), report["mod_system_bank_energy"], strict=True):
        expect(
            found(
                console,
                f"{x} 241 162",
                "enderio:block_cap_bank",
                f"{{energyStored:{energy},maxInput:1234,maxOutput:2345}}",
                data=2,
            ),
            prefix + f"bank_{x}_energy_and_limits_restored",
        )
    expect(
        found(console, "170 241 162", "thermalexpansion:machine", STONE),
        prefix + "furnace_inventory_restored",
    )
    expect(
        found(
            console,
            "172 241 162",
            "minecraft:chest",
            '{Items:[{Slot:0b,id:"minecraft:gold_ingot",Count:5}]}',
            data=2,
        ),
        prefix + "outside_neighbor_unchanged",
    )


def exercise(client, session, mods, start, backup, expect, report, snapshots):
    console = start()
    with LabPlayer(client, session, 25576, mods) as actor:
        _place(actor, FIRST, (166.5, 244, 166.5), console)
        seed(console, expect, report)
    backup("before-grief")
    console = start()
    with LabPlayer(client, session, 25576, mods) as actor:
        _place(actor, FIRST, (166.5, 244, 166.5), console)
        damage(console, expect)
    backup("before-restore")
    console = start()
    with LabPlayer(client, session, 25576, mods) as actor:
        _place(actor, FIRST, (166.5, 244, 166.5), console)
        expect(
            preflight(snapshots / "before-grief.zip", MINIMUM, MAXIMUM)["blocks"]
            == 180,
            "mod_system_snapshot_coverage_checked_before_apply",
        )
        console("op " + FIRST)
        for cmd, response in (
            ("//pos1 160,241,160", "First position set"),
            ("//pos2 171,243,164", "Second position set"),
            ("/snap use before-grief.zip", "Snapshot set"),
        ):
            _response(actor, cmd, response)
        for prefix in ("restore_", "repeat_"):
            try:
                _response(
                    actor, "//restore", "Restored; 0 missing chunks and 0 other errors."
                )
            finally:
                report.setdefault("mod_system_restore_responses", []).append(
                    list(actor.messages)
                )
            restored(console, expect, report, prefix)
        console("deop " + FIRST)
    backup("after-restore")
    console = start()
    with LabPlayer(client, session, 25576, mods) as actor:
        _place(actor, FIRST, (166.5, 244, 166.5), console)
        restored(console, expect, report, "restart_")
        console(
            'blockdata 162 242 162 {Items:[{Slot:0b,id:"minecraft:diamond",'
            'Count:1b,Damage:0s,tag:{display:{Name:"ME recovery fixture"}}}]}'
        )
        wait_found(
            console,
            "162 241 162",
            "appliedenergistics2:chest",
            cell_nbt(8),
            expect,
            "restored_ae2_ingests_new_item_after_full_restart",
        )
        console(
            'blockdata 170 241 162 {Energy:0,Inventory:[{Slot:0,id:"minecraft:cobblestone",Count:1,Damage:0s}]}'
        )
        wait_found(
            console,
            "170 241 162",
            "thermalexpansion:machine",
            STONE,
            expect,
            "restored_bank_network_powers_furnace_after_full_restart",
        )


def verify_saved(snapshots, expect):
    def tiles(name):
        return {
            (
                tile.value["x"].value,
                tile.value["y"].value,
                tile.value["z"].value,
            ): tile.value
            for tile in chunk_level(snapshots / name, 10, 10)["TileEntities"].value[1]
        }

    before, damaged, after = (
        tiles(name + ".zip")
        for name in ("before-grief", "before-restore", "after-restore")
    )
    point = (162, 241, 162)
    expect(
        before[point]["inv"] == after[point]["inv"],
        "saved_ae2_complete_cell_inventory_matches_snapshot",
    )
    expect(
        before[point]["inv"] != damaged[point]["inv"],
        "saved_ae2_inventory_damage_control",
    )
    for x in (168, 169):
        for key in ("energyStored", "maxInput", "maxOutput"):
            expect(
                before[(x, 241, 162)][key] == after[(x, 241, 162)][key],
                f"saved_bank_{x}_{key}_matches_snapshot",
            )
    expect(
        damaged[(172, 241, 162)] == after[(172, 241, 162)],
        "saved_outside_neighbor_complete_nbt_unchanged",
    )
