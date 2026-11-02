"""Owned Linux WR-CBE lifecycle lab; a separate private probe replays a late callback."""

import hashlib
import json
import shutil
import time
from pathlib import Path
from uuid import uuid4

from omk.dj2_commands_lab import FIRST, _place
from omk.dj2_lab import (
    _accounts,
    _console_sender,
    _copy_server,
    _wait_server,
    approved_mods,
)
from omk.dj2_linux_lab import (
    JAVA_IMAGE,
    LinuxServer,
    container_outcome,
    docker,
    forge_log_crashed,
    inspect_owned,
)
from omk.forge_player import LabPlayer
from omk.operator_lab import _cleanup
from omk.profiles import PROJECT_ROOT

PINS = {
    "wrcbe": (
        "WR-CBE-1.12.2-2.3.2.33-universal.jar",
        "a8305c42e29f43abbad906c3c91c36ed0a1a6f949ff2bff9eec66499fb57f36e",
    ),
    "mixinbooter": (
        "!mixinbooter-10.6.jar",
        "c74998ccd73e6722b2b1f0d236c7b9c0b34572a892a3810d5e49557d96a356bd",
    ),
    "probe": (None, "b214d2fb54496d4d400c610f36f0ff52755078aa2112ccee4fb5f919ea63508e"),
}


