"""WorldEdit snapshot experiment. Only newly created, loopback DJ2 labs are touched."""

import hashlib
import json
import shutil
import time
import traceback
import zipfile
from uuid import uuid4

from omk.dj2_commands_lab import FIRST, _place, _response
from omk.dj2_lab import (
    _accounts,
    _cleanup,
    _console_sender,
    _copy_server,
    _start_server,
    _stop_server,
    _wait_server,
    approved_mods,
)
from omk.forge_player import LabPlayer
from omk.profiles import PROJECT_ROOT
from omk.recovery_edges_lab import (
    characterize_entities,
    check_partial_snapshot,
    damage_edges,
    seed_edges,
)
from omk.recovery_preflight_lab import preflight
from omk.recovery_snapshot_lab import prepare_overworld_snapshot

WORLDEDIT_SHA256 = "cd4768ded9e2b527e3fc093fdf4ce07f058187de7961bdc0d7fa821c1b756f75"
WORLDEDIT_SOURCE = (
    "https://www.curseforge.com/minecraft/mc-mods/worldedit/files/2941712"
)
ITEM = '{Slot:0b,id:"minecraft:diamond",Count:3,Damage:0s,tag:{display:{Name:"Recovery fixture"}}}'
MACHINE = '{Energy:20000,Facing:5b,Inventory:[{Slot:1,id:"minecraft:iron_ingot",Count:7,Damage:0s}]}'


def _sha256(path):
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def add_recovery_lab(parser):
    from pathlib import Path  # noqa: PLC0415

    for flag in ["server-source", "agent", "core", "mods-json", "worldedit"]:
        parser.add_argument("--" + flag, type=Path, required=True)
    parser.add_argument("--java", type=Path, help="Required for the native runtime")
    parser.add_argument(
        "--runtime", choices=("native", "linux-docker"), default="native"
    )
    parser.add_argument(
        "--edge-cases",
        action="store_true",
        help="Characterize entities and a deliberately incomplete snapshot in the new lab",
    )
    parser.add_argument(
        "--full-backup-return",
        action="store_true",
        help="With --edge-cases, start a full backup in a new empty replacement lab",
    )


def _snapshot(server, dest, target):
    if (
        server.poll() != 0
        or dest.name != "server"
        or not dest.parent.name.startswith("recovery-lab-")
    ):
        raise ValueError("Snapshot requires a cleanly stopped owned recovery lab")
    world = dest / "lab-world"
    if not (world / "level.dat").is_file() or target.exists():
        raise ValueError("Missing fresh world or snapshot already exists")
    # Streaming ZIP, no region replacement or extraction, no files from old servers.
    size = count = 0
    with zipfile.ZipFile(target, "x", zipfile.ZIP_DEFLATED, compresslevel=1) as archive:
        for path in sorted(world.rglob("*")):
            if path.is_symlink():
                raise ValueError("Linked lab snapshot input")
            if not path.is_file():
                continue
            size += path.stat().st_size
            count += 1
            if size > 512 * 1024**2 or count > 20000:
                raise ValueError("Lab snapshot limit exceeded")
            archive.write(path, path.relative_to(dest).as_posix())
    return {
        "files": count,
        "uncompressed_bytes": size,
        "bytes": target.stat().st_size,
        "sha256": _sha256(target),
    }


def _found(console, xyz, block, nbt="{}", *, data=-1):
    return "Successfully found" in console(f"testforblock {xyz} {block} {data} {nbt}")


def _fixture(console):
    console("fill 128 240 128 143 240 143 minecraft:bedrock")
    console("fill 128 241 128 143 245 143 minecraft:air")
    console(f"setblock 130 241 130 minecraft:chest 2 replace {{Items:[{ITEM}]}}")
    console(f"setblock 132 241 130 ironchest:iron_chest 0 replace {{Items:[{ITEM}]}}")
    console("setblock 134 241 130 thermalexpansion:machine")
    # CoFH's placement callback initializes its tile after setblock NBT. Merge
    # the fixture into the initialized tile, retaining its complete schema.
    console(f"blockdata 134 241 130 {MACHINE}")
    console("setblock 136 241 130 minecraft:chest 2 replace {Items:[]}")
    console("setblock 130 244 130 minecraft:gold_block")
    console("setblock 129 241 130 minecraft:gold_block")
    console("setblock 130 241 129 minecraft:gold_block")


def _damage(console):
    console("setblock 130 241 130 minecraft:air")
    console("setblock 132 241 130 ironchest:iron_chest 0 replace {Items:[]}")
    console("blockdata 132 241 130 {Items:[]}")
    console("blockdata 134 241 130 {Energy:0,Inventory:[],Facing:2b}")
    console("setblock 131 242 131 minecraft:obsidian")
    console(f"blockdata 136 241 130 {{Items:[{ITEM}]}}")
    console("setblock 130 244 130 minecraft:diamond_block")
    console("setblock 129 241 130 minecraft:diamond_block")
    console("setblock 130 241 129 minecraft:diamond_block")
    console("setblock 130 240 130 minecraft:diamond_block")


