"""Managed archive transaction, currently exercised only by disposable labs.

No live-world copying, server stop, scheduler, adoption of FTB folders or restore.
The caller supplies a closed archive AND an independently obtained file inventory.
"""

import json
import os
import re
import shutil
from contextlib import contextmanager
from dataclasses import dataclass
from uuid import uuid4

from omk.backup_archive import MAX_MANIFEST_BYTES, SHA256, regular_file, verify_archive

ENTRY = re.compile(r"(snapshot|pending|retired)-[a-f0-9]{32}")
OWNER = {"schema": 1, "kind": "omk-managed-backup-store"}


def _directory(path):
    # Reject linked ancestors too; this is an operator-owned local filesystem,
    # not a sandbox against a hostile process with the same filesystem access.
    for parent in (path, *path.parents):
        if parent.is_symlink() or parent.is_junction():
            raise ValueError("Linked backup directories are forbidden")
    if not path.is_dir():
        raise ValueError("Expected an existing backup directory")


def _sync_directory(path):
    if os.name != "nt":
        descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def _json_write(path, value):
    data = _json_bytes(value)
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def _json_bytes(value):
    data = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    if len(data) > MAX_MANIFEST_BYTES:
        raise ValueError("Backup manifest exceeded its limit")
    return data


def _json_read(path):
    if regular_file(path) > MAX_MANIFEST_BYTES:
        raise ValueError("Backup metadata exceeded its limit")
    return json.loads(path.read_bytes())


@contextmanager
def _lock(root):
    regular_file(root / "lock")
    with (root / "lock").open("r+b") as stream:
        if os.name == "nt":
            import msvcrt  # noqa: PLC0415

            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl  # noqa: PLC0415

            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            if os.name == "nt":
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


@dataclass(frozen=True)
class BackupPolicy:
    max_bytes: int
    max_count: int
    staging_bytes: int
    reserve_bytes: int

    def __post_init__(self):
        if (
            any(type(value) is not int or value < 1 for value in vars(self).values())
            or self.max_count < 2
        ):
            raise ValueError("Invalid backup policy; retain at least two copies")


