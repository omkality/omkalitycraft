"""Linux lifecycle for the existing disposable region-recovery scenarios."""

import hashlib
import shutil
import tarfile
import zipfile
from uuid import uuid4

from omk.dj2_linux_lab import JAVA_IMAGE, LinuxServer, docker, inspect_owned
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

    def prepare(self, dest, args, client):
        return self.server.prepare(dest, args, client)

    def start(self):
        process = self.server.start(snapshot_dir=self.snapshots)
        return process, self.server.log, self.server.collector

    def backup(self, name):
        if name not in {"before-grief", "before-restore", "after-restore"}:
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
        docker("rm", self.server.name)
        return info

    def close(self, report):
        report["linux_java_image"] = JAVA_IMAGE
        self.server.close(report)
