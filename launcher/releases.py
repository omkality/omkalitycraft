"""Signed release contracts. An untrusted CDN cannot change executable artifacts."""

import base64
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from api.core.content_policy import is_private_path
from omk.fs import resolved

MAX_MANIFEST_BYTES = 8 * 1024 * 1024
PLATFORMS = {"windows-x64", "linux-x64", "linux-arm64", "macos-x64", "macos-arm64"}


class ReleaseError(RuntimeError):
    pass


def safe_path(value: str) -> PurePosixPath:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 500
        or "\\" in value
        or ":" in value
    ):
        raise ReleaseError("Недопустимый путь в описании сборки.")
    path = PurePosixPath(value)
    if path.is_absolute() or any(p in {"", ".", ".."} for p in value.split("/")):
        raise ReleaseError("Недопустимый путь в описании сборки.")
    if is_private_path(value) or any(p.startswith(".omk-") for p in path.parts):
        raise ReleaseError("Описание сборки содержит служебный путь.")
    if path.parts[0].casefold() in {
        "saves",
        "world",
        "logs",
        "screenshots",
        "journeymap",
        "backups",
        "options.txt",
        "servers.dat",
    }:
        raise ReleaseError("Сборка не может управлять личными файлами игрока.")
    reserved = {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    }
    if any(
        p.rstrip(". ") != p
        or p.split(".")[0].upper() in reserved
        or any(ord(c) < 32 for c in p)
        for p in path.parts
    ):
        raise ReleaseError("Путь несовместим с переносимой установкой.")
    return path


def inside(root: Path, relative: str) -> Path:
    path = root.joinpath(*safe_path(relative).parts)
    if not resolved(path).is_relative_to(resolved(root)):
        raise ReleaseError("Путь выходит за пределы папки сборки.")
    return path


def canonical(value: dict[str, Any]) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class Artifact:
    path: str
    sha256: str
    size: int
    executable: bool = False


def _validate_artifacts(files: tuple[Artifact, ...]) -> set[str]:
    names: set[str] = set()
    for file in files:
        safe_path(file.path)
        if file.path.casefold() in names or not re.fullmatch(
            r"[a-f0-9]{64}", file.sha256
        ):
            raise ValueError
        if (
            type(file.size) is not int
            or not 0 <= file.size <= 2 * 1024**3
            or type(file.executable) is not bool
        ):
            raise ValueError
        names.add(file.path.casefold())
    if sum(file.size for file in files) > 50 * 1024**3:
        raise ValueError
    return names


@dataclass(frozen=True)
class Release:
    pack_id: str
    version: str
    minecraft: str
    platform: str
    files: tuple[Artifact, ...]
    launch: dict[str, Any]
    digest: str
    envelope: dict[str, Any]

    @property
    def total_size(self) -> int:
        return sum(file.size for file in self.files)

    @classmethod
    def parse(cls, payload: dict[str, Any], envelope: dict[str, Any]) -> Release:
        try:
            if (
                payload["schema"] != 1
                or payload["loader"] != "forge"
                or payload["platform"] not in PLATFORMS
            ):
                raise ValueError
            if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,47}", payload["pack_id"]):
                raise ValueError
            if (
                not isinstance(payload["version"], str)
                or not 1 <= len(payload["version"]) <= 80
            ):
                raise ValueError
            if (
                not isinstance(payload["files"], list)
                or not 1 <= len(payload["files"]) <= 30000
            ):
                raise ValueError
            files = tuple(Artifact(**file) for file in payload["files"])
            names = _validate_artifacts(files)
            launch = payload["launch"]
            if launch["main_class"] != "net.minecraft.launchwrapper.Launch":
                raise ValueError
            if not launch["classpath"] or len(launch["classpath"]) > 500:
                raise ValueError
            for name in [launch["java"], launch["agent"], *launch["classpath"]]:
                safe_path(name)
                if name.casefold() not in names:
                    raise ValueError
            safe_path(launch["natives"])
            safe_path(launch["assets"])
            return cls(
                payload["pack_id"],
                payload["version"],
                payload["minecraft"],
                payload["platform"],
                files,
                launch,
                hashlib.sha256(canonical(payload)).hexdigest(),
                envelope,
            )
        except KeyError, TypeError, ValueError:
            raise ReleaseError(
                "Описание сборки повреждено или не поддерживается."
            ) from None


def read_release(data: bytes, trusted_keys: dict[str, str]) -> Release:
    if len(data) > MAX_MANIFEST_BYTES:
        raise ReleaseError("Описание сборки превышает допустимый размер.")
    try:
        envelope = json.loads(data)
        key = Ed25519PublicKey.from_public_bytes(
            base64.b64decode(trusted_keys[envelope["key_id"]], validate=True)
        )
        key.verify(
            base64.b64decode(envelope["signature"], validate=True),
            canonical(envelope["manifest"]),
        )
        return Release.parse(envelope["manifest"], envelope)
    except KeyError, ValueError, TypeError, InvalidSignature:
        raise ReleaseError(
            "Не удалось подтвердить подлинность сборки. Загрузка остановлена."
        ) from None


def sign_release(
    payload: dict[str, Any], private_key: Ed25519PrivateKey
) -> dict[str, Any]:
    Release.parse(payload, {})
    public = private_key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    return {
        "key_id": hashlib.sha256(public).hexdigest()[:16],
        "manifest": payload,
        "signature": base64.b64encode(private_key.sign(canonical(payload))).decode(),
    }
