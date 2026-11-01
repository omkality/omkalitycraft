"""Disposable Linux Docker Forge server, optionally viewed by a real desktop client."""

import base64
import hashlib
import json
import shutil
import subprocess
import time
from pathlib import Path
from uuid import UUID, uuid4

from launcher.game import GameRunner
from launcher.install import current_platform
from launcher.log_policy import prepare_logging
from launcher.releases import inside, read_release
from launcher.skin_defaults import SKIN_ASSETS
from omk.diagnostics import BoundedLog, PipeLog
from omk.dj2_commands_lab import FIRST, SECOND, _place
from omk.dj2_lab import (
    _accounts,
    _console_sender,
    _copy_server,
    _stop_game,
    _wait_server,
    approved_mods,
)
from omk.forge_player import LabPlayer
from omk.logging_runtime import stage_logging_runtime
from omk.profiles import PROJECT_ROOT

JAVA_IMAGE = "eclipse-temurin:8-jre@sha256:377fe8e36a4b1530d9d52020069367ef44313fa891a82ae102b1016a6a3a72f5"
LABEL = "omkality.lab.run"


def docker(*args, timeout=60, check=True):
    result = subprocess.run(
        ["docker", *args], capture_output=True, text=True, timeout=timeout, check=False
    )
    if check and result.returncode:
        raise RuntimeError("Owned Docker lab operation failed: " + " ".join(args[:2]))
    return result


def inspect_owned(kind, name, run_id):
    result = docker(kind, "inspect", name, check=False)
    if result.returncode:
        return None
    data = json.loads(result.stdout)[0]
    labels = (
        data.get("Labels", {})
        if kind == "volume"
        else data.get("Config", {}).get("Labels", {})
    )
    if (labels or {}).get(LABEL) != run_id:
        raise ValueError("Refusing access to an unowned Docker resource")
    return data


