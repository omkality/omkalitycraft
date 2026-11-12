"""REST/TLS transport primitives for sealed exports, not a backup scheduler.

The owner must serialize jobs and persist transfer identity before upload. An
uncertain result is inspected by that identity, never automatically retried.
This module does not copy a live world/SQLite, rotate repositories, or cut over
restored services. Every restore uses a fresh private directory for inspection.
"""

import hashlib
import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from omk.fs import regular, resolved
from omk.offsite_process import OffsiteError, bounded
from omk.profiles import PROJECT_ROOT
from omk.storage_policy import storage_plan

HOST = "omkality-offsite"
IDENTITY = re.compile(r"[a-f0-9]{64}")
OPERATION = re.compile(r"[a-f0-9]{32}")
FILENAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}")


def policy(environment=None):
    env = os.environ if environment is None else environment
    result = {}
    for key, default, low, high in (
        ("TIMEOUT_SECONDS", 900, 1, 7200),
        ("OUTPUT_BYTES", 262144, 1024, 4 * 1024**2),
        ("UPLOAD_KIB", 10240, 64, 1048576),
        ("GOMAXPROCS", 1, 1, 4),
        ("MAX_BYTES", 16 * 1024**3, 1, 1024**4),
        ("MAX_FILES", 32, 1, 128),
    ):
        raw = env.get("OMK_OFFSITE_" + key, str(default))
        if (
            not isinstance(raw, str)
            or not raw.isascii()
            or not raw.isdecimal()
            or len(raw) > 15
            or not low <= int(raw) <= high
        ):
            raise OffsiteError("Invalid OMK_OFFSITE_" + key)
        result[key.lower()] = int(raw)
    budget = storage_plan(env)
    if not budget["ok"]:
        raise OffsiteError(budget["error"])
    result["reserve_bytes"] = budget["budgets_gib"]["reserve"] * 1024**3
    return result


def credential_path(root, name):
    path = root / name
    if resolved(path) != path.absolute() or not path.absolute().is_relative_to(root):
        raise OffsiteError(
            "Offsite credentials must stay inside their private directory"
        )
    return path


def private_text(root, name, maximum=8192):
    path = credential_path(root, name)
    if (
        not regular(path, root)
        or path.stat().st_nlink != 1
        or (os.name != "nt" and path.stat().st_mode & 0o077)
    ):
        raise OffsiteError("Offsite credentials require private unlinked files")
    with path.open("rb") as stream:
        raw = stream.read(maximum + 1)
    try:
        value = raw.decode("utf-8").removesuffix("\r\n").removesuffix("\n")
        if (
            len(raw) > maximum
            or not value
            or any(x in value for x in ("\n", "\r", "\0"))
        ):
            raise ValueError
    except ValueError, UnicodeError:
        raise OffsiteError("Invalid offsite credential file") from None
    return value


def signature(source, settings):
    """A small flat set of already prepared archives, never a live game tree."""
    if resolved(source) != source.absolute() or not source.is_dir():
        raise OffsiteError(
            "Offsite input must be an explicit unlinked export directory"
        )
    inventory, total = {}, 0
    before = source.stat()
    for path in source.iterdir():
        if (
            not FILENAME.fullmatch(path.name)
            or not regular(path, source)
            or path.stat().st_nlink != 1
        ):
            raise OffsiteError("Offsite export contains a linked or unsupported entry")
        stamp = path.stat()
        size = stamp.st_size
        total += size
        if total > settings["max_bytes"] or len(inventory) >= settings["max_files"]:
            raise OffsiteError("Offsite export exceeds its byte or file bound")
        digest = hashlib.sha256()
        read_bytes = 0
        with path.open("rb") as stream:
            while block := stream.read(1024**2):
                read_bytes += len(block)
                if read_bytes > size:
                    raise OffsiteError("Offsite export grew while hashing")
                digest.update(block)
        after = path.stat()
        if read_bytes != size or any(
            getattr(stamp, k) != getattr(after, k)
            for k in ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        ):
            raise OffsiteError("Offsite export changed while hashing")
        inventory[path.name] = {"bytes": size, "sha256": digest.hexdigest()}
    if not inventory:
        raise OffsiteError("Offsite export is empty")
    if source.stat().st_mtime_ns != before.st_mtime_ns:
        raise OffsiteError("Offsite export entries changed while hashing")
    value = {"source": str(source), "files": inventory, "bytes": total}
    value["sha256"] = hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return value


