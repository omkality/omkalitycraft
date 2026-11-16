"""Compose reviewed resource path changes in memory, before release signing."""

import hashlib
import json
import re
from collections.abc import Collection, Mapping
from dataclasses import dataclass

from launcher.releases import safe_path

_ROOT = "resources/contenttweaker/models/item/"
_TEXTURES = "resources/contenttweaker/textures/items/"
_SCRIPTS = {
    "scripts/ContentTweaker/ContentTweakerItems.zs",
    "scripts/Unique/ContentTweakerBag.zs",
}
_REGISTRATIONS = "scripts/ContentTweaker/ContentTweakerItems.zs"
_ITEM = re.compile(r"contenttweaker:puzzle_tile_[bgkor]{5}")
_CREATED = re.compile(r'VanillaFactory\.createItem\("(puzzle_tile_[bgkor]{5})"\)')
_MAX_FILE = 2 * 1024**2
_MAX_TOTAL = 8 * 1024**2


@dataclass(frozen=True)
class ResourceModelOverlay:
    files: dict[str, bytes]
    removed: tuple[str, ...]
    items: tuple[str, ...]


def _pinned(resources, row):
    if not isinstance(row, dict) or set(row) != {"path", "size", "sha256"}:
        raise ValueError("Invalid resource descriptor")
    name, size, digest = row["path"], row["size"], row["sha256"]
    if not isinstance(name, str):
        raise ValueError("Invalid resource path")
    raw = resources.get(name)
    if (
        type(size) is not int
        or not 0 < size <= _MAX_FILE
        or not isinstance(digest, str)
        or re.fullmatch("[0-9a-f]{64}", digest) is None
        or not isinstance(raw, bytes)
        or len(raw) != size
        or hashlib.sha256(raw).hexdigest() != digest
    ):
        raise ValueError("Resource bytes differ from the reviewed generation")
    return raw


def _review_inventory(review, inventory):
    if (
        set(review)
        != {
            "schema",
            "pack",
            "version",
            "upstream_commit",
            "scripts",
            "models",
            "preserved_models",
        }
        or type(review["schema"]) is not int
        or review["schema"] != 1
        or review["pack"] != "dj2"
        or review["version"] != "2.23.4"
        or not isinstance(review["upstream_commit"], str)
        or re.fullmatch("[0-9a-f]{40}", review["upstream_commit"]) is None
    ):
        raise ValueError("Unsupported resource model review")
    if not 1 <= len(inventory) <= 65536 or any(
        not isinstance(n, str) for n in inventory
    ):
        raise ValueError("Invalid release inventory")
    names = set(inventory)
    if len(names) != len(inventory) or len({n.casefold() for n in names}) != len(names):
        raise ValueError("Release inventory has ambiguous paths")
    for name in names:
        safe_path(name)
    models, preserved, scripts = (
        review["models"],
        review["preserved_models"],
        review["scripts"],
    )
    if (
        not isinstance(models, list)
        or not 1 <= len(models) <= 64
        or not isinstance(preserved, list)
        or len(preserved) > 64
        or not isinstance(scripts, list)
        or len(scripts) != 2
        or any(not isinstance(r, dict) for r in scripts)
        or {r.get("path") for r in scripts} != _SCRIPTS
    ):
        raise ValueError("Invalid reviewed model or script inventory")
    return names


def compose_resource_models(
    *, resources: Mapping, inventory: Collection[str], review: Mapping
) -> ResourceModelOverlay:
    """Return exact replacement paths; never read or modify an installation."""
    names = _review_inventory(review, inventory)
    required = set()

    def pinned(row):
        raw = _pinned(resources, row)
        name = row["path"]
        if name not in names or name in required:
            raise ValueError("Missing or repeated reviewed resource")
        required.add(name)
        return raw

    for row in review["scripts"]:
        pinned(row)
    registered = _CREATED.findall(resources[_REGISTRATIONS].decode("utf-8"))
    expected = {"contenttweaker:" + item for item in registered}
    if len(expected) != len(registered):
        raise ValueError("Duplicate puzzle item registration")
    output, removed, items = {}, [], set()
    for row in review["models"]:
        if not isinstance(row, dict) or set(row) != {
            "item",
            "source",
            "target",
            "texture",
        }:
            raise ValueError("Invalid reviewed model mapping")
        item = row["item"]
        if not isinstance(item, str) or _ITEM.fullmatch(item) is None or item in items:
            raise ValueError("Invalid or duplicate puzzle item")
        stem = item.split(":", 1)[1]
        raw = pinned(row["source"])
        pinned(row["texture"])
        source = row["source"]["path"]
        target = _ROOT + stem + ".json"
        if (
            row["target"] != target
            or source == target
            or not source.startswith(_ROOT)
            or source.lower() != target
            or target in names
            or target in output
            or row["texture"]["path"] != _TEXTURES + stem + ".png"
        ):
            raise ValueError("Model path change is outside the reviewed item")
        model = json.loads(raw)
        if model != {
            "parent": "item/generated",
            "textures": {"layer0": "contenttweaker:items/" + source[len(_ROOT) : -5]},
        }:
            raise ValueError("Reviewed model parent or texture reference changed")
        output[target] = raw
        removed.append(source)
        items.add(item)
    if items != expected:
        raise ValueError("Model mappings do not match registered puzzle items")
    for row in review["preserved_models"]:
        pinned(row)
        name = row["path"]
        if (
            not name.startswith(_ROOT)
            or not name.endswith(".json")
            or "contenttweaker:" + name[len(_ROOT) : -5].lower() in expected
        ):
            raise ValueError("Preserved model is a registered item")
    if (
        required != resources.keys()
        or sum(len(v) for v in resources.values()) > _MAX_TOTAL
    ):
        raise ValueError("Unexpected resources or resource budget exceeded")
    return ResourceModelOverlay(output, tuple(sorted(removed)), tuple(sorted(items)))