class BackupStore:
    def __init__(self, root, policy):
        self.root, self.policy = root, policy
        _directory(root)
        if _json_read(root / "owner.json") != OWNER:
            raise ValueError("Unowned backup store")

    @classmethod
    def create(cls, root, policy):
        """Only a new directory; never adopt or clear existing backup data."""
        _directory(root.parent)
        root.mkdir()
        _json_write(root / "owner.json", OWNER)
        with (root / "lock").open("xb") as stream:
            stream.write(b"0")
            stream.flush()
            os.fsync(stream.fileno())
        _sync_directory(root)
        _sync_directory(root.parent)
        return cls(root, policy)

    def _snapshots(self):
        _directory(self.root)
        if _json_read(self.root / "owner.json") != OWNER:
            raise ValueError("Unowned backup store")
        snapshots = []
        for entry in self.root.iterdir():
            if entry.name in {"lock", "owner.json"}:
                regular_file(entry)
                continue
            if not ENTRY.fullmatch(entry.name):
                raise ValueError("Foreign data in backup store")
            _directory(entry)
            if not entry.name.startswith("snapshot-"):
                raise ValueError("Interrupted backup needs operator inspection")
            if {p.name for p in entry.iterdir()} != {"archive.zip", "manifest.json"}:
                raise ValueError("Incomplete or foreign backup snapshot")
            manifest = _json_read(entry / "manifest.json")
            if (
                not isinstance(manifest, dict)
                or set(manifest) != {"schema", "sequence", "sha256", "files", "bytes"}
                or type(manifest["schema"]) is not int
                or manifest["schema"] != 1
                or not isinstance(manifest["sha256"], str)
                or not SHA256.fullmatch(manifest["sha256"])
                or type(manifest["sequence"]) is not int
                or manifest["sequence"] < 1
                or regular_file(entry / "archive.zip") != manifest["bytes"]
                or type(manifest["bytes"]) is not int
                or manifest["bytes"] <= 0
                or manifest["bytes"] > self.policy.staging_bytes
            ):
                raise ValueError("Invalid stored backup manifest")
            verify_archive(entry / "archive.zip", manifest["files"], manifest["sha256"])
            snapshots.append(
                (
                    manifest["sequence"],
                    entry,
                    manifest["bytes"] + regular_file(entry / "manifest.json"),
                )
            )
        snapshots.sort()
        if len({s[0] for s in snapshots}) != len(snapshots):
            raise ValueError("Ambiguous backup sequence")
        return snapshots

    def inspect(self):
        with _lock(self.root):
            return [
                {"sequence": sequence, "id": entry.name, "bytes": size}
                for sequence, entry, size in self._snapshots()
            ]

    def _victims(self, snapshots, incoming_size):
        remaining, size = list(snapshots), sum(s[2] for s in snapshots) + incoming_size
        victims = []
        while (
            len(remaining) + 1 > self.policy.max_count or size > self.policy.max_bytes
        ):
            if len(remaining) <= 1:
                raise ValueError("Budget cannot retain the new and preceding copy")
            victim = remaining.pop(0)
            size -= victim[2]
            victims.append(victim[1])
        return victims

    def _copy(self, archive, target, expected_size):
        with archive.open("rb") as incoming, target.open("xb") as outgoing:
            size = 0
            while data := incoming.read(1024**2):
                size += len(data)
                if size > expected_size:
                    raise ValueError("Backup input changed during copying")
                outgoing.write(data)
            outgoing.flush()
            os.fsync(outgoing.fileno())
        if size != expected_size:
            raise ValueError("Backup input changed during copying")

    def _retire(self, entry):
        target = self.root / entry.name.replace("snapshot-", "retired-", 1)
        entry.rename(target)
        _sync_directory(self.root)
        # No recursive delete or glob. Fail closed on foreign content/links.
        if {p.name for p in target.iterdir()} != {"archive.zip", "manifest.json"}:
            raise ValueError("Foreign data during backup retirement")
        for name in ("archive.zip", "manifest.json"):
            regular_file(target / name)
        (target / "archive.zip").unlink()
        (target / "manifest.json").unlink()
        target.rmdir()
        _sync_directory(self.root)

    def publish(self, archive, files):
        """Commit a verified copy before retiring anything. Failures preserve history.

        Pending/retired leftovers deliberately block further writes after a crash.
        An operator must inspect them; repeated retries cannot fill the disk.
        """
        # Own the inventory for the duration of this transaction. A caller
        # reusing/mutating its dict must not change the committed manifest after
        # the staged archive's readback has already passed.
        files = json.loads(_json_bytes(files))
        if archive.resolve().is_relative_to(self.root.resolve()):
            raise ValueError("Backup input must be outside the managed store")
        size = regular_file(archive)
        if not 0 < size <= min(self.policy.staging_bytes, self.policy.max_bytes):
            raise ValueError("Backup exceeds staging or retention budget")
        digest = verify_archive(archive, files)
        with _lock(self.root):
            return self._publish(archive, files, size, digest)

    def _publish(self, archive, files, size, digest):
        snapshots = self._snapshots()
        if (
            len(snapshots) > self.policy.max_count
            or sum(s[2] for s in snapshots) > self.policy.max_bytes
        ):
            raise ValueError("Unfinished retention needs operator inspection")
        metadata = {
            "schema": 1,
            "sequence": snapshots[-1][0] + 1 if snapshots else 1,
            "sha256": digest,
            "files": files,
            "bytes": size,
        }
        stored_size = size + len(_json_bytes(metadata))
        victims = self._victims(snapshots, stored_size)
        if stored_size > self.policy.staging_bytes:
            raise ValueError("Backup and metadata exceed staging budget")
        if (
            shutil.disk_usage(self.root).free
            < stored_size + 65536 + self.policy.reserve_bytes
        ):
            raise OSError("Insufficient free space; previous backups preserved")
        pending = self.root / ("pending-" + uuid4().hex)
        pending.mkdir()
        # On error do not guess that an incomplete directory is safe to erase.
        # It remains bounded to one staging attempt and is visible to the operator.
        self._copy(archive, pending / "archive.zip", size)
        verify_archive(pending / "archive.zip", files, digest)
        _json_write(pending / "manifest.json", metadata)
        _sync_directory(pending)
        committed = self.root / pending.name.replace("pending-", "snapshot-", 1)
        pending.rename(committed)
        _sync_directory(self.root)
        for victim in victims:
            self._retire(victim)
        return {
            "id": committed.name,
            "sequence": metadata["sequence"],
            "sha256": digest,
            "verified": True,
            "retired": len(victims),
        }
