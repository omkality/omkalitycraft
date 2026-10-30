"""Offline release preparation. Private signing keys never belong to the CDN."""

import json
import os
import re
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from packaging.version import Version
from securesystemslib.signer import CryptoSigner
from tuf.api.metadata import (
    Metadata,
    MetaFile,
    Root,
    Snapshot,
    TargetFile,
    Targets,
    Timestamp,
)

from launcher.install import current_platform
from launcher.releases import PLATFORMS, safe_path, sha256_file
from launcher.updater import MAX_ARCHIVE, LauncherUpdater


def _signer(folder: Path, role: str) -> CryptoSigner:
    path = folder / f"{role}.pem"
    if not path.exists():
        folder.mkdir(parents=True, exist_ok=True)
        key = Ed25519PrivateKey.generate()
        with path.open("xb") as file:
            file.write(
                key.private_bytes(
                    serialization.Encoding.PEM,
                    serialization.PrivateFormat.PKCS8,
                    serialization.NoEncryption(),
                )
            )
        path.chmod(0o600)
    return CryptoSigner(
        serialization.load_pem_private_key(path.read_bytes(), password=None)
    )


def publish_update(
    repository: Path,
    keys: Path,
    archive: Path,
    version: str,
    entrypoint: str,
    *,
    platform: str | None = None,
    now: datetime | None = None,
) -> Path:
    """Sign one platform bundle while retaining targets for other platforms."""
    import zipfile  # noqa: PLC0415

    if keys.resolve().is_relative_to(repository.resolve()):
        raise ValueError("Private signing keys must be outside the public repository")
    platform = platform or current_platform()
    if platform not in PLATFORMS or archive.stat().st_size > MAX_ARCHIVE:
        raise ValueError("Unsupported platform or archive size")
    Version(version)
    safe_path(entrypoint)
    with zipfile.ZipFile(archive) as bundle:
        LauncherUpdater._validate_zip(bundle.infolist())
        if entrypoint not in bundle.namelist():
            raise ValueError("Entrypoint missing from bundle")
    now = now or datetime.now(UTC)
    signers = {
        role: _signer(keys, role)
        for role in ["root", "targets", "snapshot", "timestamp"]
    }
    metadata = repository / "metadata"
    metadata.mkdir(parents=True, exist_ok=True)
    root_path = _root(metadata, signers, now)
    targets_path = metadata / "targets.json"
    if targets_path.exists():
        previous = Metadata.from_file(str(targets_path)).signed
        counter, retained = previous.version + 1, dict(previous.targets)
    else:
        counter, retained = 1, {}
    target_name = f"{platform}/launcher.zip"
    _validate_version(retained.get(target_name), version, archive)
    consistent = Metadata.from_file(str(root_path)).signed.consistent_snapshot
    storage_name = (
        f"{platform}/{sha256_file(archive)}.launcher.zip" if consistent else target_name
    )
    destination = repository / "targets" / storage_name
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".tmp")
    if not destination.exists() or sha256_file(destination) != sha256_file(archive):
        shutil.copyfile(archive, temporary)
        os.replace(temporary, destination)
    target = TargetFile.from_file(target_name, str(destination), ["sha256"])
    target.unrecognized_fields["custom"] = {
        "version": version,
        "entrypoint": entrypoint,
    }
    retained[target_name] = target
    targets = Metadata(
        Targets(version=counter, expires=now + timedelta(days=90), targets=retained)
    )
    targets.sign(signers["targets"])
    snapshot = Metadata(
        Snapshot(
            version=counter,
            expires=now + timedelta(days=90),
            meta={
                "targets.json": MetaFile.from_data(
                    counter, targets.to_bytes(), ["sha256"]
                )
            },
        )
    )
    snapshot.sign(signers["snapshot"])
    timestamp = Metadata(
        Timestamp(
            version=counter,
            expires=now + timedelta(days=30),
            snapshot_meta=MetaFile.from_data(counter, snapshot.to_bytes(), ["sha256"]),
        )
    )
    timestamp.sign(signers["timestamp"])
    for name, document in [
        ("targets", targets),
        ("snapshot", snapshot),
        ("timestamp", timestamp),
    ]:
        if consistent and name != "timestamp":
            document.to_file(str(metadata / f"{counter}.{name}.json"))
        temporary = metadata / f"{name}.tmp"
        document.to_file(str(temporary))
        os.replace(temporary, metadata / f"{name}.json")
    (repository / "release.json").write_text(
        json.dumps(
            {"version": version, "platform": platform, "metadata_version": counter}
        ),
        encoding="utf-8",
    )
    return root_path


def _root(metadata: Path, signers: dict[str, CryptoSigner], now: datetime) -> Path:
    roots = [
        path
        for path in metadata.glob("*.root.json")
        if re.fullmatch(r"[1-9][0-9]*\.root\.json", path.name)
    ]
    root_path = (
        max(roots, key=lambda path: int(path.name.split(".")[0]))
        if roots
        else metadata / "1.root.json"
    )
    if not root_path.exists():
        root = Root(
            version=1, expires=now + timedelta(days=1095), consistent_snapshot=True
        )
        for role, signer in signers.items():
            root.add_key(signer.public_key, role)
        document = Metadata(root)
        document.sign(signers["root"])
        document.to_file(str(root_path))
    else:
        # Key rotation is a separate explicit operation, never an accidental overwrite.
        root = Metadata.from_file(str(root_path)).signed
        for role, signer in signers.items():
            if signer.public_key.keyid not in root.roles[role].keyids:
                raise ValueError("Signing key differs from the trusted root")
    return root_path


def _validate_version(
    previous_target: TargetFile | None, version: str, archive: Path
) -> None:
    if previous_target is not None and Version(version) < Version(
        previous_target.custom["version"]
    ):
        raise ValueError("Refusing to publish an older launcher")
    if (
        previous_target is not None
        and Version(version) == Version(previous_target.custom["version"])
        and previous_target.hashes["sha256"] != sha256_file(archive)
    ):
        raise ValueError("Changed launcher contents require a new version")
