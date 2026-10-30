"""Start only a verified release, keep paths local, and redact credential output."""

import os
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID, uuid4

from launcher.client_defaults import prepare_client_defaults
from launcher.log_policy import prepare_logging
from launcher.mod_policy import clean_extra_mods, verify_mods
from launcher.releases import Release, ReleaseError, inside
from launcher.session import Session
from launcher.version import VERSION
from omk.diagnostics import (
    BoundedLog,
    collect_output,
    environment_snapshot,
    event,
    failure,
    prune_native_archives,
    prune_reports,
)
from omk.fs import resolved


@dataclass
class GameProcess:
    process: subprocess.Popen = field(repr=False)
    log_path: Path
    folder: Path
    diagnostics_done: threading.Event = field(
        default_factory=threading.Event, repr=False
    )
    logging_failed: threading.Event = field(default_factory=threading.Event, repr=False)

    def poll(self) -> int | None:
        return self.process.poll()


class GameRunner:
    def __init__(self, root: Path, *, memory_mb: int = 6144) -> None:
        if not 1024 <= memory_mb <= 16384:
            raise ValueError("Invalid memory setting")
        self.root = resolved(root)
        self.memory_mb = memory_mb

    def command(
        self,
        release: Release,
        folder: Path,
        session: Session,
        *,
        memory_mb: int | None = None,
    ) -> list[str]:
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
        command = self.command(release, folder, session, memory_mb=memory_mb)
        clean_extra_mods(release, folder)
        verify_mods(release, folder)
        prepare_client_defaults(release, folder)
        if server:
            command.extend(["--server", server[0], "--port", str(server[1])])
        log = self.root / "userdata" / "logs" / f"{release.pack_id}-game.log"
        writer = BoundedLog(log)
        prune_reports(self.root, folder / "crash-reports")
        prune_native_archives(self.root, folder / "logs")
        environment = {
            **os.environ,
            "TMP": str(self.root / "userdata/tmp"),
            "TEMP": str(self.root / "userdata/tmp"),
            "TMPDIR": str(self.root / "userdata/tmp"),
        }
        environment.pop("JAVA_TOOL_OPTIONS", None)
        environment.pop("_JAVA_OPTIONS", None)
        environment.pop("JDK_JAVA_OPTIONS", None)
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
                    f"\n--- run {run_id}: {release.pack_id} {release.version} ---\n"
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
                event(
                    self.root,
                    "game_exited",
                    run_id=run_id,
                    pack=release.pack_id,
                    exit_code=code,
                    logging_failed=result.logging_failed.is_set(),
                )
                prune_reports(self.root, folder / "crash-reports")
                prune_native_archives(self.root, folder / "logs")
            except OSError as error:
                result.logging_failed.set()
                failure(self.root, "game_log", error)
            finally:
                result.diagnostics_done.set()

        threading.Thread(
            target=collect, daemon=True, name=f"{release.pack_id}-game-log"
        ).start()
        return result
