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
from packaging.version import Version

from launcher.pack.client_policy import JOURNEYMAP_PREFERENCES_CONFIGS, ClientDefaults
from launcher.version import VERSION
from omk.shared.content_policy import is_private_path
from omk.shared.fs import resolved

MAX_MANIFEST_BYTES = 8 * 1024 * 1024
MAX_GENERATION = 2**63 - 1
PLATFORMS = {"windows-x64", "linux-x64", "linux-arm64", "macos-x64", "macos-arm64"}


class ReleaseError(RuntimeError):
    """Report an invalid, unavailable or unsupported game release."""

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
    """Describe one signed file, including its size, hash and executable bit."""

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


def valid_generation(value: object) -> bool:
    """Validate a positive signed generation or deployment floor."""
    return type(value) is int and 1 <= value <= MAX_GENERATION


def generation_floors(value: object) -> dict[str, int]:
    """Read build-time pack floors shared across the packaged platforms."""
    if not isinstance(value, dict) or any(
        not isinstance(pack, str)
        or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,47}", pack)
        or not valid_generation(generation)
        for pack, generation in value.items()
    ):
        raise ValueError("Invalid minimum pack generations")
    return dict(value)


def _pack_generation(payload: dict[str, Any]) -> int | None:
    generation = payload.get("generation")
    if payload["schema"] == 3:
        if not valid_generation(generation):
            raise ValueError("Invalid release generation")
    elif "generation" in payload:
        raise ValueError("Release generations need schema 3")
    return generation


def _minimum_launcher(payload: dict[str, Any]) -> str | None:
    schema = payload["schema"]
    if type(schema) is not int or schema not in {1, 2, 3}:
        raise ValueError("Unsupported release schema")
    if schema in {2, 3}:
        minimum = payload.get("minimum_launcher_version")
        if not isinstance(minimum, str) or not re.fullmatch(
            r"[0-9][A-Za-z0-9.!+_-]{0,79}", minimum
        ):
            raise ValueError("Invalid minimum launcher version")
        Version(minimum)
        return minimum
    if "minimum_launcher_version" in payload:
        raise ValueError("Launcher requirements need schema 2")
    return None


def _require_default_capabilities(defaults: dict, minimum: str | None) -> None:
    for field, version in (
        ("initial_keybindings", "0.3.0.dev12"),
        ("initial_options", "0.3.0.dev13"),
    ):
        if field in defaults and (
            minimum is None or Version(minimum) < Version(version)
        ):
            raise ValueError(f"{field} requires minimum launcher {version}")
    if any(
        config["path"] in JOURNEYMAP_PREFERENCES_CONFIGS
        for config in defaults.get("initial_configs", ())
    ) and (minimum is None or Version(minimum) < Version("0.3.0.dev17")):
        raise ValueError(
            "JourneyMap core and waypoint defaults require launcher 0.3.0.dev17"
        )


@dataclass(frozen=True)
class Release:
    """Represent a verified pack manifest for a specific platform."""

    pack_id: str
    version: str
    minecraft: str
    platform: str
    files: tuple[Artifact, ...]
    launch: dict[str, Any]
    digest: str
    envelope: dict[str, Any]
    minimum_launcher_version: str | None = None
    generation: int | None = None

    def require_launcher(self, running_version: str = VERSION) -> None:
        """Reject a release that needs a newer launcher."""
        if self.minimum_launcher_version is not None and Version(
            running_version
        ) < Version(self.minimum_launcher_version):
            raise ReleaseError(
                "Нужно обновление лаунчера. Проверьте соединение и перезапустите OmkalityCraft."
            )

    @property
    def total_size(self) -> int:
        """Return the total signed size of the release's files."""
        return sum(file.size for file in self.files)

    @classmethod
    def parse(cls, payload: dict[str, Any], envelope: dict[str, Any]) -> Release:
        """Decode and validate the manifest payload and its launch fields."""
        try:
            minimum = _minimum_launcher(payload)
            generation = _pack_generation(payload)
            if payload["loader"] != "forge" or payload["platform"] not in PLATFORMS:
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
            _validate_jvm_args(launch.get("jvm_args", []))
            defaults = ClientDefaults.parse(launch.get("client_defaults", {}))
            _require_default_capabilities(launch.get("client_defaults", {}), minimum)
            for name in defaults.resourcepacks:
                path = (
                    "resourcepacks/"
                    + name
                    + ("" if name.endswith(".zip") else "/pack.mcmeta")
                )
                if path.casefold() not in names:
                    raise ValueError
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
                minimum,
                generation,
            )
        except KeyError, TypeError, ValueError:
            raise ReleaseError(
                "Описание сборки повреждено или не поддерживается."
            ) from None


def _validate_jvm_args(arguments: list) -> None:
    if not isinstance(arguments, list) or len(arguments) > 100:
        raise ValueError("Invalid JVM arguments")
    for argument in arguments:
        if (
            not isinstance(argument, str)
            or len(argument) > 1000
            or argument.startswith(
                (
                    "-Xmx",
                    "-Xms",
                    "-XX:MaxRAM",
                    "-XX:InitialRAM",
                    "-XX:MaxHeapSize",
                    "-XX:InitialHeapSize",
                    "-XX:MinHeapSize",
                )
            )
        ):
            raise ValueError("Heap settings belong to the player's memory control")


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
