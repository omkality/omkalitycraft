"""Real FTB spawn boundary/restart checks on a fresh Linux Docker world only."""

import hashlib
import json
import time
from pathlib import Path
from uuid import uuid4

from omk.dj2_claims_lab import _block
from omk.dj2_commands_lab import FIRST, SECOND, _place, _response
from omk.dj2_explosions_lab import _tnt
from omk.dj2_graves_lab import check_graves
from omk.dj2_lab import _accounts, _console_sender, _copy_server, _wait_server
from omk.dj2_linux_lab import JAVA_IMAGE, LinuxServer, docker, inspect_owned
from omk.dj2_spawn_policy import write_spawn_policy
from omk.forge_player import LabPlayer
from omk.operator_lab import _cleanup
from omk.profiles import PROJECT_ROOT


def add_spawn_lab(parser):
    for name in ("server-source", "agent", "core", "mods-json"):
        parser.add_argument("--" + name, type=Path, required=True)


def check_boundary(actor, console, expect, x, z, protected, label):
    # Console creates fixture; ordinary non-OP creative actor actually edits it.
    _place(actor, FIRST, (x + 0.5, 241, z + 2.5), console)
    console(f"fill {x-2} 240 {z-2} {x+2} 240 {z+2} minecraft:bedrock")
    console(f"fill {x-2} 241 {z-2} {x+2} 244 {z+2} minecraft:air")
    expect(_block(console, x, 240, z, "bedrock"), label + "_platform_exists")
    # Underground Biomes replaces vanilla stone even at these high lab positions.
    console(f"setblock {x} 241 {z} minecraft:wool")
    expect(_block(console, x, 241, z, "wool"), label + "_dig_fixture_exists")
    actor.dig(x, 241, z)
    time.sleep(0.6)
    expect(_block(console, x, 241, z, "wool" if protected else "air"), label + "_dig")
    console(f"setblock {x} 241 {z} minecraft:air")
    console("replaceitem entity " + FIRST + " slot.hotbar.0 minecraft:wool 64")
    actor.select_hotbar(0)
    actor.use_block(x, 240, z)
    time.sleep(0.6)
    expect(
        _block(console, x, 241, z, "air" if protected else "wool"),
        label + "_place",
    )


def _first_boot_checks(first, second, console, expect):
    for x, z, p, label in [
        (0, 0, True, "origin"),
        (300, 0, True, "requested_positive_edge"),
        (-300, 0, True, "requested_negative_edge"),
        (303, 0, True, "aligned_positive_edge"),
        (-304, 0, True, "aligned_negative_edge"),
        (304, 0, False, "outside_positive_control"),
        (-305, 0, False, "outside_negative_control"),
        (300, 300, True, "requested_corner"),
        (0, 300, True, "positive_z_edge"),
        (0, -300, True, "negative_z_edge"),
    ]:
        check_boundary(first, console, expect, x, z, p, label)
    _place(first, FIRST, (8.5, 241, 8.5), console)
    first.command("/chunks claim")
    _response(first, "/chunks info", "OmkalityCraft spawn")
    expect(True, "player_cannot_take_spawn_claim")
    first.command("/chunks unclaim")
    _response(first, "/chunks info", "OmkalityCraft spawn")
    expect(True, "player_cannot_unclaim_server_spawn")
    _response(second, "/team join omk_spawn", "ftblib.lang.team.error.not_member")
    expect(True, "player_cannot_join_server_team")
    _place(first, FIRST, (408.5, 241, 8.5), console)
    first.command("/chunks claim")
    _response(first, "/chunks info", "omklab")
    expect(True, "personal_quota_remains_available_outside_spawn")
    _place(first, FIRST, (302.5, 241, 8.5), console)
    console("setblock 303 241 8 minecraft:wool")
    console("setblock 304 241 8 minecraft:wool")
    _tnt(console, 304.0, 242.5, 8.5)
    expect(
        _block(console, 303, 241, 8, "wool") and _block(console, 304, 241, 8, "air"),
        "outside_tnt_preserves_spawn_and_breaks_unclaimed_control",
    )


def _boot(server, report, state, expect):
    state("starting_owned_linux_server")
    process = server.start()
    report["boot_count"] += 1
    _wait_server(process, server.log, state)
    expect(
        "Omkality spawn claims verified: 1444"
        in server.log.read_text(encoding="utf-8"),
        "boot_" + str(report["boot_count"]) + "_all_1444_server_claims_verified",
    )
    return _console_sender(process, server.log)


