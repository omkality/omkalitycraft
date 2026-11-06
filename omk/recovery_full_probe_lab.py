"""Real game checks for a full backup started in an empty replacement lab."""

import hashlib
import json
import shutil
import time
from contextlib import ExitStack

from omk.dj2_commands_lab import FIRST, SECOND, _place, _response
from omk.dj2_lab import _console_sender, _copy_server
from omk.forge_player import LabPlayer
from omk.recovery_edges_lab import TAGS, entity_count
from omk.recovery_full_lab import stage_full_world


def seed_full_return(actor, console, expect):
    _response(actor, "/team create omkrecovery", "ftblib.lang.team.created")
    actor.command("/chunks claim")
    time.sleep(0.5)
    _response(actor, "/sethome backuporigin", "ftbutilities.lang.homes.set")
    console(f"replaceitem entity {FIRST} slot.hotbar.8 minecraft:emerald 5")
    expect(
        "Found "
        in console(
            # DJ2/NotEnoughIDs writes Count as TAG_Int, Slot remains TAG_Byte.
            f'testfor {FIRST} {{Inventory:[{{Slot:8b,id:"minecraft:emerald",Count:5}}]}}'
        ),
        "full_backup_player_inventory_seeded",
    )


def damage_full_return(actor, console, expect):
    actor.command("/chunks unclaim")
    _response(actor, "/delhome backuporigin", "ftbutilities.lang.homes.del")
    console(f"replaceitem entity {FIRST} slot.hotbar.8 minecraft:emerald 1")
    expect(
        "Found "
        in console(
            f'testfor {FIRST} {{Inventory:[{{Slot:8b,id:"minecraft:emerald",Count:1}}]}}'
        ),
        "full_backup_player_inventory_really_changed",
    )


def tree_digest(root, *, jars_only=False):
    values = {}
    for path in sorted(root.rglob("*.jar" if jars_only else "*")):
        if path.is_symlink():
            raise ValueError("Linked owned lab tree")
        if path.is_file():
            with path.open("rb") as file:
                values[path.relative_to(root).as_posix()] = hashlib.file_digest(
                    file, "sha256"
                ).hexdigest()
    return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()


def _restored_state(first, console, expect):
    from omk.recovery_lab import ITEM, MACHINE, _found, _smelt  # noqa: PLC0415

    for label, point, block, nbt in [
        ("vanilla_chest", "130 241 130", "minecraft:chest", f"{{Items:[{ITEM}]}}"),
        ("iron_chest", "132 241 130", "ironchest:iron_chest", f"{{Items:[{ITEM}]}}"),
        ("thermal", "134 241 130", "thermalexpansion:machine", MACHINE),
        ("old_neighbor_inventory", "136 241 130", "minecraft:chest", "{Items:[]}"),
    ]:
        expect(_found(console, point, block, nbt), "full_return_" + label)
    for kind, count in (("original", 1), ("new", 0), ("outside", 1)):
        expect(entity_count(console, TAGS[kind]) == count, "full_return_entity_" + kind)
    expect(
        "Found "
        in console(
            f'testfor {FIRST} {{Inventory:[{{Slot:8b,id:"minecraft:emerald",Count:5}}]}}'
        ),
        "full_return_player_inventory",
    )
    _place(first, FIRST, (140.5, 241, 140.5), console)
    first.command("/home backuporigin")
    first.wait(lambda: abs(first.position[0] - 128.5) < 1)
    expect(True, "full_return_ftb_home_really_teleports")
    _smelt(console, expect, "full_return_machine_really_smelts")


def _claim(first, second, console, expect):
    for actor, name in ((first, FIRST), (second, SECOND)):
        _place(actor, name, (140.5, 241, 132.5), console)
        console("gamemode 1 " + name)
    for x in (139, 144):
        console(f"setblock {x} 241 132 minecraft:stone")
    second.dig(144, 241, 132)
    time.sleep(0.5)
    expect(
        "Successfully found" in console("testforblock 144 241 132 minecraft:air"),
        "full_return_outsider_unclaimed_positive_control",
    )
    second.dig(139, 241, 132)
    time.sleep(0.5)
    expect(
        "Successfully found" in console("testforblock 139 241 132 minecraft:stone"),
        "full_return_ftb_claim_blocks_outsider",
    )
    first.dig(139, 241, 132)
    time.sleep(0.5)
    expect(
        "Successfully found" in console("testforblock 139 241 132 minecraft:air"),
        "full_return_ftb_owner_keeps_access",
    )


