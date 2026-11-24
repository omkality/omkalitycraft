"""Build-fixture setup and an actual packaged Qt startup in isolated state."""

import argparse
import contextlib
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

import psutil

from launcher.install import current_platform
from launcher.paths import MACOS_APP, MACOS_RUNTIME, bundle_entrypoint
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
    executable = bundle.resolve() / bundle_entrypoint(current_platform())
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


def smoke_finder(archive: Path, version: str) -> None:
    """Unpack and open a Mac app with Launch Services and wait for its first paint."""
    if sys.platform != "darwin":
        raise ValueError("Launch Services checks require macOS")
    archive = archive.resolve()
    if archive.is_dir():
        archive /= f"OmkalityCraft-{version}-{current_platform()}.zip"
    with TemporaryDirectory(prefix="omk-launch-services-") as folder:
        root = Path(folder).resolve()
        app = root / MACOS_APP
        binary = root / bundle_entrypoint(current_platform())
        log = root / "userdata/logs/launcher.jsonl"
        subprocess.run(["/usr/bin/ditto", "-x", "-k", archive, root], check=True)
        if (root / "userdata").exists():
            raise RuntimeError("The Mac ZIP must be tested as a clean portable install")
        subprocess.run(
            ["/usr/bin/codesign", "--verify", "--deep", "--strict", app], check=True
        )
        try:
            subprocess.run(["/usr/bin/open", "-n", app], check=True, timeout=15)
            deadline = time.monotonic() + 45
            while time.monotonic() < deadline:
                if log.is_file():
                    for line in log.read_text(encoding="utf-8").splitlines():
                        with contextlib.suppress(ValueError):
                            record = json.loads(line)
                            if (
                                record["event"] == "launcher_window_painted"
                                and record["version"] == version
                                and record["qt"] == "cocoa"
                            ):
                                if not list((root / "userdata/tmp").glob("_MEI*")):
                                    raise RuntimeError(
                                        "macOS runtime extracted outside the portable root"
                                    )
                                print(
                                    "Launch Services opened the app, with runtime and logs in the portable root"
                                )
                                return
                time.sleep(0.1)
            raise RuntimeError(
                "macOS launcher did not paint after Launch Services open"
            )
        finally:
            # The one-file bootloader may use two processes. Only stop this copy.
            executables = {str(binary), str(binary.with_name(MACOS_RUNTIME))}
            children = [
                process
                for process in psutil.process_iter(["exe"])
                if process.info["exe"] in executables
            ]
            for process in children:
                with contextlib.suppress(psutil.NoSuchProcess):
                    process.terminate()
            _, alive = psutil.wait_procs(children, timeout=5)
            for process in alive:
                with contextlib.suppress(psutil.NoSuchProcess):
                    process.kill()
            psutil.wait_procs(alive, timeout=5)


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


def smoke_archive(archive: Path, *, version: str = VERSION) -> None:
    """Deliver the actual ZIP over loopback TUF, then start its extracted binary."""
    archive = archive.resolve()
    if archive.is_dir():
        archive /= f"OmkalityCraft-{version}-{current_platform()}.zip"
    fixture = PROJECT_ROOT / ".local/packaging-fixture"
    bootstrap = (fixture / "repository/metadata/1.root.json").read_bytes()
    digest = sha256_file(archive)
    entrypoint = bundle_entrypoint(current_platform())
    with TemporaryDirectory(
        dir=PROJECT_ROOT / ".local", prefix="archive-smoke-"
    ) as folder:
        temporary = Path(folder)
        repository = temporary / "updates"
        shutil.copytree(fixture / "repository", repository)
        publish_update(repository, fixture / "keys", archive, version, entrypoint)
        with serve(temporary) as (origin, requests):
            updater = LauncherUpdater(
                temporary / "portable", origin, bootstrap, "0.0.1"
            )
            update = updater.prepare(print)
            if update is None or update.version != version or update.digest != digest:
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
    mode.add_argument(
        "--finder-archive", type=Path, help="macOS app ZIP or build output"
    )
    parser.add_argument("--version", default=VERSION)
    args = parser.parse_args()
    if args.prepare:
        prepare()
    elif args.bundle:
        smoke(args.bundle)
    elif args.finder_archive:
        smoke_finder(args.finder_archive, args.version)
    else:
        smoke_archive(args.archive, version=args.version)


if __name__ == "__main__":
    main()