def _stop_checkpoint(server, report, expect):
    server.process.stdin.write(b"stop\n")
    server.process.stdin.flush()
    server.process.wait(timeout=60)
    server.collector.close()
    data = inspect_owned("container", server.name, server.run_id)
    expect(
        data["State"]["ExitCode"] == 0 and not data["State"]["OOMKilled"],
        "boot_" + str(report["boot_count"]) + "_clean_stop_no_oom",
    )
    docker("rm", server.name)


def _check_operators(server, report, expect, label, console):
    ops = json.loads(server.helper("cat /srv/ops.json").stdout)
    report["operator_entries"] = [
        {"name": item.get("name"), "level": item.get("level")} for item in ops
    ]
    # Exact fixture observed in pinned PlaneFix 1.0.0 bytecode. Never silently
    # remove a human operator. This is only the disposable lab, not pack policy.
    expect(
        all(
            item.get("name") == "[Minecraft]"
            and item.get("uuid", "").lower() == "41c82c87-7afb-4024-ba57-13d2c99cae77"
            and item.get("level") == 4
            for item in ops
        ),
        label + "_no_human_or_unknown_operators",
    )
    if ops:
        console("deop [Minecraft]")
    expect(json.loads(server.helper("cat /srv/ops.json").stdout) == [], label)


def run_spawn_lab(args):
    run_id = uuid4().hex[:10]
    lab = PROJECT_ROOT / ".local" / ("spawn-policy-" + run_id)
    lab.mkdir()
    project = "omk-spawn-" + run_id
    compose = [
        "docker",
        "compose",
        "--project-name",
        project,
        "-f",
        str(PROJECT_ROOT / "deploy/auth-lab/compose.yaml"),
    ]
    server = LinuxServer(lab, run_id, project + "_default")
    report = {
        "ok": False,
        "security_ready": False,
        "lab": lab.relative_to(PROJECT_ROOT).as_posix(),
        "checks": [],
        "core_sha256": hashlib.sha256(args.core.read_bytes()).hexdigest(),
        "linux_java_image": JAVA_IMAGE,
        "boot_count": 0,
    }

    def state(phase):
        (PROJECT_ROOT / ".local/spawn-policy-status.json").write_text(
            json.dumps({"phase": phase, "report": report}, ensure_ascii=False),
            encoding="utf-8",
        )

    def expect(ok, label):
        if not ok:
            raise RuntimeError(label)
        report["checks"].append(label)
        state(label)

    try:
        state("preparing_owned_lab")
        client, _service, session, session2 = _accounts(compose, lab)
        dest, mods = _copy_server(args, lab)
        report["spawn_plan"] = write_spawn_policy(dest / "config", {})
        (dest / "ops.json").write_text("[]\n", encoding="ascii")
        server.prepare(dest, args, client)
        console = _boot(server, report, state, expect)
        with (
            LabPlayer(client, session, 25576, mods) as first,
            LabPlayer(client, session2, 25576, mods) as second,
        ):
            for name in (FIRST, SECOND):
                console("gamemode 1 " + name)
            _check_operators(server, report, expect, "operator_list_empty", console)
            _response(first, "/team create omklab", "ftblib.lang.team.created")
            _first_boot_checks(first, second, console, expect)
            check_graves(first, second, console, expect)
            console("save-all flush")
        _stop_checkpoint(server, report, expect)
        # Keep checkpoint logs separate; BoundedLog rotates on start anyway.
        console = _boot(server, report, state, expect)
        expect(
            "1444 existing" in server.log.read_text(encoding="utf-8"),
            "restart_is_idempotent_no_duplicate_claims",
        )
        with LabPlayer(client, session, 25576, mods) as first:
            console("gamemode 1 " + FIRST)
            check_boundary(first, console, expect, 0, 0, True, "restart_origin")
            _place(first, FIRST, (408.5, 241, 8.5), console)
            _response(first, "/chunks info", "omklab")
            expect(True, "restart_preserves_personal_claim")
            _check_operators(
                server, report, expect, "restart_operator_list_still_empty", console
            )
        report["ok"] = True
    except Exception as error:
        report["error_type"] = type(error).__name__
        report["error"] = str(error)[:1500]
    finally:
        server.close(report)
        report["auth_removed"] = _cleanup(None, None, compose)
        (lab / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        state("complete")
    return report
