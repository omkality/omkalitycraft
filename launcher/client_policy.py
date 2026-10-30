"""Small signed client defaults, independent of game-version UI code."""

import json
import re
from dataclasses import dataclass
from urllib.parse import urlsplit


@dataclass(frozen=True)
class DefaultServer:
    id: str
    name: str
    address: str


@dataclass(frozen=True)
class InitialConfig:
    path: str
    content: dict


def _initial_configs(raw: list) -> tuple[InitialConfig, ...]:
    # Explicit adapter allowlist: these are personal JSON settings, never maps,
    # waypoints, executable files or globally managed pack configuration.
    if not isinstance(raw, list) or len(raw) > 8:
        raise ValueError("Invalid initial configs")
    configs = tuple(InitialConfig(**entry) for entry in raw)
    if len({entry.path for entry in configs}) != len(configs):
        raise ValueError("Duplicate initial config")
    for entry in configs:
        if (
            not isinstance(entry.path, str)
            or not re.fullmatch(
                r"journeymap/config/5\.7/journeymap\.(minimap2?|fullmap)\.config",
                entry.path,
            )
            or not isinstance(entry.content, dict)
            or len(entry.content) > 100
            or any(
                not isinstance(key, str)
                or not re.fullmatch(r"[A-Za-z0-9_]{1,64}", key)
                or type(value) not in {str, bool, int}
                for key, value in entry.content.items()
            )
            or len(json.dumps(entry.content).encode()) > 16384
        ):
            raise ValueError("Unsupported initial config")
    return configs


@dataclass(frozen=True)
class ClientDefaults:
    resourcepacks: tuple[str, ...] = ()
    language: str | None = None
    unicode_font: bool | None = None
    servers: tuple[DefaultServer, ...] = ()
    initial_configs: tuple[InitialConfig, ...] = ()

    @classmethod
    def parse(cls, value: dict):
        if not isinstance(value, dict) or set(value) - {
            "required_resourcepacks",
            "language",
            "force_unicode_font",
            "servers",
            "initial_configs",
        }:
            raise ValueError("Invalid client defaults")
        packs = value.get("required_resourcepacks", [])
        if (
            not isinstance(packs, list)
            or len(packs) > 8
            or any(
                not isinstance(name, str)
                or not re.fullmatch(r"[A-Za-z0-9 _.-]{1,100}", name)
                or name in {".", ".."}
                or name.rstrip(". ") != name
                for name in packs
            )
        ):
            raise ValueError("Invalid resource pack names")
        language = value.get("language")
        if language is not None and not re.fullmatch(
            r"[a-z]{2,3}_[a-z]{2,3}", language
        ):
            raise ValueError("Invalid default language")
        unicode_font = value.get("force_unicode_font")
        if unicode_font is not None and type(unicode_font) is not bool:
            raise ValueError("Invalid font setting")
        raw = value.get("servers", [])
        if not isinstance(raw, list) or len(raw) > 8:
            raise ValueError("Too many default servers")
        servers = tuple(DefaultServer(**entry) for entry in raw)
        if len({server.id for server in servers}) != len(servers):
            raise ValueError("Duplicate server ID")
        for server in servers:
            _validate_server(server)
        configs = _initial_configs(value.get("initial_configs", []))
        return cls(tuple(packs), language, unicode_font, servers, configs)


def _validate_server(server: DefaultServer) -> None:
    if (
        not re.fullmatch(r"[a-z0-9_-]{1,48}", server.id)
        or not isinstance(server.name, str)
        or not 1 <= len(server.name) <= 80
        or any(ord(c) < 32 for c in server.name)
    ):
        raise ValueError("Invalid default server")
    if (
        not isinstance(server.address, str)
        or not 1 <= len(server.address) <= 260
        or any(c.isspace() for c in server.address)
    ):
        raise ValueError("Invalid server address")
    target = urlsplit("//" + server.address)
    if (
        not target.hostname
        or target.username
        or target.password
        or target.path
        or target.query
        or target.fragment
        or (target.port is not None and not 1 <= target.port <= 65535)
    ):
        raise ValueError("Invalid server address")
    if not re.fullmatch(r"[A-Za-z0-9_.:-]+", target.hostname):
        raise ValueError("Invalid server hostname")