def add_wrcbe_lab(parser):
    for name in ("server-source", "agent", "core", "mods-json", "probe"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument(
        "--baseline",
        action="store_true",
        help="Expect the old WR shutdown callback to throw; use the old Core",
    )
    parser.add_argument(
        "--cycles", type=int, default=3, help="Owned stop/restart cycles, 1..5"
    )


def validate_inputs(args):
    if type(args.cycles) is not int or not 1 <= args.cycles <= 5:
        raise ValueError("WR lab cycles must be 1..5")
    for path in (
        args.agent,
        args.core,
        args.mods_json,
        args.server_source / "forge-1.12.2-14.23.5.2860.jar",
    ):
        if not path.is_file():
            raise ValueError("A required WR lab input is missing")
    approved_mods(args.mods_json)
    hashes = {}
    for label, (filename, expected) in PINS.items():
        path = (
            args.probe if filename is None else args.server_source / "mods" / filename
        )
        if (
            not path.is_file()
            or path.is_symlink()
            or path.stat().st_size > 16 * 1024**2
        ):
            raise ValueError("Missing or invalid pinned WR lab artifact")
        with path.open("rb") as file:
            actual = hashlib.file_digest(file, "sha256").hexdigest()
        if actual != expected:
            raise ValueError("WR lab artifact hash mismatch: " + label)
        hashes[label] = actual
    return hashes


class ProbeServer(LinuxServer):
    def command(self, **kwargs):
        command = super().command(**kwargs)
        command.insert(command.index("-Xms1G"), "-Domkality.lab.wrcbeProbe=true")
        return command


class WrcbeScenario:
    def __init__(self, server, report):
        self.server, self.report = server, report

    def state(self, phase):
        (PROJECT_ROOT / ".local/wrcbe-status.json").write_text(
            json.dumps({"phase": phase, "report": self.report}, ensure_ascii=False),
            encoding="utf-8",
        )

    def expect(self, ok, label):
        if not ok:
            raise RuntimeError(label)
        self.report["checks"].append(label)
        self.state(label)

    def result(self):
        raw = self.server.helper(
            "if test -f /srv/omk-wrcbe-probe.properties; then cat /srv/omk-wrcbe-probe.properties; fi"
        ).stdout
        if len(raw) > 8192:
            raise ValueError("Oversized WR lab probe response")
        return dict(
            line.split("=", 1)
            for line in raw.splitlines()
            if "=" in line and not line.startswith("#")
        )

    def request(self, operation):
        if operation not in {"setup", "check", "runtime-null"}:
            raise ValueError("Unknown WR lab probe operation")
        nonce = uuid4().hex[:10]
        # Both components are generated/allowlisted here, never player input.
        self.server.helper(
            "printf '%s' '" + nonce + ":" + operation + "' > /srv/omk-wrcbe-request.txt"
        )
        for _ in range(15):
            time.sleep(1)
            result = self.result()
            if result.get("request") == nonce:
                return result
            if self.server.process.poll() is not None:
                break
        raise RuntimeError("WR-CBE lab request did not complete")

    def check(self, result, on, cycle):
        self.expect(
            result.get("manager_present") == result.get("server_running") == "true",
            f"managers_live_cycle_{cycle}",
        )
        self.expect(
            result.get("live_start") == result.get("live_end") == "ok",
            f"native_live_start_end_cycle_{cycle}",
        )
        self.expect(
            result.get("tx_freq") == result.get("rx_freq") == "321",
            f"part_frequencies_cycle_{cycle}",
        )
        self.expect(
            result.get("tx_active") == result.get("rx_active") == str(on).lower(),
            f"wireless_power_{on}_cycle_{cycle}",
        )
        self.expect(
            result.get("frequency_name") == "omk-shutdown-lab",
            f"frequency_name_cycle_{cycle}",
        )

    def power(self, console, on):
        for x, z in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            console(
                f"setblock {x} 240 {z} minecraft:" + ("redstone_block" if on else "air")
            )
        time.sleep(2)

    def cycle(self, cycle, client, session, mods):
        self.state("starting_" + str(cycle))
        process = self.server.start()
        _wait_server(process, self.server.log, self.state)
        console = _console_sender(process, self.server.log)
        with LabPlayer(client, session, 25576, mods) as actor:
            console("gamemode 1 " + FIRST)
            _place(actor, FIRST, (4.5, 242, 4.5), console)
            if cycle == 0:
                console("fill -2 239 -2 10 239 2 minecraft:stone")
                self.check(self.request("setup"), False, cycle)
                self.power(console, True)
                self.check(self.request("check"), True, cycle)
                result = self.request("runtime-null")
                self.expect(
                    result.get("live_null_result") == "null_pointer_in_world_tick",
                    "live_null_fault_is_not_suppressed",
                )
                self.expect(
                    result.get("live_null_manager_restored") == "true",
                    "injected_live_null_manager_restored",
                )
                self.power(console, False)
                self.check(self.request("check"), False, cycle)
                self.power(console, True)
                self.check(self.request("check"), True, cycle)
            else:
                time.sleep(2)
                self.check(self.request("check"), True, cycle)
            console(f"forge setdimension {FIRST} -1 24 100 24")
            actor.wait(lambda: actor.dimension == -1, timeout=45)
            self.expect(
                "Found" in console(f"testfor {FIRST} {{Dimension:-1}}"),
                f"last_player_in_nether_cycle_{cycle}",
            )
        process.stdin.write(b"stop\n")
        process.stdin.flush()
        process.wait(timeout=80)
        self.server.collector.close()
        data = inspect_owned("container", self.server.name, self.server.run_id)
        outcome = container_outcome(data)
        self.expect(
            process.returncode == 0
            and not outcome["oom_killed"]
            and forge_log_crashed(self.server.log) is False,
            f"clean_native_shutdown_cycle_{cycle}",
        )
        result = self.result()
        count = int(result.get("shutdown_replays", "0"))
        self.expect(
            count > 0
            and result.get("shutdown_server_running")
            == result.get("shutdown_manager_present")
            == "false",
            f"real_disposed_manager_shutdown_context_cycle_{cycle}",
        )
        expected = "null_pointer_in_world_tick" if self.report["baseline"] else "ok"
        self.expect(
            all(
                result.get("shutdown_start_" + str(n)) == expected
                for n in range(1, count + 1)
            ),
            f"shutdown_start_callback_{expected}_cycle_{cycle}",
        )
        self.expect(
            all(
                result.get("shutdown_end_" + str(n)) == "ok"
                for n in range(1, count + 1)
            ),
            f"shutdown_end_callback_preserved_cycle_{cycle}",
        )
        shutil.copy2(self.server.log, self.server.lab / f"cycle-{cycle}.log")
        self.report["cycles"].append(
            {"cycle": cycle, "outcome": outcome, "probe": result}
        )


def run_wrcbe_lab(args):
    hashes = validate_inputs(args)
    run = uuid4().hex[:10]
    lab = PROJECT_ROOT / ".local" / ("wrcbe-shutdown-" + run)
    lab.mkdir()
    project = "omk-wrcbe-" + run
    compose = [
        "docker",
        "compose",
        "--project-name",
        project,
        "-f",
        str(PROJECT_ROOT / "deploy/auth-lab/compose.yaml"),
    ]
    server = ProbeServer(lab, run, project + "_default")
    report = {
        "ok": False,
        "security_ready": False,
        "baseline": args.baseline,
        "lab": lab.relative_to(PROJECT_ROOT).as_posix(),
        "checks": [],
        "cycles": [],
        "core_sha256": hashlib.sha256(args.core.read_bytes()).hexdigest(),
        "artifacts": hashes,
        "java_image": JAVA_IMAGE,
    }
    scenario = WrcbeScenario(server, report)
    try:
        scenario.state("preparing")
        client, _service, session, _session2 = _accounts(compose, lab)
        dest, mods = _copy_server(args, lab)
        shutil.copy2(args.probe, dest / "mods/OmkWrcbeLabProbe.jar")
        server.prepare(dest, args, client)
        for cycle in range(args.cycles):
            scenario.cycle(cycle, client, session, mods)
            if cycle < args.cycles - 1:
                docker("rm", server.name)
        report["ok"] = True
    except Exception as error:
        report["error_type"] = type(error).__name__
        report["error"] = str(error)[:1600]
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
