"""Compile an opt-in lab-only agent; it never changes the player release or Core."""

import hashlib
import os
import subprocess
import zipfile

from launcher.game import GameRunner
from omk.profiles import PROJECT_ROOT

COMPILER_SHA256 = "ac0ba5876eaf7ebb47749a0d1be179c51f194b9dd0b875d1c09e1b530f5a2db5"
COMPILER_SOURCE = (
    "https://repo.maven.apache.org/maven2/org/eclipse/jdt/ecj/3.26.0/ecj-3.26.0.jar"
)
CANARY = "omk_lab_canary_not_a_credential"


def build_crash_agent(java, compiler, lab):
    with compiler.open("rb") as file:
        if hashlib.file_digest(file, "sha256").hexdigest() != COMPILER_SHA256:
            raise ValueError("Expected pinned ECJ 3.26.0 compiler")
    classes = lab / "crash-fixture/classes"
    classes.mkdir(parents=True)
    source = PROJECT_ROOT / "tests/fixtures/ClientCrashAgent.java"
    environment = {**os.environ}
    for name in ("JAVA_TOOL_OPTIONS", "_JAVA_OPTIONS", "JDK_JAVA_OPTIONS"):
        environment.pop(name, None)
    result = subprocess.run(
        [
            str(java.resolve()),
            "-jar",
            str(compiler.resolve()),
            "-1.8",
            "-proc:none",
            "-encoding",
            "UTF-8",
            "-d",
            str(classes.resolve()),
            str(source),
        ],
        env=environment,
        capture_output=True,
        timeout=90,
        check=False,
    )
    if result.returncode:
        raise RuntimeError("Controlled client crash fixture did not compile")
    jar = lab / "crash-fixture/client-crash-agent.jar"
    with zipfile.ZipFile(jar, "x", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(classes.rglob("*.class")):
            archive.writestr(
                zipfile.ZipInfo(
                    path.relative_to(classes).as_posix(), (2026, 1, 1, 0, 0, 0)
                ),
                path.read_bytes(),
            )
        archive.writestr(
            zipfile.ZipInfo("META-INF/MANIFEST.MF", (2026, 1, 1, 0, 0, 0)),
            "Manifest-Version: 1.0\nPremain-Class: omk.lab.fixture.ClientCrashAgent\n\n",
        )
    return jar


class CrashLabRunner(GameRunner):
    def __init__(self, root, *, fixture, marker, reports_url):
        super().__init__(root, reports_url=reports_url)
        if (
            not marker.parent.name.startswith("client-crash-lab-")
            or marker.name != "request-client-crash"
            or not fixture.resolve().is_relative_to(marker.parent.resolve())
        ):
            raise ValueError("Expected isolated controlled crash fixture")
        self.fixture, self.marker = fixture, marker

    def command(self, *args, **kwargs):
        command = super().command(*args, **kwargs)
        command.insert(
            1, f"-javaagent:{self.fixture.resolve()}={self.marker.resolve()}"
        )
        return command
