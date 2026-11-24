"""Merge required fonts and compatible server entries into player-owned files."""

import hashlib
import json
from dataclasses import asdict, replace
from pathlib import Path

from launcher.files import atomic_write, local_file
from launcher.nbt import MAX_BYTES, Tag, read_nbt, write_nbt
from launcher.pack.client_policy import ClientDefaults
from launcher.releases import Release, ReleaseError, inside

DJ2_MACOS_OPTIONS = {
    "renderDistance": "6",
    "fancyGraphics": "false",
    "ao": "0",
    "renderClouds": "false",
    "entityShadows": "false",
    "particles": "1",
    "mipmapLevels": "0",
    "useVbo": "true",
    "key_key.inventory": "18:NONE",
    "key_key.chat": "20:NONE",
    # Forge serializes Command on macOS as CONTROL. Leave Cmd+F and Cmd+T to JEI.
    "key_roots.keybinds.spell_library": "24:CONTROL",
    "key_key.open_wireless_terminal.desc": "34:CONTROL",
    "key_key.open_wireless_crafting_terminal.desc": "18:CONTROL",
    "key_key.open_wireless_pattern_terminal.desc": "19:CONTROL",
    "key_key.open_wireless_fluid_terminal.desc": "38:CONTROL",
    "key_key.integrateddynamics.logic_programmer_focus_search": "36:CONTROL",
    "key_key.integrateddynamics.logic_programmer_open_rename": "37:CONTROL",
    "key_key.plustic_fruit_salad.desc": "12:CONTROL",
    "key_key.plustic_mots.desc": "13:CONTROL",
}

# Bindings from the previously shipped DJ2 DefaultOptions profile.
_DJ2_MACOS_LEGACY_SHORTCUTS = {
    "key_roots.keybinds.spell_library": "24:SHIFT",
    "key_key.open_wireless_terminal.desc": "20:SHIFT",
    "key_key.open_wireless_crafting_terminal.desc": "18:SHIFT",
    "key_key.open_wireless_pattern_terminal.desc": "19:SHIFT",
    "key_key.open_wireless_fluid_terminal.desc": "33:SHIFT",
}


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


def _previous_keys(record: Path) -> set[str]:
    if not record.exists():
        return set()
    if record.stat().st_size > 32768:
        raise ValueError("Initial keybinding record too large")
    saved = json.loads(record.read_text(encoding="utf-8"))
    values = saved.get("bindings")
    if (
        saved.get("schema") != 1
        or not isinstance(values, list)
        or len(values) > 64
        or any(not isinstance(v, str) or not 1 <= len(v) <= 160 for v in values)
    ):
        raise ValueError("Invalid initial keybinding record")
    return set(values)


def _macos_shortcut_changes(
    folder: Path, options: dict[str, str]
) -> tuple[dict[str, str], Path | None]:
    record = local_file(folder, ".omk-dj2-macos-shortcuts-v1")
    if record.exists():
        return {}, None
    occupied = {value for key, value in options.items() if key.startswith("key_")}
    changes = {}
    for key, legacy in _DJ2_MACOS_LEGACY_SHORTCUTS.items():
        replacement = DJ2_MACOS_OPTIONS[key]
        if options.get(key) == legacy and replacement not in occupied:
            changes[key] = replacement
    return changes, record


def _options(
    folder: Path, defaults: ClientDefaults, *, platform_options: dict[str, str]
) -> None:
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
    changed.update(
        (key, value) for key, value in defaults.initial_options if key not in options
    )
    key_record = local_file(folder, ".omk-initial-keybindings.json")
    previous_keys = set()
    if defaults.initial_keybindings and path.exists():
        previous_keys = _previous_keys(key_record)
    for binding, code in defaults.initial_keybindings:
        key = "key_" + binding
        if binding not in previous_keys and key not in options:
            changed[key] = str(code)
    changed.update(
        (key, value) for key, value in platform_options.items() if key not in options
    )
    migration_record = None
    if platform_options:
        shortcut_changes, migration_record = _macos_shortcut_changes(folder, options)
        changed.update(shortcut_changes)
    if any(options.get(key) != value for key, value in changed.items()):
        output = [line for line in lines if line.split(":", 1)[0] not in changed]
        output.extend(f"{key}:{value}" for key, value in changed.items())
        _replace(folder, "options.txt", ("\n".join(output) + "\n").encode())
    if defaults.initial_keybindings:
        data = json.dumps(
            {"schema": 1, "bindings": [k for k, _ in defaults.initial_keybindings]},
            ensure_ascii=False,
        ).encode()
        if not key_record.exists() or key_record.read_bytes() != data:
            atomic_write(key_record, data)
    if migration_record is not None:
        atomic_write(migration_record, b"1\n")


def _remember_platform_keys(folder: Path, options: dict[str, str]) -> None:
    # DefaultOptions 9.2.8 resets any binding it has not seen in knownkeys.txt,
    # even when options.txt already contains a value for that binding.
    path = local_file(folder, "knownkeys.txt")
    if path.exists() and path.stat().st_size > MAX_BYTES:
        raise ValueError("Known keys file too large")
    old = path.read_bytes() if path.exists() else b""
    seen = set(old.splitlines())
    bindings = (
        key.removeprefix("key_").encode("ascii")
        for key in options
        if key.startswith("key_")
    )
    additions = [binding for binding in bindings if binding not in seen]
    if additions:
        separator = b"\n" if old and not old.endswith(b"\n") else b""
        _replace(
            folder, "knownkeys.txt", old + separator + b"\n".join(additions) + b"\n"
        )


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
        platform_options = (
            DJ2_MACOS_OPTIONS
            if release.pack_id == "dj2"
            and release.minecraft == "1.12.2"
            and release.platform.startswith("macos-")
            else {}
        )
        if release.pack_id == "dj2":
            # The signed presets still supply the server identity and address.
            defaults = replace(
                defaults,
                servers=tuple(
                    replace(server, name="Divine Journey 2 RU")
                    if server.id == "dj2"
                    else server
                    for server in defaults.servers
                ),
            )
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
            or defaults.initial_keybindings
            or defaults.initial_options
            or platform_options
        ):
            _options(folder, defaults, platform_options=platform_options)
        if platform_options:
            _remember_platform_keys(folder, platform_options)
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
