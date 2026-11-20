"""Build-fixture setup and an actual packaged Qt startup in isolated state."""

import argparse
import json
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path
from secrets import token_hex
from tempfile import TemporaryDirectory
from unittest.mock import patch

from launcher.install import current_platform
from launcher.releases import sha256_file
from launcher.updater import LauncherUpdater, PreparedUpdate
from launcher.version import VERSION
from omk.distribution.updates import publish_update
from omk.shared.profiles import PROJECT_ROOT
from tests.fixtures.http import serve


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


def _handoff(updater: LauncherUpdater, update: PreparedUpdate) -> None:
    """Run the real handoff, retaining the child handle for smoke-test cleanup."""
    processes = []
    popen = subprocess.Popen

    def start(*args, **kwargs):
        process = popen(*args, **kwargs)
        processes.append(process)
        return process

    try:
        with patch("launcher.updater.subprocess.Popen", side_effect=start):
            if not updater.handoff(update, timeout=45):
                raise RuntimeError(
                    "Archived launcher did not acknowledge healthy startup"
                )
        if updater.active() != update:
            raise RuntimeError("Healthy archive was not activated by the updater")
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)


def smoke_archive(archive: Path) -> None:
    """Deliver the actual ZIP over loopback TUF, then start its extracted binary."""
    archive = archive.resolve()
    if archive.is_dir():
        archive /= f"OmkalityCraft-{VERSION}-{current_platform()}.zip"
    fixture = PROJECT_ROOT / ".local/packaging-fixture"
    bootstrap = (fixture / "repository/metadata/1.root.json").read_bytes()
    digest = sha256_file(archive)
    entrypoint = "OmkalityCraft.exe" if sys.platform == "win32" else "OmkalityCraft"
    with TemporaryDirectory(
        dir=PROJECT_ROOT / ".local", prefix="archive-smoke-"
    ) as folder:
        temporary = Path(folder)
        repository = temporary / "updates"
        shutil.copytree(fixture / "repository", repository)
        publish_update(repository, fixture / "keys", archive, VERSION, entrypoint)
        with serve(temporary) as (origin, requests):
            updater = LauncherUpdater(
                temporary / "portable", origin, bootstrap, "0.0.1"
            )
            update = updater.prepare(print)
            if update is None or update.version != VERSION or update.digest != digest:
                raise RuntimeError("Updater did not prepare the supplied archive")
            _handoff(updater, update)
            print(
                json.dumps(
                    {
                        "archive": archive.name,
                        "sha256": digest,
                        "platform": current_platform(),
                        "version": update.version,
                        "tuf_http_requests": len(requests),
                        "health_handoff": True,
                    }
                )
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--bundle", type=Path)
    mode.add_argument(
        "--archive",
        type=Path,
        help="ZIP or output directory built with the --prepare test trust root",
    )
    args = parser.parse_args()
    if args.prepare:
        prepare()
    elif args.bundle:
        smoke(args.bundle)
    else:
        smoke_archive(args.archive)


if __name__ == "__main__":
    main()
