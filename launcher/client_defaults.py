"""Merge required fonts and compatible server entries into player-owned files."""

import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from launcher.client_policy import ClientDefaults
from launcher.files import atomic_write, local_file
from launcher.nbt import MAX_BYTES, Tag, read_nbt, write_nbt
from launcher.releases import Release, ReleaseError, inside


def _replace(folder: Path, filename: str, data: bytes) -> None:
    path = local_file(folder, filename)
    old = path.read_bytes() if path.exists() else None
    if old == data:
        return
    if old is not None:
        backup = local_file(
            folder,
            f".omk-defaults-backups/{hashlib.sha256(old).hexdigest()}-{filename}",
        )
        if not backup.exists():
            atomic_write(backup, old)
    atomic_write(path, data)


def _options(folder: Path, defaults: ClientDefaults) -> None:
    path = local_file(folder, "options.txt")
    if path.exists() and path.stat().st_size > MAX_BYTES:
        raise ValueError("Options file too large")
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    options = dict(line.split(":", 1) for line in lines if ":" in line)
    packs = json.loads(options.get("resourcePacks", "[]"))
    if (
        not isinstance(packs, list)
        or len(packs) > 100
        or any(not isinstance(name, str) for name in packs)
    ):
        raise ValueError("Invalid active resource packs")
    changed = {
        "resourcePacks": json.dumps(
            list(dict.fromkeys([*packs, *defaults.resourcepacks])), ensure_ascii=False
        )
    }
    if defaults.language and "lang" not in options:
        changed["lang"] = defaults.language
    if defaults.unicode_font is not None:
        changed["forceUnicodeFont"] = str(defaults.unicode_font).lower()
    if all(options.get(key) == value for key, value in changed.items()):
        return
    output = [line for line in lines if line.split(":", 1)[0] not in changed]
    output.extend(f"{key}:{value}" for key, value in changed.items())
    _replace(folder, "options.txt", ("\n".join(output) + "\n").encode())


def _servers(folder: Path, defaults: ClientDefaults) -> None:
    record = local_file(folder, ".omk-client-defaults.json")
    try:
        if record.exists() and record.stat().st_size > 65536:
            raise ValueError("Defaults record too large")
        previous = (
            json.loads(record.read_text(encoding="utf-8"))["servers"]
            if record.exists()
            else []
        )
    except OSError, ValueError, KeyError:
        previous = []
    if not defaults.servers and not previous:
        return
    path = local_file(folder, "servers.dat")
    if path.exists() and path.stat().st_size > MAX_BYTES:
        raise ValueError("Server list too large")
    name, root = read_nbt(path.read_bytes()) if path.exists() else ("", {})
    old_list = root.get("servers", Tag(9, (10, [])))
    if old_list.kind != 9 or (old_list.value[0] != 10 and old_list.value != (0, [])):
        raise ValueError("Invalid server list")
    entries = old_list.value[1]
    managed = {
        (entry["name"], entry["address"])
        for entry in previous
        if isinstance(entry, dict)
        and isinstance(entry.get("name"), str)
        and isinstance(entry.get("address"), str)
    }
    current = {(server.name, server.address) for server in defaults.servers}
    retained = [
        entry
        for entry in entries
        if (
            entry.value.get("name", Tag(8, "")).value,
            entry.value.get("ip", Tag(8, "")).value,
        )
        not in managed | current
    ]
    by_pair = {
        (
            entry.value.get("name", Tag(8, "")).value,
            entry.value.get("ip", Tag(8, "")).value,
        ): entry
        for entry in entries
    }
    previous_ids = {
        entry.get("id"): (entry.get("name"), entry.get("address"))
        for entry in previous
        if isinstance(entry, dict)
    }
    added = []
    for server in defaults.servers:
        existing = by_pair.get((server.name, server.address)) or by_pair.get(
            previous_ids.get(server.id)
        )
        properties = (
            dict(existing.value)
            if existing is not None
            else {"acceptTextures": Tag(1, 0)}
        )
        properties.update(name=Tag(8, server.name), ip=Tag(8, server.address))
        added.append(Tag(10, properties))
    root["servers"] = Tag(9, (10, [*added, *retained]))
    _replace(folder, "servers.dat", write_nbt(name, root))
    atomic_write(
        record,
        json.dumps(
            {"servers": [asdict(server) for server in defaults.servers]}
        ).encode(),
    )


def prepare_client_defaults(release: Release, folder: Path) -> None:
    raw = release.launch.get("client_defaults")
    if raw is None:
        return
    try:
        defaults = ClientDefaults.parse(raw)
        for name in defaults.resourcepacks:
            path = inside(folder, "resourcepacks/" + name)
            if not (
                path.is_file()
                if name.endswith(".zip")
                else (path / "pack.mcmeta").is_file()
            ):
                raise ValueError("Required font resource pack missing")
        if (
            defaults.resourcepacks
            or defaults.language
            or defaults.unicode_font is not None
        ):
            _options(folder, defaults)
        _servers(folder, defaults)
        for config in defaults.initial_configs:
            path = local_file(folder, config.path)
            if not path.exists():
                atomic_write(
                    path,
                    (
                        json.dumps(config.content, ensure_ascii=False, indent=2) + "\n"
                    ).encode(),
                )
    except OSError, ValueError, TypeError, KeyError, AttributeError:
        raise ReleaseError(
            "Не удалось подготовить настройки игры. Проверьте options.txt, servers.dat "
            "и папку настроек карты; изменённые файлы имеют резервные копии."
        ) from None
