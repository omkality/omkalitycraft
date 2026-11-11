"""Private allowlisted staging targets, distinct across owner workflows."""

import json
import os
import re
import tomllib

from omk import admin_backups as backups
from omk.admin import AdminError
from omk.fs import regular
from omk.resource_reset_inventory import validate_dimension

FILES = {"restores.toml", "resource-resets.toml"}


def document(config, filename):
    if filename not in FILES | {"backups.toml"}:
        raise AdminError("Unsupported owner target configuration")
    path = config.private / filename
    if not regular(path, config.private) or (
        os.name != "nt" and path.stat().st_mode & 0o077
    ):
        raise AdminError("Use a private mode-600 .omk-admin/" + filename)
    with path.open("rb") as stream:
        raw = stream.read(65537)
    if len(raw) > 65536:
        raise AdminError("Owner target configuration exceeds limit")
    value = tomllib.loads(raw.decode())
    if (
        set(value) != {"schema", "servers"}
        or type(value["schema"]) is not int
        or value["schema"] != 1
        or not isinstance(value["servers"], dict)
        or not value["servers"]
        or set(value["servers"]) - set(config.servers)
    ):
        raise AdminError("Invalid owner target configuration")
    return value["servers"]


def validate_entry(entry, current):
    keys = {"data_volume", "owner", "label", "image", "release"}
    if current == "resource-resets.toml":
        keys.add("dimension")
    if (
        not isinstance(entry, dict)
        or set(entry) != keys
        or any(not isinstance(entry[k], str) for k in keys - {"dimension"})
    ):
        raise AdminError("Invalid owner staging target")
    if any(
        not backups.RESOURCE.fullmatch(entry[k])
        for k in ("data_volume", "owner", "release")
    ) or (
        not re.fullmatch(r"omkality\.[a-z0-9_.-]{1,64}", entry["label"])
        or not backups.PINS.fullmatch(entry["image"])
    ):
        raise AdminError("Invalid staging resource or image pin")
    if current == "resource-resets.toml":
        try:
            validate_dimension(entry["dimension"])
        except ValueError:
            raise AdminError("Invalid explicitly configured reset dimension") from None


def target_for(config, server, source, filename):
    if filename not in FILES or server not in config.servers:
        raise AdminError("Unsupported owner target or server")
    volumes = set()
    for name in document(config, "backups.toml"):
        item = backups.target_for(config, name)
        volumes.update((item["data_volume"], item["store_volume"]))
    selected = None
    targets = []
    for current in sorted(FILES):
        path = config.private / current
        if current != filename and not path.exists() and not path.is_symlink():
            continue
        for name, entry in document(config, current).items():
            validate_entry(entry, current)
            configured = source if name == server else backups.target_for(config, name)
            if (
                entry["image"] != configured["image"]
                or entry["release"] != configured["release"]
            ):
                raise AdminError(
                    "Staging target must use the current pinned release and image"
                )
            targets.append(entry["data_volume"])
            if current == filename and name == server:
                selected = dict(entry)
    if len(set(targets)) != len(targets) or set(targets) & volumes:
        raise AdminError(
            "Staging volumes must be distinct from all source/store/restore/reset targets"
        )
    if selected is None:
        raise AdminError("Server has no explicit staging target")
    return selected


def destination(target, *, unused=False):
    rows = json.loads(backups.docker("volume", "inspect", target["data_volume"]))
    if (
        len(rows) != 1
        or rows[0]["Name"] != target["data_volume"]
        or (rows[0].get("Labels") or {}).get(target["label"]) != target["owner"]
    ):
        raise AdminError("Staging volume identity is not explicitly owned")
    if backups.docker(
        "ps", "-aq" if unused else "-q", "--filter", "volume=" + target["data_volume"]
    ).strip():
        raise AdminError(
            "Staging volume is referenced by a container/helper"
            if unused
            else "Staging volume is mounted by an active container"
        )
    return {
        "volume": target["data_volume"],
        "created": rows[0]["CreatedAt"],
        "owner": target["owner"],
    }