def exercise_full_return(
    args,
    lab,
    old_server,
    client,
    sessions,
    mods,
    report,
    expect,
    start,
    backup,
    original_world_digest=None,
    current_access_stage=None,
    restore_source=None,
):
    if current_access_stage is not None:
        from omk.recovery_access_lab import seed_access  # noqa: PLC0415

        seed_access(_console_sender(old_server, lab / "server-output.log"), expect)
    if getattr(args, "rank_policy", False):
        from omk.recovery_ranks_lab import seed_ranks  # noqa: PLC0415

        seed_ranks(_console_sender(old_server, lab / "server-output.log"), expect)
    backup("before-full-return")
    original = lab / "server"
    original_world_digest = original_world_digest or (
        lambda: tree_digest(original / "lab-world")
    )
    original_digest = original_world_digest()
    report["full_return_original_digest_before"] = original_digest
    replacement = lab / "recovery-lab-return"
    replacement.mkdir()
    dest, _ = _copy_server(args, replacement)
    shutil.copy2(args.worldedit, dest / "mods/WorldEdit.jar")
    expect(
        tree_digest(original / "mods", jars_only=True)
        == tree_digest(dest / "mods", jars_only=True),
        "full_return_identical_runtime_mods",
    )
    archive, expected = (
        restore_source()
        if restore_source is not None
        else (
            lab / "backups/before-grief.zip",
            report["backups"]["before-grief"]["sha256"],
        )
    )
    report["full_return_stage"] = stage_full_world(
        old_server,
        archive,
        expected,
        dest / "lab-world",
        lab=lab,
    )
    expect(True, "full_return_archive_bytes_readback_verified_before_start")
    if current_access_stage is not None:
        report["current_access"] = current_access_stage(dest)
        expect(True, "current_access_lists_staged_before_replacement_start")
    if not _authority_gate(
        args, lab, dest, report, expect, original_world_digest, original_digest
    ):
        return
    console = start(dest)
    if current_access_stage is not None:
        from omk.recovery_access_lab import verify_access  # noqa: PLC0415

        verify_access(client, sessions, mods, console, expect)
    if getattr(args, "rank_policy", False):
        from omk.recovery_ranks_lab import verify_ranks  # noqa: PLC0415

        verify_ranks(client, sessions[0], mods, console, expect)
    with ExitStack() as stack:
        first, second = [
            stack.enter_context(LabPlayer(client, s, 25576, mods)) for s in sessions
        ]
        _restored_state(first, console, expect)
        _claim(first, second, console, expect)
    report["full_return_original_digest_after"] = original_world_digest()
    expect(
        report["full_return_original_digest_after"] == original_digest,
        "full_return_original_world_preserved",
    )


def _authority_gate(
    args, lab, dest, report, expect, original_world_digest, original_digest
):
    if getattr(args, "ftb_authority_policy", False):
        from omk.ftb_restore_authority import stage_gate  # noqa: PLC0415

        try:
            report["ftb_authority"] = stage_gate(
                lab / "backups/before-full-return.zip", dest, lab=lab
            )
        except ValueError as error:
            if not getattr(args, "ftb_authority_conflict", False) or str(error) != (
                "Current FTB authority differs from historical world; replacement start blocked"
            ):
                raise
            comparison = json.loads((lab / "ftb-authority-comparison.json").read_text())
            expect(
                not comparison["compatible"],
                "historical_revoked_ally_blocks_full_return",
            )
            expect(
                "teams/omkrecovery.dat" in comparison["changed_records"],
                "revoked_team_authority_difference_identified",
            )
            report["ftb_authority"] = comparison
            report["replacement_start_blocked"] = True
            report["full_return_original_digest_after"] = original_world_digest()
            expect(
                report["full_return_original_digest_after"] == original_digest,
                "refused_return_preserves_original_world",
            )
            return False
        if getattr(args, "ftb_authority_conflict", False):
            raise ValueError(
                "Expected historical FTB authority conflict was not detected"
            )
        expect(True, "current_ftb_authority_matches_historical_before_start")
    return True