def _restored(console, expect, prefix):
    for label, xyz, block, nbt in [
        (
            "vanilla_chest_named_inventory",
            "130 241 130",
            "minecraft:chest",
            f"{{Items:[{ITEM}]}}",
        ),
        (
            "same_type_iron_chest_inventory",
            "132 241 130",
            "ironchest:iron_chest",
            f"{{Items:[{ITEM}]}}",
        ),
        (
            "machine_energy_orientation_inventory",
            "134 241 130",
            "thermalexpansion:machine",
            MACHINE,
        ),
        ("griefer_block_removed", "131 242 131", "minecraft:air", "{}"),
        (
            "neighbor_chest_same_chunk_unchanged",
            "136 241 130",
            "minecraft:chest",
            f"{{Items:[{ITEM}]}}",
        ),
        (
            "above_selection_same_chunk_unchanged",
            "130 244 130",
            "minecraft:diamond_block",
            "{}",
        ),
        ("west_of_selection_unchanged", "129 241 130", "minecraft:diamond_block", "{}"),
        (
            "north_of_selection_unchanged",
            "130 241 129",
            "minecraft:diamond_block",
            "{}",
        ),
        ("below_selection_unchanged", "130 240 130", "minecraft:diamond_block", "{}"),
    ]:
        data = 2 if block == "minecraft:chest" else -1
        expect(_found(console, xyz, block, nbt, data=data), prefix + label)
    expect(
        _found(console, "134 241 130", "thermalexpansion:machine", data=0),
        prefix + "machine_block_metadata_unchanged",
    )


def _smelt(console, expect, label):
    console(
        'blockdata 134 241 130 {Inventory:[{Slot:0,id:"minecraft:cobblestone",Count:1,Damage:0s}]}'
    )
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        if _found(
            console,
            "134 241 130",
            "thermalexpansion:machine",
            '{Inventory:[{Slot:1,id:"minecraft:stone",Count:1}]}',
        ):
            expect(True, label)
            return
        time.sleep(0.5)
    raise RuntimeError(label + ": " + console("blockdata 134 241 130 {}")[-2000:])


def _restore(actor, command="//restore"):
    _response(actor, command, "Restored; 0 missing chunks and 0 other errors.")


def _restore_checks(actor, console, expect, report, snapshots, edge_cases):
    _response(actor, "//restore before-grief.zip", "not permitted")
    expect(
        _found(console, "130 241 130", "minecraft:air"),
        "normal_player_cannot_restore",
    )
    console("op " + FIRST)  # Only this new lab, not the player's real rank.
    _response(actor, "//pos1 130,241,130", "First position set")
    _response(actor, "//pos2 135,243,134", "Second position set")
    _response(actor, "/snap list", "before-grief.zip")
    expect(True, "operator_lists_actual_zip_snapshots")
    _response(actor, "/snap use before-grief.zip", "Snapshot set")
    if edge_cases:
        expect(
            preflight(snapshots / "before-grief.zip", (130, 241, 130), (135, 243, 134))[
                "blocks"
            ]
            == 90,
            "primary_restore_selection_passes_readonly_preflight",
        )
    _restore(actor)
    report["restore_response"] = list(actor.messages)
    _restored(console, expect, "first_restore_")
    if edge_cases:
        characterize_entities(console, expect, report, "after_restore_")
    _response(actor, "//undo", "Undo successful")
    expect(_found(console, "130 241 130", "minecraft:air"), "undo_restores_damaged_air")
    expect(
        _found(console, "134 241 130", "thermalexpansion:machine", "{Energy:0}"),
        "undo_restores_damaged_machine",
    )
    _response(actor, "//redo", "Redo successful")
    _restored(console, expect, "redo_")
    _restore(actor)
    _restored(console, expect, "repeat_restore_")
    _response(actor, "//restore nonexistent.zip", "does not exist")
    _restored(console, expect, "missing_snapshot_")
    if edge_cases:
        check_partial_snapshot(actor, console, snapshots, expect, report)
    console("deop " + FIRST)


