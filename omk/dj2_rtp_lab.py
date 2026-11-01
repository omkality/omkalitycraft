"""Real RTP dimension/surface/timer checks in a fresh Linux Docker world."""

import hashlib
import json
import time
from pathlib import Path
from uuid import uuid4

from omk.dj2_commands_lab import FIRST, SECOND, _hold, _near, _place, _response
from omk.dj2_lab import _accounts, _console_sender, _copy_server, _wait_server
from omk.dj2_linux_lab import JAVA_IMAGE, LinuxServer
from omk.dj2_rtp_policy import write_rtp_policy
from omk.forge_player import LabPlayer
from omk.operator_lab import _cleanup
from omk.profiles import PROJECT_ROOT


def add_rtp_lab(parser):
    for name in ("server-source", "agent", "core", "mods-json"):
        parser.add_argument("--" + name, type=Path, required=True)


class RtpScenario:
    def __init__(self, server, report):
        self.server, self.report = server, report
        self.console = None

    def state(self, phase):
        (PROJECT_ROOT / ".local/rtp-status.json").write_text(
            json.dumps({"phase": phase, "report": self.report}, ensure_ascii=False),
            encoding="utf-8",
        )

    def expect(self, ok, label):
        if not ok:
            raise RuntimeError(label)
        self.report["checks"].append(label)
        self.state(label)

    def has(self, actor, key):
        return any(
            key in json.dumps(m, ensure_ascii=False) for m in tuple(actor.messages)
        )

    def response(self, actor, cmd, key):
        actor.messages.clear()
        actor.command(cmd)
        try:
            actor.wait(lambda: self.has(actor, key))
        except RuntimeError:
            raise RuntimeError(
                "No response for "
                + cmd
                + "; "
                + json.dumps(list(actor.messages), ensure_ascii=False)[:1200]
            ) from None

    def at(self, name, command):
        # Console keeps authority; the actor supplies only the execution world.
        return self.console(f"execute {name} ~ ~ ~ {command}")

    def wait_loaded(self, name, x=0, z=0):
        # PlayerChunkMap queues surrounding chunks after a dimension transfer.
        # testforblock checks loaded state without generating the missing chunk.
        for dx, dz in ((-17, -17), (-17, 17), (17, -17), (17, 17)):
            deadline = time.monotonic() + 35
            while time.monotonic() < deadline:
                result = self.at(name, f"testforblock {x+dx} 1 {z+dz} minecraft:air")
                if "Successfully found" in result or "The block at" in result:
                    break
                time.sleep(0.1)
            else:
                raise RuntimeError("RTP fixture chunks did not finish loading")

    def transfer(self, actor, name, dim, x=24, y=241, z=24):
        if actor.dimension != dim:
            self.console(f"forge setdimension {name} {dim} {x} {y} {z}")
            actor.wait(lambda: actor.dimension == dim, timeout=40)
        _place(actor, name, (x + 0.5, y, z + 0.5), self.console)
        self.expect(
            "Found" in self.console(f"testfor {name} {{Dimension:{dim}}}"),
            "server_confirms_dimension_" + str(dim) + "_" + name,
        )

    def surface(self, actor, name, x=0, z=0, material="wool"):
        _place(actor, name, (x + 0.5, 241, z + 0.5), self.console)
        self.wait_loaded(name, x, z)
        self.at(name, f"fill {x-17} 244 {z-17} {x+17} 244 {z+17} minecraft:bedrock")
        self.at(name, f"fill {x-17} 245 {z-17} {x+17} 245 {z+17} minecraft:glass")
        self.at(name, f"fill {x-16} 245 {z-16} {x+16} 245 {z+16} minecraft:{material}")
        self.at(name, f"fill {x-16} 246 {z-16} {x+16} 253 {z+16} minecraft:air")
        self.expect(
            "Successfully found"
            in self.at(name, f"testforblock {x} 245 {z} minecraft:{material}"),
            "surface_fixture_" + material + "_dimension_" + str(actor.dimension),
        )

    def success(self, actor, name, dim, y, cx=0, cz=0):
        _place(actor, name, (cx + 24.5, 241, cz + 24.5), self.console)
        actor.messages.clear()
        start = time.monotonic()
        actor.command("/rtp")
        actor.wait(
            lambda: actor.position is not None and y <= actor.position[1] < y + 1,
            timeout=25,
        )
        x, actual_y, z = actor.position[:3]
        self.expect(
            time.monotonic() - start >= 2, "rtp_observes_ftb_warmup_" + str(dim)
        )
        self.expect(
            actor.dimension == dim
            and "Found" in self.console(f"testfor {name} {{Dimension:{dim}}}"),
            "rtp_keeps_invocation_world_" + str(dim),
        )
        distance = ((x - cx) ** 2 + (z - cz) ** 2) ** 0.5
        self.expect(8 <= distance <= 12, "rtp_lands_in_configured_annulus_" + str(dim))
        self.report["destinations"].append(
            {"dimension": dim, "position": [x, actual_y, z]}
        )

    def fail(self, actor, name, label, key="Безопасная точка"):
        _place(actor, name, (24.5, 241, 24.5), self.console)
        self.response(actor, "/rtp", key)
        self.expect(_near(actor, (24.5, 241, 24.5)), label + "_does_not_teleport")
        time.sleep(5.1)

    def basics(self, first):
        self.console("gamemode 1 " + FIRST)
        self.console("ranks setp player ftbutilities.rtp.warmup 3s")
        self.console("ranks setp player ftbutilities.rtp.cooldown 10s")
        self.surface(first, FIRST)
        self.success(first, FIRST, 0, 246)
        self.response(first, "/rtp", "Дождитесь")
        self.expect(True, "repeat_request_during_attempt_guard_rejected")
        time.sleep(2)
        self.response(first, "/rtp", "cant_use_now_cooldown")
        self.expect(True, "native_ftb_cooldown_is_preserved")
        time.sleep(8)
        self.console("ranks setp player ftbutilities.rtp.cooldown 0s")
        self.console("ranks setp player command.ftbutilities.rtp false")
        _response(first, "/rtp", "commands.generic.permission")
        self.expect(True, "native_ftb_permission_denial_is_preserved")
        self.console("ranks setp player command.ftbutilities.rtp true")

    def denials(self, first):
        self.surface(first, FIRST, material="water")
        self.fail(first, FIRST, "water_surface_rejected")
        self.surface(first, FIRST, material="stone_slab")
        self.fail(first, FIRST, "partial_floor_rejected")
        self.surface(first, FIRST)
        self.console("worldborder set 16")
        self.fail(first, FIRST, "too_small_border_rejected")
        self.console("worldborder set 60000000")
        _response(first, "/team create omklab", "ftblib.lang.team.created")
        for x, z in [(-8, -8), (-8, 8), (8, -8), (8, 8)]:
            _place(first, FIRST, (x + 0.5, 246.01, z + 0.5), self.console)
            first.command("/chunks claim")
            _response(first, "/chunks info", "omklab")
        self.fail(first, FIRST, "all_candidate_claims_rejected")
        first.command("/chunks unclaim_all")
        time.sleep(2)
        _place(first, FIRST, (8.5, 246.01, 8.5), self.console)
        _response(first, "/chunks info", "not_claimed")

    def center_and_movement(self, first):
        self.console("worldborder center 128 128")
        self.console("worldborder set 64")
        self.surface(first, FIRST, 128, 128)
        self.success(first, FIRST, 0, 246, 128, 128)
        time.sleep(5.1)
        self.console("worldborder center 0 0")
        self.console("worldborder set 60000000")
        _place(first, FIRST, (24.5, 241, 24.5), self.console)
        first.messages.clear()
        first.command("/rtp")
        time.sleep(0.3)
        first.move(26.5, 241, 24.5)
        first.wait(lambda: self.has(first, "stand_still_failed"))
        self.expect(True, "cross_block_movement_cancels_native_rtp_warmup")
        time.sleep(5.1)

    def dimensions(self, first):
        self.transfer(first, FIRST, -1, 0, 100, 0)
        self.wait_loaded(FIRST)
        self.at(FIRST, "fill -16 65 -16 16 65 16 minecraft:gold_block")
        self.at(FIRST, "fill -16 66 -16 16 90 16 minecraft:air")
        self.at(FIRST, "fill -16 91 -16 16 120 16 minecraft:air")
        self.at(FIRST, "fill -16 127 -16 16 127 16 minecraft:bedrock")
        self.expect(
            "Successfully found"
            in self.at(FIRST, "testforblock 0 127 0 minecraft:bedrock"),
            "nether_roof_positive_control_present",
        )
        self.expect(
            "Successfully found"
            in self.at(FIRST, "testforblock 0 65 0 minecraft:gold_block")
            and "Successfully found"
            in self.at(FIRST, "testforblock 0 66 0 minecraft:air"),
            "nether_floor_and_headroom_fixtures_exist",
        )
        self.success(first, FIRST, -1, 66)
        time.sleep(5.1)
        self.transfer(first, FIRST, 7)
        self.surface(first, FIRST)
        self.success(first, FIRST, 7, 246)
        time.sleep(5.1)
        first.messages.clear()
        first.command("/rtp")
        self.transfer(first, FIRST, 1)
        time.sleep(4)
        self.expect(
            first.dimension == 1 and _near(first, (24.5, 241, 24.5)),
            "dimension_change_during_warmup_never_returns_to_old_world",
        )
        self.response(first, "/rtp", "RTP недоступен")
        self.expect(first.dimension == 1, "end_story_world_denied_without_fallback")
        self.transfer(first, FIRST, -100)
        self.response(first, "/rtp", "RTP недоступен")
        self.expect(
            first.dimension == -100, "unlisted_registered_world_denied_without_fallback"
        )
        self.transfer(first, FIRST, 0)
        self.surface(first, FIRST)

    def disconnected(self, first, client, session2, mods):
        self.console("ranks setp player ftbutilities.rtp.cooldown 10s")
        with LabPlayer(client, session2, 25576, mods) as second:
            self.console("gamemode 1 " + SECOND)
            _place(second, SECOND, (24.5, 241, 24.5), self.console)
            second.command("/rtp")
            time.sleep(0.3)
        time.sleep(1)
        with LabPlayer(client, session2, 25576, mods) as second:
            _place(second, SECOND, (24.5, 241, 24.5), self.console)
            _hold(second, (24.5, 241, 24.5), 5)
            self.success(second, SECOND, 0, 246)
            self.expect(
                True, "disconnected_request_does_not_spend_new_connection_cooldown"
            )

    def ungenerated(self, first):
        self.console("save-all flush")
        listing = (
            "find /srv/lab-world/region -maxdepth 1 -type f -name '*.mca' "
            "-printf '%f\\n' | sort"
        )
        before = self.server.helper(listing).stdout
        self.expect("r.97.97.mca" not in before, "far_target_region_absent_control")
        self.console("worldborder center 50000 50000")
        self.fail(first, FIRST, "ungenerated_region_rejected")
        self.console("save-all flush")
        after = self.server.helper(listing).stdout
        self.expect(
            before == after, "rtp_does_not_create_region_files_for_absent_chunks"
        )
        self.console("worldborder center 0 0")

    def concurrent(self, first, client, session2, mods):
        self.console("ranks setp player ftbutilities.rtp.cooldown 0s")
        time.sleep(5.1)
        with LabPlayer(client, session2, 25576, mods) as second:
            self.transfer(second, SECOND, -1, 24, 100, 24)
            _place(first, FIRST, (24.5, 241, 24.5), self.console)
            started = time.monotonic()
            first.command("/rtp")
            second.command("/rtp")
            first.wait(lambda: 246 <= first.position[1] < 247, timeout=25)
            second.wait(lambda: 66 <= second.position[1] < 67, timeout=25)
            self.expect(
                first.dimension == 0 and second.dimension == -1,
                "simultaneous_rtp_keeps_two_independent_dimensions",
            )
            self.expect(
                time.monotonic() - started >= 2, "concurrent_requests_keep_warmup"
            )
            self.expect(
                "Found" in self.console(f"testfor {FIRST} {{Dimension:0}}")
                and "Found" in self.console(f"testfor {SECOND} {{Dimension:-1}}"),
                "server_independently_confirms_concurrent_worlds",
            )
            self.transfer(second, SECOND, 0)

    def run(self, client, session, session2, mods):
        with LabPlayer(client, session, 25576, mods) as first:
            self.basics(first)
            self.denials(first)
            self.ungenerated(first)
            self.center_and_movement(first)
            self.dimensions(first)
            self.disconnected(first, client, session2, mods)
            self.concurrent(first, client, session2, mods)
            # Let empty dimensions unload while the server is still running.
            time.sleep(5)


