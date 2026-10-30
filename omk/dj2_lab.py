"""Explicit, disposable DJ2 integration lab. Never copies old worlds or server credentials."""

import argparse
import json
import os
import re
import secrets
import shutil
import subprocess
import time
import traceback
from contextlib import ExitStack
from pathlib import Path
from uuid import uuid4

from launcher.accounts import AccountService
from launcher.game import GameRunner
from launcher.log_policy import prepare_logging
from launcher.releases import read_release
from launcher.storage import FileSessionStore
from omk.diagnostics import BoundedLog, PipeLog
from omk.drasl import DraslClient
from omk.forge_player import LabPlayer
from omk.lab import skin_fixture
from omk.logging_runtime import stage_logging_runtime
from omk.profiles import PROJECT_ROOT


def approved_mods(path):
    with path.open("rb") as file:
        raw = file.read(65537)
    if len(raw) > 65536:
        raise ValueError("Approved mod list too large")
    values = json.loads(raw)
    if not isinstance(values, dict) or not 1 <= len(values) <= 1000:
        raise ValueError("Invalid approved mod list")
    for key, value in values.items():
        if (
            not isinstance(key, str)
            or re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", key) is None
            or not isinstance(value, str)
            or len(value) > 100
            or any(c in value for c in "\\\r\n")
        ):
            raise ValueError("Invalid approved mod entry")
    return values