class LinuxServer:
    def __init__(self, lab, run_id, network):
        self.lab, self.run_id, self.network = lab, run_id, network
        self.name = "omk-dj2-linux-" + run_id
        self.volume = self.name + "-data"
        self.volume_created = False
        self.process = self.collector = None
        self.log = lab / "server-output.log"

    def helper(self, script, *, source=None, export=None):
        arguments = [
            "run",
            "--rm",
            "--pull",
            "never",
            "--platform",
            "linux/amd64",
            "--name",
            self.name + "-helper",
            "--label",
            LABEL + "=" + self.run_id,
            "--mount",
            f"type=volume,source={self.volume},target=/srv",
        ]
        for path, target, readonly in [
            (source, "/seed", True),
            (export, "/export", False),
        ]:
            if path is not None:
                arguments += [
                    "--mount",
                    f"type=bind,source={path.resolve()},target={target}"
                    + (",readonly" if readonly else ""),
                ]
        return docker(
            *arguments, "--entrypoint", "/bin/sh", JAVA_IMAGE, "-c", script, timeout=180
        )

    def prepare(self, dest, args, client):
        if docker("volume", "inspect", self.volume, check=False).returncode == 0:
            raise ValueError("A new Docker volume is required")
        docker("volume", "create", "--label", LABEL + "=" + self.run_id, self.volume)
        self.volume_created = True
        inspect_owned("volume", self.volume, self.run_id)
        props = dest / "server.properties"
        props.write_text(props.read_text().replace("server-ip=127.0.0.1", "server-ip="))
        private = dest / ".omk"
        private.mkdir()
        for folder in ("tmp", "java-home"):
            (private / folder).mkdir()
        shutil.copy2(args.agent, private / "authlib-injector.jar")
        # Metadata is public (RSA verification key + texture domains), not an
        # account credential. Prefetch avoids the public loopback discovery
        # header redirecting the internal Docker server back to its own loopback.
        metadata = client.request("GET", "/authlib-injector")
        self.prefetched = base64.b64encode(json.dumps(metadata).encode()).decode(
            "ascii"
        )
        shutil.copy2(
            prepare_logging("1.12.2", self.lab / "logging"), private / "log4j2.xml"
        )
        jars = stage_logging_runtime(dest)
        self.classpath = ":".join(
            "/srv/" + p.relative_to(dest).as_posix() for p in jars
        )
        self.classpath += ":/srv/forge-1.12.2-14.23.5.2860.jar"
        self.helper(
            "set -eu; cp -a /seed/. /srv/; mkdir -p /srv/.omk/case-check; "
            "touch /srv/.omk/case-check/CaseFile; test ! -e /srv/.omk/case-check/casefile",
            source=dest,
        )
        result = self.helper("uname -s; java -version")
        return result.stdout + result.stderr

    def start(self):
        if docker("container", "inspect", self.name, check=False).returncode == 0:
            raise ValueError("A new Docker container is required")
        command = [
            "docker",
            "run",
            "--interactive",
            "--pull",
            "never",
            "--platform",
            "linux/amd64",
            "--name",
            self.name,
            "--label",
            LABEL + "=" + self.run_id,
            "--network",
            self.network,
            "--publish",
            "127.0.0.1:25576:25576",
            "--memory",
            "6g",
            "--cpus",
            "4",
            "--workdir",
            "/srv",
            "--log-driver",
            "local",
            "--log-opt",
            "max-size=10m",
            "--log-opt",
            "max-file=3",
            "--mount",
            f"type=volume,source={self.volume},target=/srv",
            JAVA_IMAGE,
            "java",
            "-Xms1G",
            "-Xmx4G",
            "-Dfile.encoding=UTF-8",
            "-Djava.io.tmpdir=/srv/.omk/tmp",
            "-Duser.home=/srv/.omk/java-home",
            "-javaagent:/srv/.omk/authlib-injector.jar=http://drasl:25585/authlib-injector",
            "-Dauthlibinjector.side=server",
            "-Dauthlibinjector.yggdrasil.prefetched=" + self.prefetched,
            "-Dauthlibinjector.noLogFile",
            "-Domkality.lab.commandCatalog=true",
            "-Dlog4j.configurationFile=file:/srv/.omk/log4j2.xml",
            "-cp",
            self.classpath,
            "net.minecraftforge.fml.relauncher.ServerLaunchWrapper",
            "nogui",
        ]
        writer = BoundedLog(self.log)
        writer.write("Starting pinned Linux Docker Forge server\n")
        self.process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        self.collector = PipeLog(self.process.stdout, writer)
        return self.process

    def close(self, report):
        try:
            if self.process is not None and self.process.poll() is None:
                try:
                    self.process.stdin.write(b"stop\n")
                    self.process.stdin.flush()
                    self.process.wait(timeout=60)
                except OSError, subprocess.TimeoutExpired:
                    if inspect_owned("container", self.name, self.run_id):
                        docker("stop", "--time", "30", self.name)
                    self.process.wait(timeout=40)
            data = inspect_owned("container", self.name, self.run_id)
            if data and data["State"]["Running"]:
                docker("stop", "--time", "30", self.name)
            if self.collector is not None:
                self.collector.close()
            if data and self.process.poll() == 0:
                exported = self.lab / "export"
                exported.mkdir()
                self.helper(
                    "test ! -e /export/world-after.tar && tar -C /srv -cf /export/world-after.tar lab-world",
                    export=exported,
                )
                with (exported / "world-after.tar").open("rb") as file:
                    report["stopped_world_tar_sha256"] = hashlib.file_digest(
                        file, "sha256"
                    ).hexdigest()
            if data:
                docker("rm", self.name)
            helper = inspect_owned("container", self.name + "-helper", self.run_id)
            if helper:
                docker("rm", "--force", self.name + "-helper")
            if self.volume_created and report.get("stopped_world_tar_sha256"):
                inspect_owned("volume", self.volume, self.run_id)
                docker("volume", "rm", self.volume)
                report["owned_volume_removed_after_export"] = True
            report["owned_game_clean_exit"] = (
                self.process is not None and self.process.poll() == 0
            )
        except Exception as error:
            report["ok"] = False
            report["cleanup_error"] = type(error).__name__
            # A failed export preserves the owned volume for investigation.
            report["owned_volume_retained"] = self.volume


def add_linux_skin_lab(parser):
    for name in ("server-source", "agent", "core", "mods-json"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--client-source", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--visual-seconds", type=int, default=900)


def clone_client(args, lab):
    keys = json.loads((PROJECT_ROOT / "launcher/assets/release-keys.json").read_text())
    release = read_release(args.manifest.read_bytes(), keys)
    if release.platform != current_platform():
        raise ValueError("The graphical client source must match this desktop OS")
    root, dest = lab / "client", lab / "client/instances/dj2"
    source_root = args.client_source / "instances/dj2"
    if not source_root.is_dir():
        source_root = args.client_source
    for artifact in release.files:
        source = inside(source_root, artifact.path)
        target = inside(dest, artifact.path)
        with source.open("rb") as file:
            if hashlib.file_digest(file, "sha256").hexdigest() != artifact.sha256:
                raise ValueError("Client source artifact does not match signed release")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return root, dest, release


