"""Build twice, run the Java helper controls and check the accepted artifact bytes."""

import hashlib
import json
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def inspect_jar(path, component):
    prefixes = {
        "core": ("net/omkality/",),
        "dj2fix": ("net/omkality/patches/", "net/omkality/dj2/"),
        "client": ("net/omkality/client/",),
    }
    with zipfile.ZipFile(path) as jar:
        names = jar.namelist()
        if len(names) != len(set(names)):
            raise ValueError("Duplicate archive entry")
        classes = {name for name in names if name.endswith(".class")}
        if not classes:
            raise ValueError("Empty mod artifact")
        for name in names:
            if name.startswith("/") or "\\" in name or ".." in name.split("/"):
                raise ValueError("Noncanonical archive entry")
            if name.endswith(".jar") or "/lab/" in name or "Test" in name:
                raise ValueError("Dependency, lab or test packaged into mod")
        for name in classes:
            if not name.startswith(prefixes[component]):
                raise ValueError("Foreign class packaged into mod: " + name)
            if component == "core" and name.startswith(
                ("net/omkality/patches/", "net/omkality/dj2/", "net/omkality/client/")
            ):
                raise ValueError("Pack/client implementation packaged into Core")
            data = jar.read(name)
            if (
                data[:4] != b"\xca\xfe\xba\xbe"
                or int.from_bytes(data[6:8], "big") != 52
            ):
                raise ValueError("Mod must contain Java 8 class files")
        return classes


def main():
    versions = json.loads((ROOT / "versions.json").read_text())["artifacts"]
    pins = json.loads((ROOT / "build-tools.json").read_text())
    java = shutil.which("java")
    if java is None:
        raise RuntimeError("Java 8 is required")
    sources = {
        "core": "src/net/omkality/OmkalityCore.java",
        "dj2fix": "packs/dj2/src/net/omkality/dj2/OmkalityDJ2Fix.java",
        "client": "client/src/net/omkality/client/OmkalityClient.java",
    }
    for name, source in sources.items():
        version = re.search(r'\bversion\s*=\s*"([^"]+)"', (ROOT / source).read_text())[
            1
        ]
        if version != versions[name]["version"]:
            raise ValueError("Version metadata differs from Java annotation: " + name)
    subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
        cwd=ROOT,
        check=True,
    )
    inputs = {name: str(ROOT / "tools" / pin["filename"]) for name, pin in pins.items()}
    rounds = []
    for _ in range(2):
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "build.py"),
                "--java",
                java,
                "--forge",
                inputs["forge"],
                "--ftblib",
                inputs["ftblib"],
                "--mixinbooter",
                inputs["mixinbooter"],
            ],
            check=True,
        )
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "client/build.py"),
                "--java",
                java,
                "--forge",
                inputs["forge"],
                "--mixinbooter",
                inputs["mixinbooter"],
            ],
            check=True,
        )
        hashes, classes = {}, {}
        for name, artifact in versions.items():
            path = ROOT / "build" / artifact["file"]
            hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
            if hashes[name] != artifact["sha256"]:
                raise ValueError("Build differs from accepted artifact: " + name)
            classes[name] = inspect_jar(path, name)
        if any(
            classes[a] & classes[b]
            for a, b in [("core", "dj2fix"), ("core", "client"), ("dj2fix", "client")]
        ):
            raise ValueError("Duplicate runtime classes between mods")
        rounds.append(hashes)
    if rounds[0] != rounds[1]:
        raise ValueError("Mod build is not reproducible")
    result = {
        "schema": 1,
        "ok": True,
        "rounds": rounds,
        "matches_accepted_jars": True,
        "class_counts": {k: len(v) for k, v in classes.items()},
        "graphical_or_gameplay_test": False,
    }
    (ROOT / "build/verification.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
