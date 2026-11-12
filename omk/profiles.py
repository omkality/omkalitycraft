"""Data profiles keep modpack specifics outside the launcher interface."""

import re
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class HardwareTier:
    cpu: str
    ram_gb: int
    graphics: str
    storage_gb: int


@dataclass(frozen=True)
class SystemRequirements:
    """Editorial client guidance, separate from launch permission and heap policy."""

    state: str
    scope: str
    minimum_note: str
    platforms: str
    macos: str
    note: str
    minimum: HardwareTier | None = None
    recommended: HardwareTier | None = None


def _requirements(value: object) -> SystemRequirements | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("Invalid system requirements")
    data = dict(value)
    for name in ("minimum", "recommended"):
        tier = data.get(name)
        if tier is None:
            continue
        if not isinstance(tier, dict):
            raise ValueError("Invalid hardware tier")
        try:
            tier = HardwareTier(**tier)
        except TypeError as error:
            raise ValueError("Invalid hardware tier") from error
        if (
            not all(
                isinstance(text, str) and 0 < len(text) <= 240
                for text in (tier.cpu, tier.graphics)
            )
            or type(tier.ram_gb) is not int
            or not 1 <= tier.ram_gb <= 1024
            or type(tier.storage_gb) is not int
            or not 1 <= tier.storage_gb <= 10000
        ):
            raise ValueError("Invalid hardware tier")
        data[name] = tier
    try:
        requirements = SystemRequirements(**data)
    except TypeError as error:
        raise ValueError("Invalid system requirements") from error
    if (
        not isinstance(requirements.state, str)
        or requirements.state not in {"preliminary", "pending"}
        or not all(
            isinstance(text, str) and 0 < len(text) <= 1000
            for text in (
                requirements.scope,
                requirements.minimum_note,
                requirements.platforms,
                requirements.macos,
                requirements.note,
            )
        )
        or (
            requirements.state == "pending"
            and (
                requirements.minimum is not None or requirements.recommended is not None
            )
        )
        or (
            requirements.minimum is not None
            and requirements.recommended is not None
            and (
                requirements.minimum.ram_gb > requirements.recommended.ram_gb
                or requirements.minimum.storage_gb > requirements.recommended.storage_gb
            )
        )
    ):
        raise ValueError("Invalid system requirements")
    return requirements


@dataclass(frozen=True)
class ServerProfile:
    id: str
    name: str
    minecraft: str
    pack_version: str
    loader: str
    utilities_adapter: str
    status: str
    description: str = ""
    project_url: str = ""
    version_url: str = ""
    author: str = ""
    translation_label: str = ""
    translation_url: str = ""
    artwork: str = ""
    forge_version: str = ""
    memory_default_mb: int = 6144
    memory_recommended_mb: int = 6144
    memory_max_mb: int = 16384
    requirements: SystemRequirements | None = None

    def as_dict(self) -> dict:
        return asdict(self)


def load_profiles(path: Path | None = None) -> list[ServerProfile]:
    path = path if path is not None else PROJECT_ROOT / "profiles" / "servers.toml"
    with path.open("rb") as file:
        document = tomllib.load(file)
    if document.get("schema_version") != 1:
        raise ValueError("Unsupported server profile schema")
    profiles = [
        ServerProfile(
            **{**entry, "requirements": _requirements(entry.get("requirements"))}
        )
        for entry in document["servers"]
    ]
    ids: set[str] = set()
    for profile in profiles:
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,47}", profile.id):
            raise ValueError("Invalid server profile id")
        if profile.id in ids:
            raise ValueError("Duplicate server profile id")
        if profile.loader != "forge":
            raise ValueError("Only Forge profiles are configured at this stage")
        if profile.status not in {"legacy", "planned", "testing", "ready"}:
            raise ValueError("Invalid server profile status")
        if (
            not all(
                type(value) is int
                for value in [
                    profile.memory_default_mb,
                    profile.memory_recommended_mb,
                    profile.memory_max_mb,
                ]
            )
            or not 1024
            <= profile.memory_default_mb
            <= profile.memory_recommended_mb
            <= profile.memory_max_mb
            <= 16384
        ):
            raise ValueError("Invalid memory policy")
        if profile.utilities_adapter not in {
            "ftbutilities_112",
            "serverutilities_1710",
        }:
            raise ValueError("Unknown utilities adapter")
        ids.add(profile.id)
    return profiles