def add_dj2_lab(parser):
    for flag in ["server-source", "java", "agent", "core", "mods-json"]:
        parser.add_argument("--" + flag, type=Path, required=True)
    parser.add_argument("--client-root", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--visual-seconds", type=int, default=0)


def _validate(args):
    if (
        bool(args.client_root) != bool(args.manifest)
        or not 0 <= args.visual_seconds <= 600
    ):
        raise ValueError(
            "Provide both client-root and manifest; visual-seconds must be 0..600"
        )
    for path in [
        args.java,
        args.agent,
        args.core,
        args.mods_json,
        args.server_source / "forge-1.12.2-14.23.5.2860.jar",
    ]:
        if not path.is_file():
            raise ValueError("A required lab input file is missing")
    approved_mods(args.mods_json)


def _copy_server(args, lab):
    source = args.server_source.resolve()
    dest = lab / "server"
    dest.mkdir()
    for name in [
        "mods",
        "config",
        "scripts",
        "libraries",
        "structures",
        "patchouli_books",
        "astralsorcery",
        "resources",
        "asm",
        "vintagefix",
    ]:
        folder = source / name
        if folder.exists():
            shutil.copytree(
                folder,
                dest / name,
                ignore=lambda folder, names: {
                    n
                    for n in names
                    if "omkality" in n.lower() or n.lower().endswith(".log")
                },
            )
    for name in [
        "forge-1.12.2-14.23.5.2860.jar",
        "minecraft_server.1.12.2.jar",
        "log4j2.xml",
        "LICENSE",
    ]:
        if (source / name).exists():
            shutil.copy2(source / name, dest / name)
    shutil.copy2(args.core.resolve(), dest / "mods/OmkalityCore.jar")
    mods = approved_mods(args.mods_json)
    assert all("\n" not in v and "\\" not in v for v in mods.values())
    (dest / "config/omkalitycore-mods.properties").write_text(
        "".join(k + "=" + v + "\n" for k, v in sorted(mods.items())),
        encoding="utf-8",
    )
    cfg = dest / "config/ftbutilities.cfg"
    cfg.write_text(
        cfg.read_text()
        .replace("rtp_max_distance=100000.0", "rtp_max_distance=96.0")
        .replace("rtp_min_distance=1000.0", "rtp_min_distance=64.0"),
        encoding="utf-8",
    )
    (dest / "local/ftbutilities").mkdir(parents=True, exist_ok=True)
    shutil.copy2(
        PROJECT_ROOT / "profiles/server-defaults/dj2/ftbutilities-ranks.txt",
        dest / "local/ftbutilities/ranks.txt",
    )
    (dest / "eula.txt").write_text("eula=true\n")
    (dest / "server.properties").write_text(
        "online-mode=true\nserver-ip=127.0.0.1\nserver-port=25576\n"
        "enable-rcon=false\nview-distance=3\nspawn-protection=0\nmax-tick-time=0\n"
        "motd=Disposable OmkalityCraft auth test\nlevel-name=lab-world\ngenerate-structures=false\n"
    )
    return dest, mods


def _accounts(compose, lab):
    subprocess.run(
        [*compose, "up", "--detach", "--pull", "never"],
        capture_output=True,
        check=True,
        timeout=60,
    )
    client = DraslClient("http://127.0.0.1:25586")
    for _ in range(60):
        try:
            client.request("GET", "/authlib-injector")
            break
        except Exception:
            time.sleep(0.2)
    logs = subprocess.check_output([*compose, "logs", "--no-color", "drasl"], text=True)
    invitation = re.search(r"invite=([A-Za-z0-9_-]+)", logs)[1]
    admin = client.register("omk_lab_admin", secrets.token_urlsafe(24), invitation)
    invite = client.request("POST", "/drasl/api/v3/invites", {}, admin["apiToken"])[
        "code"
    ]
    service = AccountService(client, FileSessionStore(lab / "account/session.json"))
    actor = service.prepare_registration("omk_game_test", invite)
    session = service.register(actor).session
    invite2 = client.request("POST", "/drasl/api/v3/invites", {}, admin["apiToken"])[
        "code"
    ]
    service2 = AccountService(client, FileSessionStore(lab / "account2/session.json"))
    actor2 = service2.prepare_registration("omk_other_test", invite2)
    session2 = service2.register(actor2).session
    return client, service, session, session2


def _start_server(args, lab, dest, client):
    # No passwords or management credentials are written to status/report files.
    java = args.java.resolve()
    agent = args.agent.resolve()
    (lab / "tmp").mkdir()
    (lab / "java-home").mkdir()
    server_log = lab / "server-output.log"
    writer = BoundedLog(server_log)
    writer.write("Starting isolated Forge server\n")
    logging = prepare_logging("1.12.2", lab / "logging")
    logging_jars = stage_logging_runtime(dest)
    server = subprocess.Popen(
        [
            str(java),
            "-Xms1G",
            "-Xmx4G",
            "-Dfile.encoding=UTF-8",
            f'-Djava.io.tmpdir={lab / "tmp"}',
            f'-Duser.home={lab / "java-home"}',
            f"-javaagent:{agent}={client.base_url}/authlib-injector",
            "-Dauthlibinjector.side=server",
            "-Domkality.lab.commandCatalog=true",
            f"-Dlog4j.configurationFile={logging.as_uri()}",
            "-cp",
            os.pathsep.join(
                [
                    *(str(p) for p in logging_jars),
                    str(dest / "forge-1.12.2-14.23.5.2860.jar"),
                ]
            ),
            "net.minecraftforge.fml.relauncher.ServerLaunchWrapper",
            "nogui",
        ],
        cwd=dest,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    return server, server_log, PipeLog(server.stdout, writer)


def _wait_server(server, server_log, state):
    deadline = time.monotonic() + 900
    while time.monotonic() < deadline:
        if server.poll() is not None:
            raise RuntimeError("Forge server exited during loading")
        log = server_log.read_text(encoding="utf-8", errors="replace")
        if "LoaderExceptionModCrash" in log:
            raise RuntimeError("Forge mod startup failed; inspect isolated log")
        if re.search(r"Done \([\d.,]+s\)!", log):
            break
        state("forge_server_loading")
        time.sleep(2)
    else:
        raise RuntimeError("Forge startup timed out")
    time.sleep(15)


def _console_sender(server, server_log):
    def console(command):
        mark = server_log.stat().st_size
        server.stdin.write((command + "\n").encode())
        server.stdin.flush()
        time.sleep(0.5)
        with server_log.open("rb") as output:
            output.seek(mark)
            return output.read().decode("utf-8", errors="replace")

    return console


def _response(player, command, key):
    player.messages.clear()
    player.command(command)
    try:
        player.wait(lambda: any(key in json.dumps(m) for m in player.messages))
    except RuntimeError:
        raise RuntimeError("No expected response for lab command " + command) from None


def _check_homes(first, console, expect):
    console("fill 0 78 0 15 78 15 minecraft:stone")
    console("tp omk_game_test 8.5 79 8.5")
    first.wait(lambda: abs(first.position[0] - 8.5) < 1)
    for name in ["one", "two", "three"]:
        _response(first, "/sethome " + name, "ftbutilities.lang.homes.set")
    _response(first, "/sethome four", "ftbutilities.lang.homes.limit")
    expect(True, "three_homes_allowed_and_fourth_denied_for_normal_player")
    for command in [
        "/fly",
        "/god",
        "/op omk_game_test",
        "/setwarp denied",
        "/home list omk_other_test",
    ]:
        _response(first, command, "commands.generic.permission")
    expect(
        True,
        "normal_player_cannot_fly_god_op_manage_global_warps_or_read_others_homes",
    )
    console("fill 120 78 120 135 78 135 minecraft:stone")
    console("tp omk_game_test 128.5 79 128.5")
    first.wait(lambda: abs(first.position[0] - 128.5) < 1)
    first.command("/home one")
    first.wait(lambda: abs(first.position[0] - 8.5) < 1.5)
    expect(True, "home_command_really_teleports_player_after_warmup")


def _check_claims(first, second, console, expect):
    _response(first, "/team create omklab", "ftblib.lang.team.created")
    console("tp omk_other_test 8.5 79 8.5")
    second.wait(lambda: abs(second.position[0] - 8.5) < 1)
    # Creative mode is a lab-only positive control; both users remain non-OP.
    console("gamemode 1 omk_game_test")
    console("gamemode 1 omk_other_test")
    console("setblock 9 79 8 minecraft:stone")
    second.dig(9, 79, 8)
    time.sleep(0.8)
    found = console("testforblock 9 79 8 minecraft:air")
    expect(
        "Successfully found" in found,
        "non_owner_can_break_unclaimed_test_block_positive_control",
    )
    first.command("/chunks claim")
    time.sleep(1)
    console("setblock 9 79 8 minecraft:stone")
    second.dig(9, 79, 8)
    time.sleep(0.8)
    found = console("testforblock 9 79 8 minecraft:stone")
    expect("Successfully found" in found, "ftb_claim_blocks_non_owner_block_break")
    first.dig(9, 79, 8)
    time.sleep(0.8)
    found = console("testforblock 9 79 8 minecraft:air")
    expect("Successfully found" in found, "ftb_claim_allows_owner_block_break")


def _check_guard(client, session, mods, expect):
    for name, bad in [
        ("extra", dict(mods, omk_lab_extra="1.0")),
        ("missing", {k: v for k, v in mods.items() if k != "ftbutilities"}),
        ("version", {**mods, "ftbutilities": "0.0-lab"}),
    ]:
        try:
            with LabPlayer(client, session, 25576, bad):
                pass
        except RuntimeError as error:
            expect(
                "Server kick" in str(error),
                "server_guard_rejects_" + name + "_declared_mod_list",
            )
        else:
            raise RuntimeError("Guard accepted " + name + " mod list")


def _real_client(args, lab, server_log, service, state, expect, report):
    # Verify the real graphical client still joins with the rewritten private core.
    portable = args.client_root.resolve()
    installed = portable / "instances/dj2"
    keys = json.loads((PROJECT_ROOT / "launcher/assets/release-keys.json").read_text())
    release = read_release(args.manifest.read_bytes(), keys)
    service.upload_skin(skin_fixture(), "classic")
    mark = server_log.stat().st_size
    game = GameRunner(portable).start(
        release,
        installed,
        service.renew_for_game(),
        server=("127.0.0.1", 25576),
        memory_mb=6144,
    )
    try:
        state("real_minecraft_loading")
        deadline = time.monotonic() + 900
        while time.monotonic() < deadline:
            if game.poll() is not None:
                raise RuntimeError("Real Minecraft exited before joining")
            with server_log.open("rb") as output:
                output.seek(mark)
                newlog = output.read().decode("utf-8", errors="replace")
            if "omk_game_test joined the game" in newlog:
                break
            time.sleep(2)
        else:
            raise RuntimeError("Real Minecraft join timed out")
        expect(True, "real_dj2_client_joins_with_rewritten_private_omkalitycore")
        report["game_pid"] = game.process.pid
        state("ready_for_visual_checks")
        deadline = time.monotonic() + args.visual_seconds
        while (
            time.monotonic() < deadline
            and game.poll() is None
            and not (lab / "finish-visual-checks").exists()
        ):
            time.sleep(1)
    finally:
        _stop_game(game)


def _stop_game(game):
    if game is not None and game.poll() is None:
        game.process.terminate()
        try:
            game.process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            game.process.kill()
            game.process.wait(timeout=10)


def _stop_server(server):
    if server is None or server.poll() is not None:
        return
    try:
        server.stdin.write(b"stop\n")
        server.stdin.flush()
        server.wait(timeout=40)
    except OSError, subprocess.TimeoutExpired:
        server.terminate()
        try:
            server.wait(timeout=15)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=10)


def _cleanup(server, stream, compose, report):
    try:
        _stop_server(server)
    except OSError, subprocess.SubprocessError:
        report["ok"] = False
        report["cleanup_error"] = "Failed to stop the owned lab server"
    finally:
        try:
            if stream is not None:
                stream.close()
        except OSError:
            report["ok"] = False
            report["log_collection_failed"] = True
        try:
            result = subprocess.run(
                [*compose, "down", "--timeout", "5"],
                capture_output=True,
                timeout=30,
                check=False,
            )
            report["temporary_auth_removed"] = result.returncode == 0
        except OSError, subprocess.SubprocessError:
            report["temporary_auth_removed"] = False
        if not report["temporary_auth_removed"]:
            report["ok"] = False


def _protocol_tests(client, session, session2, mods, server, server_log, expect):
    console = _console_sender(server, server_log)
    with ExitStack() as stack:
        first = stack.enter_context(LabPlayer(client, session, 25576, mods))
        second = stack.enter_context(LabPlayer(client, session2, 25576, mods))
        expect(
            first.position is not None and second.position is not None,
            "two_authenticated_protocol_players_complete_real_forge_handshake",
        )
        expect(
            f"Loaded strict client mod policy: {len(mods)} entries"
            in server_log.read_text(encoding="utf-8", errors="replace"),
            "private_server_core_loaded_explicit_client_policy",
        )
        _check_homes(first, console, expect)
        _check_claims(first, second, console, expect)
    _check_guard(client, session, mods, expect)


def run_dj2_lab(args: argparse.Namespace) -> dict:
    _validate(args)
    lab = PROJECT_ROOT / ".local" / ("ftb-guard-lab-" + uuid4().hex[:8])
    lab.mkdir(parents=True)
    report = {
        "ok": False,
        "checks": [],
        "lab_folder": str(lab.relative_to(PROJECT_ROOT)),
        "logging_runtime": "2.25.5",
    }
    compose = [
        "docker",
        "compose",
        "--project-name",
        "omk-forge-lab-" + uuid4().hex[:8],
        "-f",
        str(PROJECT_ROOT / "deploy/auth-lab/compose.yaml"),
    ]
    server = stream = None

    def state(phase):
        (PROJECT_ROOT / ".local/ftb-guard-status.json").write_text(
            json.dumps({"phase": phase, "report": report}), encoding="utf-8"
        )

    def expect(condition, label):
        if not condition:
            raise RuntimeError(label)
        report["checks"].append(label)
        state(label)

    try:
        state("preparing_isolated_server")
        dest, mods = _copy_server(args, lab)
        client, service, session, session2 = _accounts(compose, lab)
        server, server_log, stream = _start_server(args, lab, dest, client)
        _wait_server(server, server_log, state)
        catalog = server_log.parent / "omk-command-catalog.json"
        if catalog.is_file():
            metadata = json.loads(catalog.read_text(encoding="utf-8"))
            report["command_catalog"] = {
                "file": str(catalog.relative_to(PROJECT_ROOT)),
                "commands": len(metadata["commands"]),
                "rank_configs": len(metadata["rank_configs"]),
            }
        _protocol_tests(client, session, session2, mods, server, server_log, expect)
        if args.client_root is not None:
            _real_client(args, lab, server_log, service, state, expect, report)
        report["ok"] = True
    except Exception as error:
        report["error"] = type(error).__name__ + ": " + str(error)[:900]
        report["trace"] = [
            {"function": f.name, "line": f.lineno}
            for f in traceback.extract_tb(error.__traceback__)
        ]
    finally:
        _cleanup(server, stream, compose, report)
        (lab / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        state("complete" if report["ok"] else "failed")
    return report