def validate_export(value, settings):
    try:
        if (
            set(value) != {"source", "files", "bytes", "sha256"}
            or not isinstance(value["source"], str)
            or not Path(value["source"]).is_absolute()
            or str(Path(value["source"])) != value["source"]
            or ".." in Path(value["source"]).parts
            or len(Path(value["source"]).parts) > 16
            or not isinstance(value["files"], dict)
            or not 1 <= len(value["files"]) <= settings["max_files"]
            or type(value["bytes"]) is not int
            or not 0 <= value["bytes"] <= settings["max_bytes"]
            or not isinstance(value["sha256"], str)
            or not IDENTITY.fullmatch(value["sha256"])
        ):
            raise ValueError
        for name, entry in value["files"].items():
            if (
                not isinstance(name, str)
                or not FILENAME.fullmatch(name)
                or set(entry) != {"bytes", "sha256"}
                or type(entry["bytes"]) is not int
                or entry["bytes"] < 0
                or not isinstance(entry["sha256"], str)
                or not IDENTITY.fullmatch(entry["sha256"])
            ):
                raise ValueError
        core = {k: v for k, v in value.items() if k != "sha256"}
        if (
            sum(e["bytes"] for e in value["files"].values()) != value["bytes"]
            or hashlib.sha256(
                json.dumps(core, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            != value["sha256"]
        ):
            raise ValueError
    except KeyError, TypeError, ValueError:
        raise OffsiteError("Invalid frozen offsite export receipt") from None


@dataclass(frozen=True, repr=False)
class Restic:
    credential_root: Path
    workspace: Path
    repository_id: str
    settings: dict
    binary: Path = Path("/usr/local/bin/restic")

    def validate(self):
        if not isinstance(self.repository_id, str) or not IDENTITY.fullmatch(
            self.repository_id
        ):
            raise OffsiteError("Offsite repository identity must be pinned")
        endpoint = private_text(self.credential_root, "repository")
        private_text(self.credential_root, "password")
        try:
            value = urlsplit(endpoint.removeprefix("rest:"))
            if (
                not endpoint.startswith("rest:https://")
                or not value.hostname
                or not value.username
                or not value.password
                or value.query
                or value.fragment
                or not value.path.endswith("/")
            ):
                raise ValueError
            _ = value.port
        except ValueError:
            raise OffsiteError(
                "Offsite transport requires an explicit authenticated REST/TLS repository"
            ) from None
        ca = credential_path(self.credential_root, "ca.pem")
        if (
            not regular(ca, self.credential_root)
            or ca.stat().st_nlink != 1
            or not 1 <= ca.stat().st_size <= 65536
        ):
            raise OffsiteError("Offsite TLS trust file is missing or too large")
        pins = json.loads((PROJECT_ROOT / "deploy/offsite-tools.json").read_bytes())
        expected = next(
            a["binary_sha256"] for a in pins["artifacts"] if a["name"] == "restic"
        )
        if not self.binary.is_file() or self.binary.is_symlink():
            raise OffsiteError("Pinned offsite binary is missing")
        with self.binary.open("rb") as stream:
            actual = hashlib.file_digest(stream, "sha256").hexdigest()
        if actual != expected:
            raise OffsiteError("Offsite binary differs from its reviewed artifact pin")
        if (
            resolved(self.workspace) != self.workspace.absolute()
            or not self.workspace.is_dir()
            or (os.name != "nt" and self.workspace.stat().st_mode & 0o077)
        ):
            raise OffsiteError(
                "Offsite workspace must be an explicit private directory"
            )

    def invoke(self, *args):
        # No inherited proxy, password-command, repository, hook or AWS settings.
        self.validate()
        environment = {
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "HOME": str(self.workspace),
            "TMPDIR": str(self.workspace),
            "RESTIC_REPOSITORY_FILE": str(self.credential_root / "repository"),
            "RESTIC_PASSWORD_FILE": str(self.credential_root / "password"),
            "RESTIC_CACERT": str(self.credential_root / "ca.pem"),
            "GOMAXPROCS": str(self.settings["gomaxprocs"]),
        }
        if not args or args[0] not in {
            "cat",
            "snapshots",
            "backup",
            "check",
            "restore",
        }:
            raise OffsiteError("Unsupported offsite transport action")
        if args[0] in {"cat", "snapshots", "restore"}:
            # Metadata reads and immutable-snapshot restore do not write remote
            # locks. This remains usable on a full/read-only repository.
            # Concurrent external pruning may cause a refusal, never acceptance
            # of missing bytes: restic verify and our exact file hashes follow.
            args = (*args, "--no-lock")
        return bounded(
            [
                str(self.binary),
                "--no-cache",
                "--json",
                "--quiet",
                "--limit-upload",
                str(self.settings["upload_kib"]),
                *args,
            ],
            environment=environment,
            directory=self.workspace,
            timeout=self.settings["timeout_seconds"],
            maximum=self.settings["output_bytes"],
        )

    def inspect(self):
        value = json.loads(self.invoke("cat", "config"))
        if value.get("id") != self.repository_id or value.get("version") != 2:
            raise OffsiteError("Offsite repository identity or format changed")
        return {"repository_id": self.repository_id, "format": 2}

    def find(self, operation, expected):
        if not isinstance(operation, str) or not OPERATION.fullmatch(operation):
            raise OffsiteError("Invalid offsite transfer identity")
        validate_export(expected, self.settings)
        self.inspect()
        value = json.loads(self.invoke("snapshots", "--tag", "omk-op=" + operation))
        if not isinstance(value, list) or len(value) > 1:
            raise OffsiteError("Offsite snapshot identity is ambiguous")
        if not value:
            return None
        r = value[0]
        if (
            not IDENTITY.fullmatch(r.get("id", ""))
            or r.get("hostname") != HOST
            or r.get("paths") != [expected["source"]]
            or sorted(r.get("tags", []))
            != sorted(["omk-op=" + operation, "omk-sha=" + expected["sha256"]])
        ):
            raise OffsiteError(
                "Offsite snapshot differs from its frozen transfer scope"
            )
        return {
            "snapshot_id": r["id"],
            "operation": operation,
            "repository_id": self.repository_id,
            "export": expected,
            "data_read_back": False,
        }

    def upload(self, source, operation):
        expected = signature(source, self.settings)
        if self.find(operation, expected) is not None:
            raise OffsiteError(
                "Offsite transfer already exists; inspect the same identity instead of uploading again"
            )
        result = self.invoke(
            "backup",
            "--host",
            HOST,
            "--tag",
            "omk-op=" + operation,
            "--tag",
            "omk-sha=" + expected["sha256"],
            str(source),
        )
        rows = [json.loads(line) for line in result.splitlines()]
        if (
            len(rows) != 1
            or rows[0].get("message_type") != "summary"
            or not rows[0].get("snapshot_id")
        ):
            raise OffsiteError(
                "Offsite upload acknowledgement is missing; inspect the same identity"
            )
        if signature(source, self.settings) != expected:
            raise OffsiteError(
                "Offsite source changed; do not accept the upload receipt"
            )
        receipt = self.find(operation, expected)
        if receipt is None:
            raise OffsiteError(
                "Offsite snapshot not confirmed; inspect the same identity"
            )
        return receipt

    def check(self):
        self.inspect()
        self.invoke("check", "--read-data")
        return {"repository_id": self.repository_id, "all_repository_data_read": True}

    def restore(self, receipt):
        # Verification goes into fresh private staging, never an existing world.
        if receipt.get("repository_id") != self.repository_id:
            raise OffsiteError("Offsite restore receipt belongs to another repository")
        self.inspect()
        expected = receipt["export"]
        confirmed = self.find(receipt["operation"], expected)
        if confirmed is None or confirmed["snapshot_id"] != receipt["snapshot_id"]:
            raise OffsiteError("Offsite restore receipt changed")
        if (
            shutil.disk_usage(self.workspace).free
            < expected["bytes"] + self.settings["reserve_bytes"]
        ):
            raise OffsiteError("Offsite restore would violate the project disk reserve")
        target = Path(tempfile.mkdtemp(prefix="restore-", dir=self.workspace))
        self.invoke(
            "restore", receipt["snapshot_id"], "--target", str(target), "--verify"
        )
        restored = target / Path(expected["source"]).relative_to("/")
        directories = {
            str(p.relative_to(target))
            for p in [restored, *restored.parents]
            if p != target and p.is_relative_to(target)
        }
        allowed = directories | {
            str((restored / name).relative_to(target)) for name in expected["files"]
        }
        seen = set()
        for path in target.rglob("*"):
            relative = str(path.relative_to(target))
            if relative not in allowed or path.is_symlink() or path.is_junction():
                raise OffsiteError(
                    "Unexpected offsite restore entry; retain isolated staging"
                )
            seen.add(relative)
        if seen != allowed:
            raise OffsiteError("Incomplete offsite restore; retain isolated staging")
        actual = signature(restored, self.settings)
        if actual["files"] != expected["files"] or actual["bytes"] != expected["bytes"]:
            raise OffsiteError(
                "Offsite restored bytes differ; retain isolated staging for inspection"
            )
        return {
            **receipt,
            "data_read_back": True,
            "restored_directory": str(restored),
            "ready_for_players": False,
        }
