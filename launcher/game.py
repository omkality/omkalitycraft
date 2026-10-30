"""Start only a verified release, keep paths local, and redact credential output."""

import os
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID

from launcher.releases import Release, ReleaseError, inside
from launcher.session import Session
from omk.fs import resolved


@dataclass
class GameProcess:
    process: subprocess.Popen = field(repr=False)
    log_path: Path
    folder: Path

    def poll(self) -> int | None:
        return self.process.poll()


class GameRunner:
    def __init__(self, root: Path, *, memory_mb: int = 6144) -> None:
        if not 2048 <= memory_mb <= 16384:
            raise ValueError("Invalid memory setting")
        self.root = resolved(root)
        self.memory_mb = memory_mb

    def command(self, release: Release, folder: Path, session: Session) -> list[str]:
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
            f"-Xmx{self.memory_mb}M",
            "-XX:+UseG1GC",
            f"-Djava.library.path={inside(folder, launch['natives'])}",
            f"-Djava.io.tmpdir={private / 'tmp'}",
            f"-Duser.home={private / 'java-home'}",
            f"-javaagent:{agent}={session.origin}/authlib-injector",
            "-Dauthlibinjector.side=client",
        ]
        if launch.get("logging"):
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
    ) -> GameProcess:
        command = self.command(release, folder, session)
        if server:
            command.extend(["--server", server[0], "--port", str(server[1])])
        log = self.root / "userdata" / "logs" / f"{release.pack_id}-game.log"
        environment = {
            **os.environ,
            "TMP": str(self.root / "userdata/tmp"),
            "TEMP": str(self.root / "userdata/tmp"),
            "TMPDIR": str(self.root / "userdata/tmp"),
        }
        environment.pop("JAVA_TOOL_OPTIONS", None)
        environment.pop("_JAVA_OPTIONS", None)
        environment.pop("JDK_JAVA_OPTIONS", None)
        process = subprocess.Popen(
            command,
            cwd=folder,
            env=environment,
            shell=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )

        def collect() -> None:
            with log.open("w", encoding="utf-8") as output:
                for raw in iter(process.stdout.readline, b""):
                    text = raw.decode("utf-8", errors="replace")
                    for secret in [session.access_token, session.client_token]:
                        text = text.replace(secret, "[redacted]")
                    output.write(text)
                    output.flush()

        threading.Thread(
            target=collect, daemon=True, name=f"{release.pack_id}-game-log"
        ).start()
        return GameProcess(process, log, folder)
