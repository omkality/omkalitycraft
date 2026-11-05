"""Linux lifecycle for the existing disposable region-recovery scenarios."""

import hashlib
import json
import shutil
import tarfile
import zipfile
from uuid import uuid4

from omk.dj2_linux_lab import (
    JAVA_IMAGE,
    LinuxServer,
    container_outcome,
    docker,
    forge_log_crashed,
    inspect_owned,
)
from omk.recovery_full_lab import MAX_FILE, MAX_FILES, MAX_TOTAL, RESERVED, _entries


def _safe_export_path(name):
    parts = name.split("/")
    return (
        len(parts) >= 2
        and parts[0] == "lab-world"
        and "\\" not in name
        and all(
            part not in ("", ".", "..")
            and not any(ord(c) < 32 or c in ':*?"<>|' for c in part)
            and not part.endswith((".", " "))
            and not RESERVED.match(part)
            for part in parts
        )
    )


def world_tar_to_zip(source, target):
    """Stream a stopped lab world without extracting paths from tar to the host."""
    count = size = 0
    with (
        tarfile.open(source, "r|") as incoming,
        zipfile.ZipFile(target, "x", zipfile.ZIP_DEFLATED, compresslevel=1) as outgoing,
    ):
        for member in incoming:
            if member.isdir():
                continue
            if not member.isfile() or not 0 <= member.size <= MAX_FILE:
                raise ValueError("Linked or oversized Linux world export entry")
            if not _safe_export_path(member.name):
                raise ValueError("Unsafe Linux world export path")
            count += 1
            size += member.size
            if count > MAX_FILES or size > MAX_TOTAL:
                raise ValueError("Linux world export exceeds lab limits")
            with (
                incoming.extractfile(member) as data,
                outgoing.open(member.name, "w") as output,
            ):
                shutil.copyfileobj(data, output, length=1024**2)
    with zipfile.ZipFile(target) as archive:
        _entries(
            archive
        )  # Same paths/casing/collision/level marker policy as full return.
        if archive.testzip() is not None:
            raise ValueError("Linux world backup CRC failure")
    with target.open("rb") as file:
        digest = hashlib.file_digest(file, "sha256").hexdigest()
    return {
        "files": count,
        "uncompressed_bytes": size,
        "bytes": target.stat().st_size,
        "sha256": digest,
    }


class LinuxRecovery:
    def __init__(self, lab, network, snapshots):
        self.lab, self.snapshots = lab, snapshots
        self.server = LinuxServer(lab, uuid4().hex[:10], network)
        self.checkpoint_export = self.checkpoint_stop = None

    def prepare(self, dest, args, client):
        return self.server.prepare(dest, args, client)

    def start(self):
        self.checkpoint_export = self.checkpoint_stop = None
        process = self.server.start(snapshot_dir=self.snapshots)
        return process, self.server.log, self.server.collector

    def backup(self, name):
        if name not in {
            "before-grief",
            "before-restore",
            "after-restore",
            "before-full-return",
        }:
            raise ValueError("Unknown Linux recovery lab checkpoint")
        process = self.server.process
        if process is None or process.poll() is not None:
            raise ValueError("Expected the running owned Linux recovery lab")
        process.stdin.write(b"stop\n")
        process.stdin.flush()
        process.wait(timeout=60)
        self.server.collector.close()
        data = inspect_owned("container", self.server.name, self.server.run_id)
        if (
            process.poll() != 0
            or data is None
            or data["State"]["Running"]
            or data["State"]["ExitCode"] != 0
            or data["State"].get("OOMKilled") is not False
            or forge_log_crashed(self.server.log) is not False
        ):
            raise ValueError("Linux backup requires a cleanly stopped owned server")
        export = self.lab / "exports" / name
        export.mkdir(parents=True)
        self.server.helper(
            "test ! -e /export/world.tar && tar -C /srv -cf /export/world.tar lab-world",
            export=export,
        )
        info = world_tar_to_zip(
            export / "world.tar", self.lab / "backups" / (name + ".zip")
        )
        with (export / "world.tar").open("rb") as file:
            self.checkpoint_export = (
                export / "world.tar",
                hashlib.file_digest(file, "sha256").hexdigest(),
            )
        self.checkpoint_stop = container_outcome(data)
        docker("rm", self.server.name)
        return info

    def world_digest(self):
        """Read the original stopped volume twice without mounting it writable."""
        if self.checkpoint_export is None or self.server.process.poll() != 0:
            raise ValueError("World digest requires a verified stopped checkpoint")
        if inspect_owned("volume", self.server.volume, self.server.run_id) is None:
            raise ValueError("Original owned volume is missing")
        export = self.lab / ("digest-" + uuid4().hex[:10])
        export.mkdir()
        self.server.helper(
            "test ! -e /export/world.tar && tar -C /srv -cf /export/world.tar lab-world",
            export=export,
            readonly_volume=True,
        )
        archive = export / "world.zip"
        world_tar_to_zip(export / "world.tar", archive)
        with zipfile.ZipFile(archive) as incoming:
            entries, _ = _entries(incoming)
            hashes = {}
            for entry in entries:
                with incoming.open(entry) as file:
                    hashes[entry.filename] = hashlib.file_digest(
                        file, "sha256"
                    ).hexdigest()
        return hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()

    def close(self, report, *, preserve_volume=False):
        report["linux_java_image"] = JAVA_IMAGE
        # backup() already removed the stopped container. Its verified TAR is
        # still required before close() may remove this lab's original volume.
        if self.checkpoint_export is not None:
            path, expected = self.checkpoint_export
            try:
                with path.open("rb") as file:
                    valid = hashlib.file_digest(file, "sha256").hexdigest() == expected
            except OSError:
                valid = False
            if not valid:
                report["ok"] = False
                report["owned_volume_retained"] = self.server.volume
                return
            report["stopped_world_tar_sha256"] = expected
            report["linux_container_outcome"] = self.checkpoint_stop
        if preserve_volume:
            self.server.close(report, preserve_volume=True)
        else:
            self.server.close(report)
