"""Build independent Core and DJ2Fix artifacts from pinned compile-only inputs."""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import zipfile
from pathlib import Path

from archive_format import entry, ordered
from fetch_inputs import ensure_input

project = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument("--java", type=Path, required=True)
parser.add_argument("--forge", type=Path, required=True)
parser.add_argument("--ftblib", type=Path)
parser.add_argument("--mixinbooter", type=Path)
parser.add_argument(
    "--log4j-api", type=Path, default=project / "tools/log4j-api-2.15.0.jar"
)
parser.add_argument("--target", choices=["all", "core", "dj2"], default="all")
args = parser.parse_args()
pins = json.loads((project / "build-tools.json").read_text())
compiler = ensure_input("compiler", project / "tools", pins)
versions = json.loads((project / "versions.json").read_text())["artifacts"]
inputs = [(compiler, "compiler"), (args.forge, "forge"), (args.log4j_api, "log4j_api")]
if args.target in {"all", "core"}:
    if args.ftblib is None:
        parser.error("--ftblib is needed to compile the optional FTB integration")
    inputs.append((args.ftblib, "ftblib"))
if args.target in {"all", "dj2"}:
    if args.mixinbooter is None:
        parser.error("--mixinbooter is required for DJ2Fix only")
    inputs.append((args.mixinbooter, "mixinbooter"))
for path, key in inputs:
    if hashlib.sha256(path.read_bytes()).hexdigest() != pins[key]["sha256"]:
        raise ValueError("Build artifact hash mismatch: " + key)
build = project / "build"
build.mkdir(exist_ok=True)
if build.resolve() != build or build.is_symlink() or build.is_junction():
    raise ValueError("External build root")
core = build / versions["core"]["file"]
fix = build / versions["dj2fix"]["file"]


def compile_jar(name, directories, classpath, output, resources=None, manifest=None):
    classes = build / name
    if (
        not classes.resolve().is_relative_to(build)
        or classes.is_symlink()
        or classes.is_junction()
    ):
        raise ValueError("External class output")
    if classes.exists():
        shutil.rmtree(classes)
    classes.mkdir()
    sources = ordered(
        p for directory in directories for p in (project / directory).rglob("*.java")
    )
    subprocess.run(
        [
            str(args.java.resolve()),
            "-jar",
            str(compiler),
            "-1.8",
            "-proc:none",
            "-encoding",
            "UTF-8",
            "-classpath",
            os.pathsep.join(str(p.resolve()) for p in classpath),
            "-d",
            str(classes),
            *map(str, sources),
        ],
        check=True,
    )
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as jar:

        def put(name, data):
            jar.writestr(entry(name), data)

        put("META-INF/MANIFEST.MF", "Manifest-Version: 1.0\n" + (manifest or "") + "\n")
        for path in ordered((classes / "net/omkality").rglob("*.class")):
            put(path.relative_to(classes).as_posix(), path.read_bytes())
        if resources:
            for path in ordered((project / resources).rglob("*")):
                if path.is_file():
                    put(
                        path.relative_to(project / resources).as_posix(),
                        path.read_bytes(),
                    )
    print(output.name, hashlib.sha256(output.read_bytes()).hexdigest())


if args.target in {"all", "core"}:
    compile_jar(
        "core-" + versions["core"]["version"],
        ["src", "integrations/ftb/src", "abi"],
        [args.forge, args.ftblib, args.log4j_api],
        core,
    )
    controls = build / "maintenance-controls"
    controls.mkdir(exist_ok=True)
    subprocess.run(
        [
            str(args.java.resolve()),
            "-jar",
            str(compiler),
            "-1.8",
            "-proc:none",
            "-encoding",
            "UTF-8",
            "-classpath",
            str(core),
            "-d",
            str(controls),
            str(project / "tests/java/net/omkality/MaintenanceControlsTest.java"),
            str(project / "tests/java/net/omkality/GameMetricsControlsTest.java"),
        ],
        check=True,
    )
    subprocess.run(
        [
            str(args.java.resolve()),
            "-cp",
            os.pathsep.join([str(core), str(controls)]),
            "net.omkality.GameMetricsControlsTest",
        ],
        check=True,
    )
    subprocess.run(
        [
            str(args.java.resolve()),
            "-cp",
            os.pathsep.join([str(core), str(controls)]),
            "net.omkality.MaintenanceControlsTest",
        ],
        check=True,
    )
if args.target in {"all", "dj2"}:
    if not core.is_file():
        raise ValueError("Build Core before DJ2Fix")
    compile_jar(
        "dj2fix-" + versions["dj2fix"]["version"],
        ["patches/src", "packs/dj2/src", "abi"],
        [args.forge, args.mixinbooter, core, args.log4j_api],
        fix,
        "packs/dj2/resources",
        "FMLCorePlugin: net.omkality.dj2.OmkalityEarlyMixinPlugin\nFMLCorePluginContainsFMLMod: true\n",
    )
    with zipfile.ZipFile(core) as a, zipfile.ZipFile(fix) as b:
        overlap = (set(a.namelist()) & set(b.namelist())) - {"META-INF/MANIFEST.MF"}
        if overlap:
            raise ValueError("Duplicate Core/Fix classes or resources")