def _exercise(
    client, session, mods, start, backup, expect, report, *, snapshots, edge_cases
):
    console = start()
    with LabPlayer(client, session, 25576, mods) as actor:
        _place(actor, FIRST, (128.5, 241, 128.5), console)
        _fixture(console)
        if report.get("full_backup_return"):
            from omk.recovery_full_probe_lab import seed_full_return  # noqa: PLC0415

            seed_full_return(actor, console, expect)
        if edge_cases:
            seed_edges(console, expect)
        _smelt(console, expect, "machine_smelt_positive_control_before_snapshot")
        console(f"blockdata 134 241 130 {MACHINE}")
        report["machine_fixture_nbt"] = console("blockdata 134 241 130 {}")[-3500:]
        expect(
            _found(console, "134 241 130", "thermalexpansion:machine", MACHINE),
            "idle_machine_fixture_has_seeded_state",
        )
        expect(
            _found(
                console,
                "132 241 130",
                "ironchest:iron_chest",
                f"{{Items:[{ITEM}]}}",
            ),
            "iron_chest_fixture_has_named_items",
        )
    backup("before-grief")
    console = start()
    with LabPlayer(client, session, 25576, mods) as actor:
        _place(actor, FIRST, (128.5, 241, 128.5), console)
        _damage(console)
        if report.get("full_backup_return"):
            from omk.recovery_full_probe_lab import damage_full_return  # noqa: PLC0415

            damage_full_return(actor, console, expect)
        if edge_cases:
            damage_edges(console, expect)
        expect(_found(console, "130 241 130", "minecraft:air"), "base_really_damaged")
        expect(
            _found(console, "134 241 130", "thermalexpansion:machine", "{Energy:0}"),
            "machine_state_really_damaged",
        )
    backup("before-restore")
    console = start()
    with LabPlayer(client, session, 25576, mods) as actor:
        _place(actor, FIRST, (128.5, 241, 128.5), console)
        _restore_checks(actor, console, expect, report, snapshots, edge_cases)
    backup("after-restore")
    console = start()
    with LabPlayer(client, session, 25576, mods) as actor:
        _place(actor, FIRST, (128.5, 241, 128.5), console)
        _restored(console, expect, "after_restart_")
        if edge_cases:
            characterize_entities(console, expect, report, "after_restart_")
        _smelt(console, expect, "restored_machine_smelt_after_full_restart")


def _validate_inputs(args):
    paths = [args.agent, args.core, args.mods_json, args.worldedit]
    if getattr(args, "runtime", "native") == "native":
        paths.append(args.java)
    elif args.full_backup_return:
        raise ValueError("Full backup return is not yet supported in the Linux lab")
    for path in paths:
        if path is None or not path.is_file():
            raise ValueError("Required recovery lab input missing")
    approved_mods(args.mods_json)
    if _sha256(args.worldedit) != WORLDEDIT_SHA256:
        raise ValueError("Expected pinned official WorldEdit file 2941712")
    if args.full_backup_return and not args.edge_cases:
        raise ValueError("Full backup return requires --edge-cases")


def _backup(server, stream, lab, dest, name, report):
    _stop_server(server)
    stream.close()
    source = lab / "backups" / (name + ".zip")
    info = _snapshot(server, dest, source)
    _prepare_backup(lab, name, info, report)


def _prepare_backup(lab, name, info, report):
    source = lab / "backups" / (name + ".zip")
    target = lab / "snapshots" / (name + ".zip")
    report.setdefault("backups", {})[name] = info
    prepared = prepare_overworld_snapshot(source, target)
    prepared["sha256"] = _sha256(target)
    report.setdefault("snapshots", {})[name] = prepared
    if name == "before-restore":
        (lab / "recovery-plan.json").write_text(
            json.dumps(
                {
                    "schema": 1,
                    "lab_only": True,
                    "allowlisted_dimensions": [0],
                    "selection": report["scope"],
                    "restore_source": "before-grief.zip",
                    "backup_before_apply": "backups/before-restore.zip",
                    "snapshots": report["snapshots"],
                    "artifacts": report["artifacts"],
                    "native_partial_probe": (
                        {
                            "lab_only": True,
                            "guard_bypassed_for_characterization": True,
                            "min": [143, 241, 132],
                            "max": [144, 241, 132],
                        }
                        if report.get("edge_cases")
                        else None
                    ),
                },
                indent=2,
            ),
            encoding="utf-8",
        )


def _prepare_recovery_server(args, lab, report):
    dest, mods = _copy_server(args, lab)
    shutil.copy2(args.worldedit, dest / "mods/WorldEdit.jar")
    config = dest / "config/worldedit"
    config.mkdir(exist_ok=True)
    snapshots, backups = lab / "snapshots", lab / "backups"
    snapshots.mkdir()
    backups.mkdir()
    snapshot_path = (
        "/snapshots" if args.runtime == "linux-docker" else snapshots.as_posix()
    )
    (config / "worldedit.properties").write_text(
        "snapshots-dir=" + snapshot_path + "\nmax-changed-blocks=4096\n"
        "default-max-changed-blocks=4096\nuse-in-creative=false\ncheat-mode=false\n"
        "log-commands=false\n",
        encoding="ascii",
    )
    report["private_core_sha256"] = _sha256(args.core)
    report["artifacts"] = {
        p.name: _sha256(p)
        for p in [
            dest / "forge-1.12.2-14.23.5.2860.jar",
            dest / "mods/ironchest-1.12.2-7.0.72.847.jar",
            dest / "mods/ThermalExpansion-1.12.2-5.5.7.1-universal.jar",
        ]
    }
    return dest, mods, snapshots