def run_rtp_lab(args):
    run = uuid4().hex[:10]
    lab = PROJECT_ROOT / ".local" / ("rtp-dimensions-" + run)
    lab.mkdir()
    project = "omk-rtp-" + run
    compose = [
        "docker",
        "compose",
        "--project-name",
        project,
        "-f",
        str(PROJECT_ROOT / "deploy/auth-lab/compose.yaml"),
    ]
    server = LinuxServer(lab, run, project + "_default")
    report = {
        "ok": False,
        "security_ready": False,
        "checks": [],
        "lab": lab.relative_to(PROJECT_ROOT).as_posix(),
        "core_sha256": hashlib.sha256(args.core.read_bytes()).hexdigest(),
        "java_image": JAVA_IMAGE,
        "destinations": [],
    }
    scenario = RtpScenario(server, report)
    try:
        scenario.state("preparing")
        client, _service, session, session2 = _accounts(compose, lab)
        dest, mods = _copy_server(args, lab)
        report["policy"] = write_rtp_policy(
            dest / "config",
            {"OMK_DJ2_RTP_MIN_DISTANCE": "8", "OMK_DJ2_RTP_MAX_DISTANCE": "12"},
        )
        server.prepare(dest, args, client)
        process = server.start()
        _wait_server(process, server.log, scenario.state)
        scenario.expect(
            "Omkality dimension RTP enabled" in server.log.read_text(encoding="utf-8"),
            "dimension_rtp_adapter_initialized",
        )
        scenario.console = _console_sender(process, server.log)
        scenario.run(client, session, session2, mods)
        report["ok"] = True
    except Exception as error:
        report["error_type"] = type(error).__name__
        report["error"] = str(error)[:1800]
    finally:
        server.close(report)
        report["auth_removed"] = _cleanup(None, None, compose)
        report["ok"] = (
            report["ok"]
            and report.get("owned_game_clean_exit", False)
            and report["auth_removed"]
        )
        (lab / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        scenario.state("complete")
    return report
