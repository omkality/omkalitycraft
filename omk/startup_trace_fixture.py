"""Build an opt-in diagnostic agent, never a player/runtime artifact."""

import hashlib
import os
import subprocess
import zipfile

from omk.client_crash_fixture import COMPILER_SHA256, COMPILER_SOURCE
from omk.profiles import PROJECT_ROOT

PINS = {
    "compiler": {"sha256": COMPILER_SHA256, "source": COMPILER_SOURCE},
    "asm": {
        "sha256": "254b82bec9da4f8efbc8b1f93ab2b87f7465227a82b36cf3d05d9e77a0e8dd2e",
        "source": "https://repo.maven.apache.org/maven2/org/ow2/asm/asm-debug-all/5.2/asm-debug-all-5.2.jar",
    },
    "launchwrapper": {
        "sha256": "57f402b626d16cc2705bf2a37add7adbb074f0ca3b3102fa6e23aa303dae682f",
        "source": "https://libraries.minecraft.net/net/minecraft/launchwrapper/1.12/launchwrapper-1.12.jar",
    },
    "forge": {
        "sha256": "cd3fbf85d7ca744507fd6a37a41b90122d43e616a4f8962332b1b658655e8a64",
        "source": "https://maven.minecraftforge.net/net/minecraftforge/forge/1.12.2-14.23.5.2860/forge-1.12.2-14.23.5.2860-universal.jar",
    },
}


def inputs(server_source, compiler):
    paths = {
        "compiler": compiler,
        "asm": server_source
        / "libraries/org/ow2/asm/asm-debug-all/5.2/asm-debug-all-5.2.jar",
        "launchwrapper": server_source
        / "libraries/net/minecraft/launchwrapper/1.12/launchwrapper-1.12.jar",
        "forge": server_source / "forge-1.12.2-14.23.5.2860.jar",
    }
    for key, path in paths.items():
        with path.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != PINS[key]["sha256"]:
                raise ValueError("Unpinned startup fixture artifact: " + key)
    return paths


def build_startup_agent(java, compiler, server_source, lab, *, mode="full"):
    if mode not in {"full", "exclusions", "console"}:
        raise ValueError("Unknown startup trace mode")
    paths = inputs(server_source, compiler)
    if not lab.name.startswith("startup-trace-lab-") or lab.is_symlink():
        raise ValueError("Expected an isolated startup trace lab")
    directory = lab / "trace-fixture"
    directory.mkdir()
    classes = directory / "classes"
    classes.mkdir()
    sources = [
        PROJECT_ROOT / "tests/fixtures" / filename
        for filename in (
            "StartupTraceAgent.java",
            "ConsoleStartupAgent.java",
            "ReplayItemBlock.java",
        )
    ]
    environment = {
        key: value
        for key, value in os.environ.items()
        if key not in {"JAVA_TOOL_OPTIONS", "_JAVA_OPTIONS", "JDK_JAVA_OPTIONS"}
    }
    result = subprocess.run(
        [
            str(java.resolve()),
            "-jar",
            str(paths["compiler"].resolve()),
            "-1.8",
            "-proc:none",
            "-encoding",
            "UTF-8",
            "-classpath",
            os.pathsep.join(
                str(paths[key].resolve()) for key in ("asm", "launchwrapper", "forge")
            ),
            "-d",
            str(classes.resolve()),
            *map(str, sources),
        ],
        env=environment,
        capture_output=True,
        timeout=90,
        check=False,
    )
    if result.returncode:
        raise RuntimeError("Startup fixture compilation failed")
    for name in ("StartupTraceAgent", "ConsoleStartupAgent", "ReplayItemBlock"):
        if not (classes / "omk/lab/trace" / (name + ".class")).is_file():
            raise ValueError("Incomplete startup fixture compiler output")
    jar = directory / "startup-trace-agent.jar"
    with zipfile.ZipFile(jar, "x", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(classes.rglob("*.class")):
            data = path.read_bytes()
            if data[:8] != b"\xca\xfe\xba\xbe\x00\x00\x00\x34":
                raise ValueError("Expected Java 8 fixture bytecode")
            archive.writestr(
                zipfile.ZipInfo(
                    path.relative_to(classes).as_posix(), (2026, 1, 1, 0, 0, 0)
                ),
                data,
            )
        premain = "ConsoleStartupAgent" if mode == "console" else "StartupTraceAgent"
        archive.writestr(
            zipfile.ZipInfo("META-INF/MANIFEST.MF", (2026, 1, 1, 0, 0, 0)),
            "Manifest-Version: 1.0\nPremain-Class: omk.lab.trace." + premain + "\n\n",
        )
    metadata = {
        "inputs": PINS,
        "agent_sha256": hashlib.sha256(jar.read_bytes()).hexdigest(),
        "sources_sha256": {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sources
        },
    }
    return jar, metadata
