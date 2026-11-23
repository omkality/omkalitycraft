"""Download verified hourly world archives using the export-only SSH identity."""

import argparse
import contextlib
import hashlib
import json
import os
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path

SNAPSHOT = re.compile(r"snapshot-[a-f0-9]{32}")
SHA256 = re.compile(r"[a-f0-9]{64}")
RETENTION = 6


def _remote(args, request, *, output=subprocess.PIPE, timeout=20):
    result = subprocess.run(
        [
            str(args.ssh),
            "-F",
            str(args.ssh_config),
            "-T",
            "omk-hourly-backup",
            request,
        ],
        stdin=subprocess.DEVNULL,
        stdout=output,
        stderr=subprocess.DEVNULL,
        # The scheduled pythonw process has no console for ssh to inherit.
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        timeout=timeout,
        check=True,
    )
    return result.stdout


def _metadata(value):
    if (
        set(value) != {"snapshot", "time", "sequence", "bytes", "sha256"}
        or not SNAPSHOT.fullmatch(value["snapshot"])
        or not SHA256.fullmatch(value["sha256"])
        or type(value["bytes"]) is not int
        or not 0 < value["bytes"] <= 17 * 1024**3
        or type(value["sequence"]) is not int
        or value["sequence"] < 1
        or datetime.fromisoformat(value["time"]).tzinfo is None
    ):
        raise ValueError("Invalid backup metadata")
    return value


def _not_link(path):
    if path.is_symlink() or path.is_junction():
        raise ValueError("Linked backup path")


def _stored(folder):
    _not_link(folder)
    manifest = folder / "backup.json"
    archive = folder / "archive.zip"
    _not_link(manifest)
    _not_link(archive)
    if {path.name for path in folder.iterdir()} != {"backup.json", "archive.zip"}:
        raise ValueError("Unexpected files in the backup folder")
    if not manifest.is_file() or manifest.stat().st_size > 4096:
        raise ValueError("Missing backup metadata")
    row = _metadata(json.loads(manifest.read_text(encoding="utf-8")))
    if row["snapshot"] != folder.name or archive.stat().st_size != row["bytes"]:
        raise ValueError("Backup metadata and files differ")
    return row


def _verify(archive, row):
    if archive.stat().st_size != row["bytes"]:
        raise ValueError("World archive size mismatch")
    with archive.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != row["sha256"]:
            raise ValueError("World archive SHA-256 mismatch")


def _fetch(args, row):
    folder = args.destination / row["snapshot"]
    suffix = row["snapshot"] + " " + row["sha256"]
    try:
        if folder.exists() or folder.is_symlink():
            if _stored(folder) != row:
                raise ValueError("Local copy differs from the source")
            _verify(folder / "archive.zip", row)
        else:
            _remote(args, "copying " + suffix)
            staging = args.destination / ("." + row["snapshot"] + ".incoming")
            _not_link(staging)
            staging.mkdir(exist_ok=True)
            archive = staging / "archive.zip"
            marker = staging / "backup.json"
            _not_link(archive)
            _not_link(marker)
            with archive.open("wb") as stream:
                # Stop a suspended connection via both the SSH config and timeout.
                _remote(args, "get " + row["snapshot"], output=stream, timeout=3600)
                stream.flush()
                os.fsync(stream.fileno())
            _verify(archive, row)
            marker.write_text(json.dumps(row), encoding="utf-8")
            staging.rename(folder)
        return suffix
    except OSError, ValueError, subprocess.SubprocessError:
        with contextlib.suppress(OSError, subprocess.SubprocessError):
            _remote(args, "failed " + suffix)
        raise


def _prune(destination):
    folders = []
    for path in destination.iterdir():
        if SNAPSHOT.fullmatch(path.name):
            try:
                folders.append((_stored(path)["sequence"], path))
            except OSError, ValueError, KeyError, TypeError:
                continue
    for _, path in sorted(folders)[:-RETENTION]:
        (path / "archive.zip").unlink()
        (path / "backup.json").unlink()
        path.rmdir()


def sync(args, previous):
    """Pull missing verified generations, then retire only this job's old pairs."""
    raw = _remote(args, "list")
    remote = json.loads(raw) if len(raw) <= 8192 else None
    if not isinstance(remote, list) or len(remote) > RETENTION:
        raise ValueError("Invalid backup listing")
    rows = sorted(map(_metadata, remote), key=lambda row: row["sequence"])
    for path in (args.destination, *args.destination.parents):
        _not_link(path)
    if not args.destination.anchor or not Path(args.destination.anchor).is_dir():
        if rows:
            row = rows[-1]
            _remote(args, "failed " + row["snapshot"] + " " + row["sha256"])
        raise OSError("Backup drive is unavailable")
    args.destination.mkdir(parents=True, exist_ok=True)
    acked = set(previous)
    for row in rows:
        snapshot = row["snapshot"]
        if snapshot in acked:
            try:
                if _stored(args.destination / snapshot) == row:
                    continue
            except OSError, ValueError, KeyError, TypeError:
                pass
        suffix = _fetch(args, row)
        _remote(args, "complete " + suffix)
        acked.add(snapshot)
    _prune(args.destination)
    return [row["snapshot"] for row in rows if row["snapshot"] in acked]


def main():
    """Run a single unattended synchronization and retain its local result."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--ssh", type=Path, required=True)
    parser.add_argument("--ssh-config", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    args = parser.parse_args()
    previous = []
    with contextlib.suppress(OSError, ValueError, KeyError, TypeError):
        previous = json.loads(args.state.read_text(encoding="utf-8"))["received"]
    row = {
        "time": datetime.now(UTC).isoformat(timespec="seconds"),
        "received": previous,
    }
    try:
        row.update(received=sync(args, previous), ok=True)
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        subprocess.SubprocessError,
    ) as error:
        row.update(ok=False, error=type(error).__name__)
    temporary = args.state.with_suffix(".tmp")
    temporary.write_text(json.dumps(row), encoding="utf-8")
    temporary.replace(args.state)
    return int(not row["ok"])


if __name__ == "__main__":
    raise SystemExit(main())
