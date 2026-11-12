"""Linux-only durable transfer ownership; no live copying, retry or cutover.

One private store must be shared by every controller for a project. A flock
descriptor is passed into restic: killing Python alone does not release the
fence while its child is still alive. Never unlink or explicitly LOCK_UN that
inode. A requested upload is never reissued, even if no snapshot is found.
"""

import json
import os
import shutil
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from omk.fs import regular, resolved
from omk.offsite_process import OffsiteError
from omk.restic_transport import IDENTITY, OPERATION, signature, validate_export

MAX_RECORD = 65536
STAGES = {"prepared", "attempted", "uploaded", "verified"}
OWNER = {"schema": 1, "kind": "omk-offsite-transfer-store"}
KEYS = {
    "schema",
    "operation",
    "repository_id",
    "workspace",
    "settings",
    "expected",
    "stage",
    "receipt",
    "created_at",
    "updated_at",
}


def limits(environment=None):
    env = os.environ if environment is None else environment
    result = {}
    for name, default, low, high in (
        ("RECORDS", 128, 1, 10000),
        ("BYTES", 16 * 1024**2, MAX_RECORD, 1024**3),
    ):
        value = env.get("OMK_OFFSITE_JOB_MAX_" + name, str(default))
        if (
            not isinstance(value, str)
            or not value.isascii()
            or not value.isdecimal()
            or len(value) > 12
            or not low <= int(value) <= high
        ):
            raise OffsiteError("Invalid offsite transfer journal limit")
        result[name.lower()] = int(value)
    return result


