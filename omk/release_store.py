"""Explicit immutable copies of signed client payloads, never worlds or auth data."""

import json
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from uuid import uuid4

from launcher.releases import (
    MAX_MANIFEST_BYTES,
    Release,
    canonical,
    inside,
    read_release,
    sha256_file,
)
from omk.backup_store import _directory, _json_write, _lock, _sync_directory
from omk.fs import regular, resolved

OWNER = {"schema": 1, "kind": "omk-managed-client-release-store"}
DIGEST = re.compile(r"[a-f0-9]{64}")


@dataclass(frozen=True)
class ReleaseStorePolicy:
    max_bytes: int = 32 * 1024**3
    reserve_bytes: int = 1024**3
    max_count: int = 64

    def __post_init__(self):
        if (
            any(
                type(n) is not int or not 1 <= n <= 1024**4 for n in vars(self).values()
            )
            or not 2 <= self.max_count <= 1024
        ):
            raise ValueError("Invalid release snapshot storage policy")

    @classmethod
    def environment(cls, environment=None):
        env = os.environ if environment is None else environment
        defaults = cls()
        values = {}
        for field, key in [
            ("max_bytes", "OMK_RELEASE_SNAPSHOT_MAX_BYTES"),
            ("reserve_bytes", "OMK_RELEASE_SNAPSHOT_RESERVE_BYTES"),
            ("max_count", "OMK_RELEASE_SNAPSHOT_MAX_COUNT"),
        ]:
            raw = env.get(key, str(getattr(defaults, field)))
            if not isinstance(raw, str) or not re.fullmatch(r"[0-9]{1,13}", raw):
                raise ValueError("Invalid release snapshot storage configuration")
            values[field] = int(raw)
        return cls(**values)


@dataclass(frozen=True)
class ReleaseSnapshot:
    directory: Path
    release: Release
    bytes: int

    @property
    def files(self) -> Path:
        return self.directory / "files"


def _read_manifest(path: Path, boundary: Path, keys) -> Release:
    if not regular(path, boundary) or path.stat().st_size > MAX_MANIFEST_BYTES:
        raise ValueError("Invalid stored release manifest")
    with path.open("rb") as stream:
        return read_release(stream.read(MAX_MANIFEST_BYTES + 1), keys)


def _verify_generation(path: Path, keys, expected_digest: str) -> ReleaseSnapshot:
    _directory(path)
    release = _read_manifest(path / "manifest.json", path, keys)
    if release.digest != expected_digest:
        raise ValueError("Stored release identity changed")
    expected = {"manifest.json", *("files/" + f.path for f in release.files)}
    directories = {"files"} | {
        str(p)
        for name in expected
        for p in PurePosixPath(name).parents
        if str(p) != "."
    }
    actual = set()
    size = 0
    for entry in path.rglob("*"):
        name = entry.relative_to(path).as_posix()
        if entry.is_symlink() or entry.is_junction():
            raise ValueError("Linked release snapshot content")
        if entry.is_dir():
            if name not in directories:
                raise ValueError("Foreign release snapshot directory")
            continue
        if not regular(entry, path):
            raise ValueError("Nonregular release snapshot content")
        actual.add(name)
        size += entry.stat().st_size
    if actual != expected:
        raise ValueError("Incomplete or foreign release snapshot")
    for artifact in release.files:
        entry = inside(path / "files", artifact.path)
        if (
            entry.stat().st_size != artifact.size
            or sha256_file(entry) != artifact.sha256
        ):
            raise ValueError("Stored release payload changed")
    return ReleaseSnapshot(path, release, size)