def _visual_client(
    args,
    lab,
    server,
    client,
    service,
    session2,
    mods,
    console,
    report,
    state,
    passed,
    owned,
):
    state("cloning_only_signed_client_artifacts")
    root, folder, release = clone_client(args, lab)
    mark = server.log.stat().st_size
    owned["game"] = game = GameRunner(root).start(
        release,
        folder,
        service.renew_for_game(),
        server=("127.0.0.1", 25576),
        memory_mb=6144,
    )
    report["game_pid"] = game.process.pid
    report["client_folder"] = str(root.relative_to(PROJECT_ROOT))
    deadline = time.monotonic() + 900
    state("real_minecraft_loading")
    while time.monotonic() < deadline:
        if game.poll() is not None:
            raise RuntimeError("Graphical Minecraft exited before joining Linux server")
        with server.log.open("rb") as file:
            file.seek(mark)
            if (FIRST + " joined the game") in file.read().decode(
                "utf-8", errors="replace"
            ):
                break
        time.sleep(1)
    else:
        raise RuntimeError("Graphical Minecraft join timed out")
    passed("real_windows_dj2_client_joins_linux_docker_server")
    console("tp " + FIRST + " 128.5 241 128.5 180 0")
    state("ready_for_visual_checks")
    deadline = time.monotonic() + args.visual_seconds
    while (
        time.monotonic() < deadline
        and game.poll() is None
        and not (lab / "finish-visual-checks").exists()
    ):
        change = lab / "skin-next.json"
        if change.exists():
            skin = json.loads(change.read_text())
            if skin not in {"classic", "legacy", "slim"}:
                raise ValueError("Unknown owned test skin")
            owned["other"].__exit__(None, None, None)
            owned["other"] = None
            model = "slim" if skin == "slim" else "classic"
            client.upload_game_skin(
                UUID(session2.player_uuid).hex,
                session2.access_token,
                (SKIN_ASSETS / ("default-" + skin + ".png")).read_bytes(),
                model,
            )
            change.unlink()
            other = LabPlayer(client, session2, 25576, mods)
            other.__enter__()
            owned["other"] = other
            _place(other, SECOND, (131.5, 241, 128.5), console)
            console("tp " + SECOND + " 131.5 241 128.5 180 0")
            report["other_skin"] = skin
            state("ready_for_visual_checks")
        time.sleep(0.25)


def _protocol_setup(client, session, mods, console, passed):
    with LabPlayer(client, session, 25576, mods) as first:
        _place(first, FIRST, (128.5, 241, 128.5), console)
        console("fill 124 240 124 140 240 136 minecraft:bedrock")
        console("fill 124 241 124 140 245 136 minecraft:air")
        passed("real_forge_login_to_linux_server")
    console("time set 6000")
    console("gamerule doDaylightCycle false")
    console("weather clear")


def run_linux_skin_lab(args):
    if (
        bool(args.client_source) != bool(args.manifest)
        or not 0 <= args.visual_seconds <= 1800
    ):
        raise ValueError(
            "Provide matching client-source/manifest and a bounded visual duration"
        )
    run_id = uuid4().hex[:10]
    lab = PROJECT_ROOT / ".local" / ("linux-skin-lab-" + run_id)
    lab.mkdir()
    report = {
        "ok": False,
        "checks": [],
        "lab_folder": str(lab.relative_to(PROJECT_ROOT)),
        "java_image": JAVA_IMAGE,
    }
    compose = [
        "docker",
        "compose",
        "--project-name",
        "omk-linux-" + run_id,
        "-f",
        str(PROJECT_ROOT / "deploy/auth-lab/compose.yaml"),
    ]
    server = LinuxServer(lab, run_id, "omk-linux-" + run_id + "_default")
    owned = {"game": None, "other": None}

    def state(phase):
        (PROJECT_ROOT / ".local/linux-skin-status.json").write_text(
            json.dumps({"phase": phase, "report": report}), "utf-8"
        )

    def passed(label):
        report["checks"].append(label)
        state(label)

    try:
        approved_mods(args.mods_json)
        state("preparing_owned_linux_volume")
        dest, mods = _copy_server(args, lab)
        client, service, session, session2 = _accounts(compose, lab)
        report["java_runtime"] = server.prepare(dest, args, client)
        passed("linux_named_volume_case_sensitive_filesystem")
        process = server.start()
        _wait_server(process, server.log, state)
        passed("full_forge_dj2_starts_in_linux_docker")
        console = _console_sender(process, server.log)
        _protocol_setup(client, session, mods, console, passed)
        client.upload_game_skin(
            UUID(session2.player_uuid).hex,
            session2.access_token,
            (SKIN_ASSETS / "default-classic.png").read_bytes(),
            "classic",
        )
        other = LabPlayer(client, session2, 25576, mods)
        other.__enter__()
        owned["other"] = other
        _place(other, SECOND, (131.5, 241, 128.5), console)
        console("tp " + SECOND + " 131.5 241 128.5 180 0")
        if args.client_source:
            _visual_client(
                args,
                lab,
                server,
                client,
                service,
                session2,
                mods,
                console,
                report,
                state,
                passed,
                owned,
            )
        report["ok"] = True
    except Exception as error:
        report["error"] = type(error).__name__ + ": " + str(error)[:400]
    finally:
        _stop_game(owned["game"])
        if owned["other"] is not None:
            owned["other"].__exit__(None, None, None)
        server.close(report)
        result = subprocess.run(
            [*compose, "down", "--timeout", "5"],
            capture_output=True,
            timeout=40,
            check=False,
        )
        report["temporary_auth_removed"] = result.returncode == 0
        report["ok"] = (
            report["ok"]
            and report["temporary_auth_removed"]
            and report.get("owned_game_clean_exit", False)
        )
        (lab / "report.json").write_text(json.dumps(report, indent=2), "utf-8")
        state("complete" if report["ok"] else "failed")
    return report