def sync(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def private_directory(path):
    if (
        sys.platform != "linux"
        or resolved(path) != path.absolute()
        or not path.is_dir()
        or path.stat().st_mode & 0o077
    ):
        raise OffsiteError(
            "Transfer store requires an explicit private Linux directory"
        )


def read_json(path, root):
    if (
        not regular(path, root)
        or path.stat().st_nlink != 1
        or path.stat().st_mode & 0o077
        or path.stat().st_size > MAX_RECORD
    ):
        raise OffsiteError("Transfer journal is missing, linked, public or oversized")
    try:
        with path.open("rb") as stream:
            data = stream.read(MAX_RECORD + 1)
        if len(data) > MAX_RECORD:
            raise ValueError
        return json.loads(data)
    except ValueError, UnicodeError:
        raise OffsiteError("Invalid transfer journal JSON") from None


class TransferStore:
    def __init__(self, root, *, bounds=None):
        private_directory(root)
        self.root = root
        self.bounds = limits() if bounds is None else bounds
        if (
            set(self.bounds) != {"records", "bytes"}
            or any(type(v) is not int for v in self.bounds.values())
            or not 1 <= self.bounds["records"] <= 10000
            or not MAX_RECORD <= self.bounds["bytes"] <= 1024**3
        ):
            raise OffsiteError("Invalid transfer store capacity")
        if read_json(root / "owner.json", root) != OWNER:
            raise OffsiteError("Unowned transfer store")

    @classmethod
    def create(cls, root, *, bounds=None):
        if sys.platform != "linux" or resolved(root) != root.absolute():
            raise OffsiteError("Transfer store requires an unlinked Linux path")
        root.mkdir(mode=0o700)
        for name, data in (("owner.json", json.dumps(OWNER).encode()), ("lock", b"0")):
            fd = os.open(root / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        sync(root)
        sync(root.parent)
        return cls(root, bounds=bounds)

    @contextmanager
    def lock(self):
        import fcntl  # noqa: PLC0415

        private_directory(self.root)
        if read_json(self.root / "owner.json", self.root) != OWNER:
            raise OffsiteError("Unowned transfer store")
        path = self.root / "lock"
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            st = os.fstat(fd)
            if (
                not regular(path, self.root)
                or st.st_nlink != 1
                or st.st_mode & 0o077
                or st.st_size != 1
            ):
                raise OffsiteError("Invalid transfer ownership lock")
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise OffsiteError(
                    "Transfer store busy; previous worker may still be alive"
                ) from None
            if (path.stat().st_dev, path.stat().st_ino) != (st.st_dev, st.st_ino):
                raise OffsiteError("Transfer ownership lock changed")
            yield fd
        finally:
            # Closing this copy leaves an orphan child's inherited flock intact.
            os.close(fd)

    def path(self, operation):
        if not isinstance(operation, str) or not OPERATION.fullmatch(operation):
            raise OffsiteError("Invalid durable transfer identity")
        return self.root / (operation + ".json")

    def census(self):
        count, total = 0, 0
        for p in self.root.iterdir():
            if p.name in {"owner.json", "lock"}:
                continue
            if (
                not p.name.endswith(".json")
                or not OPERATION.fullmatch(p.stem)
                or not regular(p, self.root)
                or p.stat().st_nlink != 1
                or p.stat().st_mode & 0o077
                or p.stat().st_size > MAX_RECORD
            ):
                raise OffsiteError(
                    "Foreign, incomplete or unsafe transfer journal entry"
                )
            count += 1
            total += p.stat().st_size
            if count > self.bounds["records"] or total > self.bounds["bytes"]:
                raise OffsiteError("Transfer journal capacity exceeded")
        return count, total

    def save(self, record):
        data = json.dumps(record, sort_keys=True, separators=(",", ":")).encode()
        if len(data) > MAX_RECORD:
            raise OffsiteError("Transfer journal exceeds its record bound")
        count, _ = self.census()
        if (
            count * MAX_RECORD > self.bounds["bytes"]
            or shutil.disk_usage(self.root).free
            < 2 * MAX_RECORD + record["settings"]["reserve_bytes"]
        ):
            raise OffsiteError(
                "Transfer journal would violate capacity or project reserve"
            )
        fd, name = tempfile.mkstemp(prefix=".transfer-", suffix=".tmp", dir=self.root)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self.path(record["operation"]))
            sync(self.root)
        finally:
            # A hard interruption leaves this owned temporary for inspection.
            if os.path.exists(name):
                os.unlink(name)

    def read(self, client, operation):
        r = read_json(self.path(operation), self.root)
        try:
            if (
                set(r) != KEYS
                or type(r["schema"]) is not int
                or r["schema"] != 1
                or r["operation"] != operation
                or r["stage"] not in STAGES
                or r["repository_id"] != client.repository_id
                or r["workspace"] != str(client.workspace)
                or r["settings"] != client.settings
                or any(
                    datetime.fromisoformat(r[k]).tzinfo != UTC
                    for k in ("created_at", "updated_at")
                )
            ):
                raise ValueError
            validate_export(r["expected"], client.settings)
            if r["stage"] in {"prepared", "attempted"}:
                if r["receipt"] is not None:
                    raise ValueError
            else:
                receipt = r["receipt"]
                keys = {
                    "snapshot_id",
                    "operation",
                    "repository_id",
                    "export",
                    "data_read_back",
                }
                if r["stage"] == "verified":
                    keys |= {"restored_directory", "ready_for_players"}
                if (
                    set(receipt) != keys
                    or receipt["operation"] != operation
                    or receipt["repository_id"] != r["repository_id"]
                    or receipt["export"] != r["expected"]
                    or not isinstance(receipt["snapshot_id"], str)
                    or not IDENTITY.fullmatch(receipt["snapshot_id"])
                    or receipt["data_read_back"] is not (r["stage"] == "verified")
                    or (
                        r["stage"] == "verified"
                        and receipt["ready_for_players"] is not False
                    )
                ):
                    raise ValueError
        except KeyError, TypeError, ValueError:
            raise OffsiteError("Invalid or rebound durable transfer record") from None
        return r

    def prepare(self, client, source, operation):
        path = self.path(operation)
        with self.lock():
            count, _ = self.census()
            if path.exists():
                raise OffsiteError("Transfer identity already reserved")
            if (
                count >= self.bounds["records"]
                or (count + 1) * MAX_RECORD > self.bounds["bytes"]
                or shutil.disk_usage(self.root).free
                < 2 * MAX_RECORD + client.settings["reserve_bytes"]
            ):
                raise OffsiteError(
                    "Transfer journal would exceed capacity or project reserve"
                )
            client.validate()
            stamp = datetime.now(UTC).isoformat()
            r = {
                "schema": 1,
                "operation": operation,
                "repository_id": client.repository_id,
                "workspace": str(client.workspace),
                "settings": client.settings,
                "expected": signature(source, client.settings),
                "stage": "prepared",
                "receipt": None,
                "created_at": stamp,
                "updated_at": stamp,
            }
            self.save(r)
            return r

    def status(self, client, operation):
        with self.lock():
            self.census()
            return self.read(client, operation)

    def run(self, client, operation, *, recover=False):
        with self.lock() as fd:
            self.census()
            r = self.read(client, operation)
            if r["stage"] == "verified":
                return r
            worker = replace(client, lease_fd=fd)
            if r["stage"] == "prepared":
                if recover:
                    raise OffsiteError(
                        "Transfer not attempted; recovery never starts an upload"
                    )
                source = Path(r["expected"]["source"])
                if signature(source, client.settings) != r["expected"]:
                    raise OffsiteError("Prepared transfer source changed")
                self.transition(r, "attempted")
                receipt = worker.upload(source, operation, expected=r["expected"])
            elif not recover:
                raise OffsiteError(
                    "Upload already attempted; inspect the same transfer"
                )
            else:
                # No second upload, even after a crash before the first spawn.
                receipt = worker.find(operation, r["expected"])
                if receipt is None:
                    raise OffsiteError(
                        "No snapshot confirmed; retain attempted transfer without retry"
                    )
            if receipt["export"] != r["expected"]:
                raise OffsiteError("Upload differs from the durable transfer intent")
            if r["receipt"] and receipt["snapshot_id"] != r["receipt"]["snapshot_id"]:
                raise OffsiteError("Durable transfer snapshot changed")
            r["receipt"] = receipt
            self.transition(r, "uploaded")
            r["receipt"] = worker.restore(receipt)
            self.transition(r, "verified")
            return r

    def transition(self, record, stage):
        record.update(stage=stage, updated_at=datetime.now(UTC).isoformat())
        self.save(record)
