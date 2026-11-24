"""Start only a verified release, keep paths local, and redact credential output."""

import contextlib
import os
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID, uuid4

import psutil

from launcher.pack.client_defaults import prepare_client_defaults
from launcher.pack.log_policy import prepare_logging, prune_game_logs
from launcher.pack.mod_policy import clean_extra_mods, verify_mods
from launcher.releases import Release, ReleaseError, inside
from launcher.session import Session
from launcher.version import VERSION
from omk.observability.diagnostics import (
    BoundedLog,
    collect_output,
    environment_snapshot,
    event,
    failure,
)
from omk.observability.incidents import (
    RunningCrashWatcher,
    capture_incident,
    crash_fingerprints,
)
from omk.shared.fs import resolved


def _is_pack_process(arguments: list[str], release: Release) -> bool:
    try:
        classpath = arguments.index("-cp")
    except ValueError:
        return False
    if arguments[classpath + 2 : classpath + 3] != [release.launch["main_class"]]:
        return False
    options = arguments[1:classpath]
    crash_path = next(
        (
            arg.removeprefix("-XX:ErrorFile=")
            for arg in options
            if arg.startswith("-XX:ErrorFile=")
        ),
        "",
    )
    crash = Path(crash_path)
    instance = crash.parent
    return (
        crash.is_absolute()
        and crash.name == "hs_err_pid%p.log"
        and instance.name == release.pack_id
        and instance.parent.name == "instances"
        and "-Dauthlibinjector.side=client" in options
        and f"-Duser.home={instance.parent.parent / 'userdata/java-home'}" in options
    )


@dataclass
class GameProcess:
    """Track the child process and the completion of its diagnostic capture."""

    process: subprocess.Popen = field(repr=False)
    log_path: Path
    folder: Path
    diagnostics_done: threading.Event = field(
        default_factory=threading.Event, repr=False
    )
    logging_failed: threading.Event = field(default_factory=threading.Event, repr=False)

    def poll(self) -> int | None:
        """Return the Java exit code when the child has stopped."""
        return self.process.poll()