class RecoveryRuntime:
    def __init__(self, args, lab, dest, client, report, state, expect):
        self.args, self.lab, self.dest, self.client = args, lab, dest, client
        self.report, self.state, self.expect = report, state, expect
        self.linux = self.server = self.stream = None

    def start(self, replacement=None):
        if self.linux is not None:
            if replacement is not None:
                raise ValueError("Linux replacement runtime has not been tested")
            self.server, log, self.stream = self.linux.start()
        else:
            self.server, log, self.stream = _start_server(
                self.args, self.lab, replacement or self.dest, self.client
            )
        _wait_server(self.server, log, self.state)
        return _console_sender(self.server, log)

    def backup(self, name):
        self.state("stopping_owned_lab_for_" + name)
        if self.linux is not None:
            info = self.linux.backup(name)
            _prepare_backup(self.lab, name, info, self.report)
        else:
            _backup(self.server, self.stream, self.lab, self.dest, name, self.report)
        self.expect(True, name + "_snapshot_after_clean_stop")

    def close(self, compose):
        if self.linux is not None:
            self.linux.close(self.report)
            _cleanup(None, None, compose, self.report)
            self.report["ok"] = self.report["ok"] and self.report.get(
                "owned_game_clean_exit", False
            )
        else:
            _cleanup(self.server, self.stream, compose, self.report)


def run_recovery_lab(args):
    _validate_inputs(args)
    lab = PROJECT_ROOT / ".local" / ("recovery-lab-" + uuid4().hex[:8])
    lab.mkdir(parents=True)
    report = {
        "ok": False,
        "checks": [],
        "edge_cases": args.edge_cases,
        "full_backup_return": args.full_backup_return,
        "runtime": args.runtime,
        "lab_folder": str(lab.relative_to(PROJECT_ROOT)),
        "candidate": {
            "source": WORLDEDIT_SOURCE,
            "sha256": WORLDEDIT_SHA256,
            "version": "6.1.10",
            "mcmod_metadata": "6.1.10-SNAPSHOT;e6b38e8",
        },
        "scope": {
            "dimension": 0,
            "min": [130, 241, 130],
            "max": [135, 243, 134],
            "blocks": 90,
        },
    }
    compose = [
        "docker",
        "compose",
        "--project-name",
        "omk-recovery-" + uuid4().hex[:8],
        "-f",
        str(PROJECT_ROOT / "deploy/auth-lab/compose.yaml"),
    ]
    runtime = None

    def state(phase):
        (PROJECT_ROOT / ".local/recovery-status.json").write_text(
            json.dumps({"phase": phase, "report": report}), encoding="utf-8"
        )

    def expect(condition, label):
        if not condition:
            raise RuntimeError(label)
        report["checks"].append(label)
        state(label)

    try:
        state("preparing_fresh_recovery_lab")
        dest, mods, snapshots = _prepare_recovery_server(args, lab, report)
        client, _, session, session2 = _accounts(compose, lab)
        runtime = RecoveryRuntime(args, lab, dest, client, report, state, expect)
        if args.runtime == "linux-docker":
            from omk.recovery_linux_lab import LinuxRecovery  # noqa: PLC0415

            runtime.linux = LinuxRecovery(lab, compose[3] + "_default", snapshots)
            report["linux_java_runtime"] = runtime.linux.prepare(dest, args, client)
            expect(True, "linux_named_volume_case_sensitive_filesystem")

        _exercise(
            client,
            session,
            mods,
            runtime.start,
            runtime.backup,
            expect,
            report,
            snapshots=snapshots,
            edge_cases=args.edge_cases,
        )
        from omk.recovery_nbt_lab import verify_snapshot_tiles  # noqa: PLC0415

        verify_snapshot_tiles(snapshots, expect)
        if args.full_backup_return:
            from omk.recovery_full_probe_lab import (  # noqa: PLC0415
                exercise_full_return,
            )

            exercise_full_return(
                args,
                lab,
                runtime.server,
                client,
                (session, session2),
                mods,
                report,
                expect,
                runtime.start,
                runtime.backup,
            )
        report["ok"] = True
    except Exception as error:
        report["error"] = type(error).__name__ + ": " + str(error)[:1800]
        report["trace"] = [
            {"function": f.name, "line": f.lineno}
            for f in traceback.extract_tb(error.__traceback__)
        ]
    finally:
        if runtime is not None:
            runtime.close(compose)
        else:
            _cleanup(None, None, compose, report)
        (lab / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        state("complete" if report["ok"] else "failed")
    return report
