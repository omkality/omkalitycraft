"""Build the client-only adapter; Minecraft ABI stubs never enter its JAR."""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

from verify_targets import verify, verify_book_resources

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))
from archive_format import entry, ordered  # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument("--java", type=Path, required=True)
parser.add_argument("--forge", type=Path, required=True)
parser.add_argument("--mixinbooter", type=Path, required=True)
parser.add_argument(
    "--log4j-api", type=Path, default=root / "tools/log4j-api-2.15.0.jar"
)
args = parser.parse_args()
pins = json.loads((root / "build-tools.json").read_text(encoding="utf-8"))
version = json.loads((root / "versions.json").read_text(encoding="utf-8"))["artifacts"][
    "client"
]
compiler = root / "tools/ecj-3.26.0.jar"
for path, name in [
    (compiler, "compiler"),
    (args.forge, "forge"),
    (args.mixinbooter, "mixinbooter"),
    (args.log4j_api, "log4j_api"),
]:
    if hashlib.sha256(path.read_bytes()).hexdigest() != pins[name]["sha256"]:
        raise ValueError("Unreviewed build input: " + name)
print("Cosmetic Forge class targets:", verify(args.forge))
print(
    "Client book resource contracts:", verify_book_resources(root / "client/resources")
)
build_root = root / "build"
if build_root.resolve() != build_root:
    raise ValueError("Linked or external build directory")
output = root / "build" / ("client-guard-" + version["version"])
if output.exists():
    if (
        output.is_symlink()
        or output.is_junction()
        or not output.resolve().is_relative_to(build_root)
    ):
        raise ValueError("Linked or external client build output")
    shutil.rmtree(output)
classes = output / "classes"
classes.mkdir(parents=True, exist_ok=True)
sources = [
    p
    for directory in ["src", "abi"]
    for p in (root / "client" / directory).rglob("*.java")
]
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
        os.pathsep.join(
            [
                str(args.forge.resolve()),
                str(args.mixinbooter.resolve()),
                str(args.log4j_api.resolve()),
            ]
        ),
        "-d",
        str(classes),
        *map(str, ordered(sources)),
    ],
    check=True,
)
tests = output / "test-classes"
tests.mkdir(parents=True, exist_ok=True)
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
        os.pathsep.join(
            [str(classes), str(args.forge.resolve()), str(args.mixinbooter.resolve())]
        ),
        "-d",
        str(tests),
        *map(str, ordered((root / "client/test").rglob("*.java"))),
    ],
    check=True,
)
for test_class in [
    "net.omkality.client.ClientNetworkTasksTest",
    "net.omkality.client.books.BookLocaleTextTest",
    "net.omkality.client.books.BookMixinHandlersTest",
    "net.omkality.client.books.BookLocaleLoaderTest",
    "net.omkality.client.books.BewitchmentBookLabelsTest",
]:
    subprocess.run(
        [
            str(args.java.resolve()),
            "-cp",
            os.pathsep.join(
                [
                    str(tests),
                    str(classes),
                    str(args.mixinbooter.resolve()),
                    str(args.forge.resolve()),
                ]
            ),
            test_class,
        ],
        check=True,
    )
jar = root / "build" / version["file"]
with zipfile.ZipFile(jar, "w", zipfile.ZIP_DEFLATED) as archive:
    for path in ordered((classes / "net/omkality/client").rglob("*.class")):
        archive.writestr(
            entry(path.relative_to(classes).as_posix()),
            path.read_bytes(),
        )
    for path in ordered((root / "client/resources").rglob("*")):
        if path.is_file():
            archive.writestr(
                entry(path.relative_to(root / "client/resources").as_posix()),
                path.read_bytes(),
            )
    archive.writestr(
        entry("META-INF/MANIFEST.MF"),
        "Manifest-Version: 1.0\n"
        "FMLCorePlugin: net.omkality.client.bootstrap.OmkalityClientLoader\n"
        "FMLCorePluginContainsFMLMod: true\n\n",
    )
with zipfile.ZipFile(jar) as archive:
    assert not any(
        n.startswith("net/minecraft/") or "Test" in n for n in archive.namelist()
    )
print(jar.name, hashlib.sha256(jar.read_bytes()).hexdigest())