class GameRunner:
    """Prepare a verified game instance and supervise its Java process."""

    def __init__(self, root: Path, *, memory_mb: int = 6144) -> None:
        if not 1024 <= memory_mb <= 16384:
            raise ValueError("Invalid memory setting")
        self.root = resolved(root)
        self.memory_mb = memory_mb

    def ensure_stopped(self, release: Release) -> None:
        """Detect a surviving client from any portable copy under the current account."""
        owner = psutil.Process().username()
        for process in psutil.process_iter(["name", "username"]):
            name = process.info["name"] or ""
            if process.info["username"] != owner or name.casefold() not in {
                "java",
                "javaw",
                "java.exe",
                "javaw.exe",
            }:
                continue
            with contextlib.suppress(psutil.NoSuchProcess, psutil.AccessDenied):
                # The argument list can include a session token. Keep it in memory only.
                if _is_pack_process(process.cmdline(), release):
                    event(
                        self.root,
                        "game_already_running",
                        pack=release.pack_id,
                        pid=process.pid,
                    )
                    raise ReleaseError(
                        "Minecraft уже запущен. Завершите предыдущий запуск и повторите."
                    )

    def command(
        self,
        release: Release,
        folder: Path,
        session: Session,
        *,
        memory_mb: int | None = None,
    ) -> list[str]:
        """Build the Java arguments for the selected release and session."""
        release.require_launcher()
        memory_mb = self.memory_mb if memory_mb is None else memory_mb
        if type(memory_mb) is not int or not 1024 <= memory_mb <= 16384:
            raise ReleaseError("Недопустимое количество памяти для игры.")
        if not resolved(folder).is_relative_to(self.root):
            raise ReleaseError("Папка игры находится вне лаунчера.")
        launch = release.launch
        private = self.root / "userdata"
        for name in ["tmp", "java-home", "logs"]:
            (private / name).mkdir(parents=True, exist_ok=True)
        java = inside(folder, launch["java"])
        agent = inside(folder, launch["agent"])
        values = {
            "username": session.player_name,
            "uuid": UUID(session.player_uuid).hex,
            "access_token": session.access_token,
            "instance_id": release.pack_id,
            "game_dir": str(folder),
            "assets_dir": str(inside(folder, launch["assets"])),
        }
        command = [
            str(java),
            "-Xms512M",
            f"-Xmx{memory_mb}M",
            "-XX:+UseG1GC",
            "-Dfile.encoding=UTF-8",
            f"-XX:ErrorFile={resolved(folder) / 'hs_err_pid%p.log'}",
            f"-Djava.library.path={inside(folder, launch['natives'])}",
            f"-Djava.io.tmpdir={private / 'tmp'}",
            f"-Duser.home={private / 'java-home'}",
            f"-javaagent:{agent}={session.origin}/authlib-injector",
            "-Dauthlibinjector.side=client",
        ]
        logging = prepare_logging(release.minecraft, private / "logging")
        if logging is not None:
            command.append(f"-Dlog4j.configurationFile={logging.as_uri()}")
        elif launch.get("logging"):
            command.append(
                f"-Dlog4j.configurationFile={inside(folder, launch['logging'])}"
            )
        command.extend(
            arg for arg in launch.get("jvm_args", []) if arg != "-XX:+UseG1GC"
        )
        command.extend(
            [
                "-cp",
                os.pathsep.join(
                    str(inside(folder, item)) for item in launch["classpath"]
                ),
                launch["main_class"],
            ]
        )
        try:
            command.extend(arg.format_map(values) for arg in launch["game_args"])
        except KeyError, ValueError:
            raise ReleaseError(
                "Не удалось подготовить параметры запуска сборки."
            ) from None
        return command

    def start(
        self,
        release: Release,
        folder: Path,
        session: Session,
        *,
        server: tuple[str, int] | None = None,
        memory_mb: int | None = None,
    ) -> GameProcess:
        """Prepare writable instance settings, launch Java and collect game output."""
        command = self.command(release, folder, session, memory_mb=memory_mb)
        self.ensure_stopped(release)
        clean_extra_mods(release, folder)
        verify_mods(release, folder)
        prepare_client_defaults(release, folder)
        if server:
            command.extend(["--server", server[0], "--port", str(server[1])])
        log = self.root / "userdata" / "logs" / f"{release.pack_id}-game.log"
        writer = BoundedLog(log)
        prune_game_logs(self.root, folder)
        environment = {
            name: value
            for name, value in os.environ.items()
            if name not in {"JAVA_TOOL_OPTIONS", "_JAVA_OPTIONS", "JDK_JAVA_OPTIONS"}
        }
        temporary = str(self.root / "userdata/tmp")
        environment.update(TMP=temporary, TEMP=temporary, TMPDIR=temporary)
        started_at = time.time()
        baseline = crash_fingerprints(self.root, folder)
        try:
            process = subprocess.Popen(
                command,
                cwd=folder,
                env=environment,
                shell=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        except OSError as error:
            failure(self.root, "java_start", error)
            raise
        result = GameProcess(process, log, folder)
        run_id = uuid4().hex
        watcher = RunningCrashWatcher(
            self.root,
            folder,
            release,
            session,
            baseline=baseline,
            run_id=run_id,
            memory_mb=self.memory_mb if memory_mb is None else memory_mb,
            launcher=VERSION,
        )
        watcher.start()
        event(
            self.root,
            "game_started",
            run_id=run_id,
            pack=release.pack_id,
            pack_version=release.version,
            minecraft=release.minecraft,
            platform=release.platform,
            launcher=VERSION,
            memory_mb=self.memory_mb if memory_mb is None else memory_mb,
            resources=environment_snapshot(self.root),
        )

        def collect() -> None:
            try:
                writer.write(
                    f"\n--- run {run_id}: {release.pack_id} {release.version} ---\n",
                    rotate=True,
                )
            except OSError:
                result.logging_failed.set()
            try:
                collect_output(
                    process.stdout,
                    writer,
                    (session.access_token, session.client_token),
                    on_error=result.logging_failed.set,
                )
                code = process.wait()
                handled = watcher.stop()
                event(
                    self.root,
                    "game_exited",
                    run_id=run_id,
                    pack=release.pack_id,
                    exit_code=code,
                    logging_failed=result.logging_failed.is_set(),
                )
                try:
                    capture_incident(
                        self.root,
                        folder,
                        release,
                        session,
                        run_id=run_id,
                        started_at=started_at,
                        exit_code=code,
                        memory_mb=self.memory_mb if memory_mb is None else memory_mb,
                        launcher=VERSION,
                        stdout_current=not result.logging_failed.is_set(),
                        baseline=handled,
                    )
                except (ValueError, TypeError) as error:
                    failure(self.root, "incident_capture", error)
                prune_game_logs(self.root, folder)
            except OSError as error:
                result.logging_failed.set()
                failure(self.root, "game_log", error)
            finally:
                with contextlib.suppress(OSError):
                    watcher.stop()
                result.diagnostics_done.set()

        threading.Thread(
            target=collect, daemon=True, name=f"{release.pack_id}-game-log"
        ).start()
        return result
