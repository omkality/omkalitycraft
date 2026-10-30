"""Build-fixture setup and an actual packaged Qt startup in isolated state."""

import argparse
import subprocess
import sys
import time
import zipfile
from pathlib import Path
from secrets import token_hex
from tempfile import TemporaryDirectory

from omk.profiles import PROJECT_ROOT
from omk.updates import publish_update


def prepare() -> None:
    folder = PROJECT_ROOT / ".local/packaging-fixture"
    folder.mkdir(parents=True, exist_ok=True)
    archive = folder / "fixture.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("OmkalityCraft", b"only used to generate a test trust root")
    publish_update(
        folder / "repository", folder / "keys", archive, "0.0.1", "OmkalityCraft"
    )


def smoke(bundle: Path) -> None:
    executable = bundle.resolve() / (
        "OmkalityCraft.exe" if sys.platform == "win32" else "OmkalityCraft"
    )
    local = PROJECT_ROOT / ".local"
    local.mkdir(exist_ok=True)
    with TemporaryDirectory(dir=local, prefix="bundle-smoke-") as folder:
        root = Path(folder)
        health = root / "userdata/updates/health.json"
        nonce = token_hex(24)
        process = subprocess.Popen(
            [
                str(executable),
                "--root",
                str(root),
                "--health-file",
                str(health),
                "--health-nonce",
                nonce,
            ],
            cwd=root,
        )
        try:
            deadline = time.monotonic() + 45
            while time.monotonic() < deadline and process.poll() is None:
                if health.exists() and nonce in health.read_text():
                    print("Packaged Qt launcher started successfully in isolated state")
                    return
                time.sleep(0.1)
            raise RuntimeError("Packaged launcher did not acknowledge healthy startup")
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=10)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--bundle", type=Path)
    args = parser.parse_args()
    if args.prepare:
        prepare()
    elif args.bundle:
        smoke(args.bundle)
    else:
        parser.error("Choose --prepare or --bundle")
