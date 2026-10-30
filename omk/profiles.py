"""Data profiles keep modpack specifics outside the launcher interface."""

import re
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


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

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


def load_profiles(path: Path | None = None) -> list[ServerProfile]:
    path = path if path is not None else PROJECT_ROOT / "profiles" / "servers.toml"
    with path.open("rb") as file:
        document = tomllib.load(file)
    if document.get("schema_version") != 1:
        raise ValueError("Unsupported server profile schema")
    profiles = [ServerProfile(**entry) for entry in document["servers"]]
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
        if profile.utilities_adapter not in {
            "ftbutilities_112",
            "serverutilities_1710",
        }:
            raise ValueError("Unknown utilities adapter")
        ids.add(profile.id)
    return profiles
