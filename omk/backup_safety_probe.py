"""Disposable Linux filesystem probes; never accepts an existing server/world."""

import errno
import hashlib
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from zipfile import ZIP_STORED, ZipFile

from omk.backup_archive import verify_archive
from omk.backup_store import BackupPolicy, BackupStore

MIB = 1024**2
POLICY = BackupPolicy(12 * MIB, 2, 16 * MIB, 65536)


def _archive(root, number, size=MIB):
    path, files = root / f"input-{number}.zip", {}
    with ZipFile(path, "x", ZIP_STORED) as archive:
        for name, payload in {
            "world/level.dat": b"synthetic level " + str(number).encode(),
            "world/DIM-1/region/r.0.0.mca": os.urandom(size),
            "world/data/teams.dat": b"synthetic claims " + str(number).encode(),
        }.items():
            archive.writestr(name, payload)
            files[name] = {
                "bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
    return path, files


def _verified_copies(root):
    result = []
    for path in sorted(root.glob("snapshot-*")):
        metadata = json.loads((path / "manifest.json").read_bytes())
        verify_archive(path / "archive.zip", metadata["files"], metadata["sha256"])
        result.append(metadata["sequence"])
    return sorted(result)


def _unchanged(root, before):
    return all((root / name).read_bytes() == data for name, data in before.items())


def _history(root):
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def _pause(root):
    (root.parent / "child-ready").write_bytes(b"ready")
    os.kill(os.getpid(), signal.SIGSTOP)
    raise RuntimeError("Probe should have killed the paused child")


class _InterruptedStore(BackupStore):
    phase = ""

    def _copy(self, archive, target, expected_size):
        if self.phase == "copy":
            with archive.open("rb") as source, target.open("xb") as output:
                output.write(source.read(65536))
                output.flush()
                os.fsync(output.fileno())
            _pause(self.root)
        super()._copy(archive, target, expected_size)

    def _retire(self, entry):
        if self.phase == "committed":
            _pause(self.root)
        if self.phase in {"retiring", "retired-data-deleted"}:
            original = Path.unlink

            def before_unlink(path, *args, **kwargs):
                if path.parent.name.startswith("retired-") and self.phase == "retiring":
                    _pause(self.root)
                result = original(path, *args, **kwargs)
                if (
                    path.parent.name.startswith("retired-")
                    and self.phase == "retired-data-deleted"
                ):
                    _pause(self.root)
                return result

            Path.unlink = before_unlink
        super()._retire(entry)


def _worker(root, phase):
    if root.parent.parent != Path("/lab") or phase not in {
        "copy",
        "committed",
        "retiring",
        "retired-data-deleted",
    }:
        raise ValueError("Probe worker requires its isolated lab path")
    source = root.parent / "incoming.zip"
    inventory = json.loads((root.parent / "incoming.json").read_bytes())
    store = _InterruptedStore(root, POLICY)
    store.phase = phase
    store.publish(source, inventory)


def _kill_probe(base, phase):
    with tempfile.TemporaryDirectory(dir=base) as temp:
        root = Path(temp)
        store = BackupStore.create(root / "store", POLICY)
        for number in range(2):
            store.publish(*_archive(root, number))
        before = _history(store.root)
        source, inventory = _archive(root, 2)
        source.rename(root / "incoming.zip")
        (root / "incoming.json").write_text(json.dumps(inventory))
        child = subprocess.Popen(
            [
                sys.executable,
                "-B",
                "-m",
                "omk.backup_safety_probe",
                "worker",
                str(store.root),
                phase,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        try:
            deadline = time.monotonic() + 15
            while not (root / "child-ready").exists():
                if child.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError("Backup probe child did not reach its barrier")
                time.sleep(0.02)
            child.kill()
            child.wait(timeout=5)
            if child.returncode != -signal.SIGKILL:
                raise AssertionError("Expected real SIGKILL")
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=5)
            child.stderr.close()
        copies = _verified_copies(store.root)
        assert copies == (
            {
                "copy": [1, 2],
                "committed": [1, 2, 3],
                "retiring": [2, 3],
                "retired-data-deleted": [2, 3],
            }[phase]
        )
        if phase == "copy":
            assert _unchanged(store.root, before)
        # The OS releases the child's advisory lock. History/leftovers, rather
        # than a stale lock or retries, explain the fail-closed result.
        try:
            store.publish(root / "incoming.zip", inventory)
        except ValueError as error:
            assert "operator inspection" in str(error)
        else:
            raise AssertionError("Interrupted operation unexpectedly accepted a retry")
        return {
            "phase": phase,
            "signal": "SIGKILL",
            "verified_sequences": copies,
            "retry_blocked": True,
            "lock_released_by_os": True,
        }


def _enospc_probe(base, inputs):
    with tempfile.TemporaryDirectory(dir=base) as temp:
        root = Path(temp)
        store = BackupStore.create(root / "store", POLICY)
        for number in range(2):
            store.publish(*_archive(inputs, 10 + number, 256 * 1024))
        before = _history(store.root)
        archive, inventory = _archive(inputs, 12, 4 * MIB)
        original = store._copy

        def concurrent_disk_consumer(source, target, size):
            # Preflight has already succeeded. Another writer now consumes
            # actual tmpfs blocks: the archive write itself must raise ENOSPC.
            free = os.statvfs(root).f_bavail * os.statvfs(root).f_frsize
            with (root / "unrelated-lab-writer").open("xb") as output:
                remaining = free - 128 * 1024
                while remaining > 0:
                    chunk = bytes(min(MIB, remaining))
                    output.write(chunk)
                    remaining -= len(chunk)
                output.flush()
                os.fsync(output.fileno())
            original(source, target, size)

        store._copy = concurrent_disk_consumer
        try:
            store.publish(archive, inventory)
        except OSError as error:
            assert error.errno == errno.ENOSPC
        else:
            raise AssertionError("Actual ENOSPC was not observed")
        assert _unchanged(store.root, before) and _verified_copies(store.root) == [1, 2]
        pending = list(store.root.glob("pending-*"))
        assert len(pending) == 1
        try:
            store.publish(archive, inventory)
        except ValueError as error:
            assert "operator inspection" in str(error)
        else:
            raise AssertionError("Disk-full retry must not create another staging copy")
        assert list(store.root.glob("pending-*")) == pending
        return {
            "errno": errno.ENOSPC,
            "filesystem": "16 MiB tmpfs",
            "previous_copies_unchanged": True,
            "verified_sequences": [1, 2],
            "retry_blocked": True,
        }


def _rotation_probe(base):
    with tempfile.TemporaryDirectory(dir=base) as temp:
        root = Path(temp)
        store = BackupStore.create(root / "store", POLICY)
        for number in range(4):
            result = store.publish(*_archive(root, number))
        assert [c["sequence"] for c in store.inspect()] == [3, 4]
        assert result["retired"] == 1
        latest = store.root / result["id"]
        manifest = json.loads((latest / "manifest.json").read_bytes())
        destination = root / "new-empty-restore"
        destination.mkdir()
        # Only trusted verified paths; never unzip over an existing game world.
        with ZipFile(latest / "archive.zip") as archive:
            for name, expected in manifest["files"].items():
                target = destination / name
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(name) as incoming, target.open("xb") as output:
                    while chunk := incoming.read(MIB):
                        output.write(chunk)
                assert (
                    hashlib.sha256(target.read_bytes()).hexdigest()
                    == expected["sha256"]
                )
        return {
            "published": 4,
            "retained_sequences": [3, 4],
            "restored_files": len(manifest["files"]),
            "restore_readback_verified": True,
            "synthetic_input": True,
        }


def main():
    if len(sys.argv) == 4 and sys.argv[1] == "worker":
        _worker(Path(sys.argv[2]), sys.argv[3])
        return
    if sys.argv[1:] or sys.platform != "linux" or not Path("/small").is_mount():
        raise ValueError("Run only through the disposable backup-safety Docker lab")
    with tempfile.TemporaryDirectory(dir="/scratch") as inputs:
        report = {
            "ok": True,
            "python": sys.version.split()[0],
            "rotation": _rotation_probe("/lab"),
            "disk_full": _enospc_probe("/small", Path(inputs)),
            "process_crashes": [
                _kill_probe("/lab", phase)
                for phase in ("copy", "committed", "retiring", "retired-data-deleted")
            ],
        }
    print(json.dumps(report))


if __name__ == "__main__":
    main()
