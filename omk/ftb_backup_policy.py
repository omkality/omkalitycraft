"""Readonly disk-policy proof for the reviewed, pinned FTB Backups artifact."""

import hashlib
import re
import stat
from pathlib import Path

from omk.cold_backup_worker import runtime_digest

ADAPTER = "ftb-backups-1.1.0.1-disabled-v1"
JAR = "FTBBackups-1.1.0.1.jar"
SHA256 = "6b6bcbbf6ac4528657345e1696339528a44643ecb06e6137908eafb8432bd962"
KEYS = {
    "D:backup_timer",
    "I:backups_to_keep",
    "I:buffer_size",
    "I:compression_level",
    "B:disable_level_saving",
    "B:display_file_size",
    "B:enabled",
    "S:extra_files",
    "S:folder",
    "B:force_on_shutdown",
    "S:max_total_size",
    "B:only_if_players_online",
    "B:silent",
}


def _property(line):
    if line == "S:extra_files <":
        return "S:extra_files", "list", "list"
    match = re.fullmatch(r"([BDIS]:[a-z_]+)=(.*)", line)
    if not match:
        raise ValueError("Unsupported FTB property syntax")
    return *match.groups(), "general"


def _properties(text):
    values, state = {}, "before"
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if state == "before" and line == "general {":
            state = "general"
        elif state == "list":
            if line == ">":
                state = "general"
            elif any(char in line for char in "{}<>"):
                raise ValueError("Unsupported FTB list syntax")
        elif state == "general" and line == "}":
            state = "after"
        elif state == "general":
            key, value, state = _property(line)
            if key not in KEYS or key in values:
                raise ValueError("Unknown or duplicate FTB property")
            values[key] = value
        else:
            raise ValueError("Unsupported FTB configuration structure")
    if state != "after":
        raise ValueError("Incomplete FTB configuration")
    return values


def disabled_config(text):
    if (
        not isinstance(text, str)
        or len(text.encode()) > 65536
        or any(ord(c) < 32 and c not in "\t\r\n" for c in text)
    ):
        raise ValueError("Invalid FTB configuration text")
    values = _properties(text)
    if set(values) != KEYS:
        raise ValueError("Incomplete FTB configuration")
    if values["B:enabled"] != "false" or values["B:force_on_shutdown"] != "false":
        raise ValueError(
            "Disable both FTB enabled and force_on_shutdown before nightly operation"
        )


def ordinary(path, *, directory=False, limit=None):
    info = path.lstat()
    if (
        path.is_symlink()
        or path.is_junction()
        or not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))
        or (not directory and info.st_nlink != 1)
        or (limit is not None and info.st_size > limit)
    ):
        raise ValueError("Invalid nightly runtime entry")
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def inspect(root=Path("/server")):
    root = Path(root)
    for folder in (root, root / "mods", root / "config"):
        ordinary(folder, directory=True)
    jar, config = root / "mods" / JAR, root / "config/ftbbackups.cfg"
    initial = [ordinary(jar, limit=1024**2), ordinary(config, limit=65536)]
    # Folder-wide runtime digest freezes other mods/configs without returning them.
    before = runtime_digest(root)
    with jar.open("rb") as stream:
        sha = hashlib.file_digest(stream, "sha256").hexdigest()
    if sha != SHA256:
        raise ValueError("Unreviewed FTB Backups artifact")
    with config.open("rb") as stream:
        text = stream.read(65537)
    disabled_config(text.decode("utf-8"))
    if runtime_digest(root) != before or initial != [
        ordinary(jar, limit=1024**2),
        ordinary(config, limit=65536),
    ]:
        raise ValueError("Runtime changed during nightly policy inspection")
    return {
        "adapter": ADAPTER,
        "artifact_sha256": sha,
        "config_sha256": hashlib.sha256(text).hexdigest(),
        "runtime_sha256": before,
        "stock_enabled_on_disk": False,
        "stock_shutdown_on_disk": False,
        "live_config_verified": False,
        "other_writers_verified": False,
    }