class ReleaseStore:
    def __init__(self, root: Path, policy: ReleaseStorePolicy, keys):
        if root.is_symlink() or root.is_junction():
            raise ValueError("Linked release store")
        self.root, self.policy, self.keys = resolved(root), policy, dict(keys)
        _directory(self.root)
        self._owner()

    def _owner(self):
        path = self.root / "owner.json"
        if not regular(path, self.root) or path.stat().st_size > 1024:
            raise ValueError("Unowned release store")
        if json.loads(path.read_bytes()) != OWNER:
            raise ValueError("Unowned release store")

    @classmethod
    def create(cls, root: Path, policy: ReleaseStorePolicy, keys):
        """Create a new dedicated directory; never adopt an existing directory."""
        _directory(resolved(root.parent))
        root.mkdir()
        _json_write(root / "owner.json", OWNER)
        with (root / "lock").open("xb") as stream:
            stream.write(b"0")
            stream.flush()
            os.fsync(stream.fileno())
        _sync_directory(root)
        _sync_directory(root.parent)
        return cls(root, policy, keys)

    def _entries(self):
        self._owner()
        result = []
        for path in self.root.iterdir():
            if path.name in {"owner.json", "lock"}:
                if not regular(path, self.root):
                    raise ValueError("Invalid release store control file")
                continue
            if not DIGEST.fullmatch(path.name):
                raise ValueError(
                    "Foreign or interrupted release snapshot needs inspection"
                )
            if len(result) >= self.policy.max_count:
                raise ValueError("Release snapshot count budget exceeded")
            result.append(_verify_generation(path, self.keys, path.name))
        return result

    def verify(self, digest: str) -> ReleaseSnapshot:
        if not isinstance(digest, str) or not DIGEST.fullmatch(digest):
            raise ValueError("Invalid release snapshot identity")
        with _lock(self.root, read_only=True):
            self._owner()
            return _verify_generation(self.root / digest, self.keys, digest)

    def publish(self, source: Path, envelope: dict) -> ReleaseSnapshot:
        # The signature is checked again; mutable caller dictionaries are not trust.
        if set(envelope) != {"manifest", "key_id", "signature"}:
            raise ValueError("Unexpected release envelope fields")
        raw = canonical(envelope)
        release = read_release(raw, self.keys)
        if source.is_symlink() or source.is_junction():
            raise ValueError("Linked release source")
        source = resolved(source)
        _directory(source)
        if source.is_relative_to(self.root) or self.root.is_relative_to(source):
            raise ValueError("Release source and snapshot store must be separate")
        with _lock(self.root):
            snapshots = self._entries()
            for snapshot in snapshots:
                if snapshot.release.digest == release.digest:
                    return snapshot
                if (
                    snapshot.release.pack_id,
                    snapshot.release.platform,
                    snapshot.release.version,
                ) == (release.pack_id, release.platform, release.version):
                    raise ValueError("Changed release content requires a new version")
            if len(snapshots) >= self.policy.max_count:
                raise ValueError(
                    "Release snapshot count budget exceeded; no copies removed"
                )
            incoming = release.total_size + len(raw)
            if sum(s.bytes for s in snapshots) + incoming > self.policy.max_bytes:
                raise ValueError(
                    "Release snapshot storage budget exceeded; no copies removed"
                )
            if shutil.disk_usage(self.root).free < incoming + self.policy.reserve_bytes:
                raise ValueError("Insufficient free space for release snapshot")
            return self._stage(source, raw, release)

    def _stage(self, source: Path, raw: bytes, release: Release) -> ReleaseSnapshot:
        stage = self.root / ("pending-" + uuid4().hex)
        stage.mkdir()
        try:
            for artifact in release.files:
                self._copy(source, stage, artifact)
            with (stage / "manifest.json").open("xb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            _verify_generation(stage, self.keys, release.digest)
            for path in sorted(
                (p for p in stage.rglob("*") if p.is_dir()),
                key=lambda p: len(p.parts),
                reverse=True,
            ):
                _sync_directory(path)
            _sync_directory(stage)
            destination = self.root / release.digest
            if (
                destination.exists()
                or destination.is_symlink()
                or destination.is_junction()
            ):
                raise ValueError("Refusing to replace an existing release snapshot")
            stage.rename(destination)
            _sync_directory(self.root)
            return _verify_generation(destination, self.keys, release.digest)
        finally:
            if stage.exists():
                # Only our fresh staging directory, never an existing generation.
                if resolved(stage).parent != self.root or not re.fullmatch(
                    r"pending-[a-f0-9]{32}", stage.name
                ):
                    raise ValueError("Unsafe release staging cleanup")
                shutil.rmtree(stage)

    @staticmethod
    def _copy(source, stage, artifact):
        incoming = inside(source, artifact.path)
        if not regular(incoming, source):
            raise ValueError("Missing or linked release payload")
        target = inside(stage / "files", artifact.path)
        target.parent.mkdir(parents=True, exist_ok=True)
        count = 0
        with incoming.open("rb") as reader, target.open("xb") as writer:
            while chunk := reader.read(min(1024**2, artifact.size - count + 1)):
                count += len(chunk)
                if count > artifact.size:
                    raise ValueError("Release payload changed during copying")
                writer.write(chunk)
            writer.flush()
            if os.name != "nt":
                os.fchmod(writer.fileno(), 0o755 if artifact.executable else 0o644)
            os.fsync(writer.fileno())
        if count != artifact.size or sha256_file(target) != artifact.sha256:
            raise ValueError("Release payload changed during copying")
