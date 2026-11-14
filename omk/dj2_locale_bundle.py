"""Verify a reviewed language generation in memory; never install or roll back files."""

import hashlib
import json
import re
from collections.abc import Mapping

from launcher.releases import safe_path

SCRIPT = "scripts/ModSpecific/InitialInventory.zs"
MAX_SCRIPT_BYTES = 256 * 1024
MAX_RESOURCE_BYTES = 8 * 1024**2
MAX_BUNDLE_BYTES = 32 * 1024**2
_LITERAL = re.compile(r'val (dj2\w+) = ("(?:\\.|[^"\\])*");')
_HEAD = "add(<minecraft:written_book>.withTag({pages: ["
_TAIL = '], author: "Atricos", title: dj2introductionbookname, resolved: 1 as byte}));'
_NOTE = (
    "// As such, english is used as the default, and the first page has instructions "
    "to send a command (which can be localized)."
)
_NEW_NOTE = "// OmkalityCraft: literal Russian pages, serialized before installation; no server-side client I18n."


def _digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _pinned(raw, pin, maximum):
    if (
        not isinstance(raw, bytes)
        or len(raw) > maximum
        or not isinstance(pin, str)
        or re.fullmatch(r"[a-f0-9]{64}", pin) is None
        or _digest(raw) != pin
    ):
        raise ValueError("Language bundle bytes do not match the reviewed generation")


def _text(value, limit):
    if not isinstance(value, str) or not value or "\0" in value or len(value) > limit:
        raise ValueError("Invalid reviewed book text")
    return value


def render_initial_book(source: bytes, review: Mapping) -> bytes:
    """Change reviewed literal text only, preserving the pinned shared script."""
    if (
        set(review)
        != {
            "schema",
            "source_sha256",
            "result_sha256",
            "book_title",
            "paper_title",
            "paper_lore",
            "pages",
        }
        or type(review["schema"]) is not int
        or review["schema"] != 1
    ):
        raise ValueError("Unsupported initial book review")
    _pinned(source, review["source_sha256"], MAX_SCRIPT_BYTES)
    title = _text(review["book_title"], 32)
    paper = _text(review["paper_title"], 256)
    lore, pages = review["paper_lore"], review["pages"]
    if not isinstance(lore, list) or len(lore) != 3:
        raise ValueError("Three reviewed paper hints are required")
    if not isinstance(pages, list) or not 1 <= len(pages) <= 50:
        raise ValueError("Invalid reviewed page count")
    for value in [*lore, *pages]:
        _text(value, 32766)
    text = source.decode("utf-8")
    edits = {
        "dj2introductionbookname": title,
        "dj2introductionpapername": paper,
        **{f"dj2introductionpaperdesc{i}": value for i, value in enumerate(lore)},
    }
    counts = dict.fromkeys(edits, 0)

    def literal(match):
        name = match[1]
        if name not in edits:
            return match[0]
        counts[name] += 1
        return "val " + name + " = " + json.dumps(edits[name], ensure_ascii=False) + ";"

    text = _LITERAL.sub(literal, text)
    if any(n != 1 for n in counts.values()) or text.count(_HEAD) != 1:
        raise ValueError("Initial inventory text boundaries changed")
    start = text.index(_HEAD)
    if text.count(_TAIL) != 1 or text.count(_NOTE) != 1:
        raise ValueError("Initial inventory author or source note changed")
    end = text.index(_TAIL, start)
    encoded = [
        json.dumps(
            json.dumps({"text": page}, ensure_ascii=False, separators=(",", ":")),
            ensure_ascii=False,
        )
        for page in pages
    ]
    text = (
        text[:start]
        + _HEAD
        + "\n"
        + "".join("    " + p + ",\n" for p in encoded)
        + text[end:]
    )
    text = re.sub(
        r'^val dj2introductionbookdesc\d+ = "(?:\\.|[^"\\])*";\r?\n',
        "",
        text,
        flags=re.M,
    )
    result = text.replace(_NOTE, _NEW_NOTE).encode("utf-8")
    _pinned(result, review["result_sha256"], MAX_SCRIPT_BYTES)
    return result


def _validate_lock(lock):
    if (
        set(lock)
        != {
            "schema",
            "pack",
            "version",
            "locale_archive_sha256",
            "client",
            "initial_inventory",
            "resources",
            "jvm_args_required",
        }
        or type(lock["schema"]) is not int
        or lock["schema"] != 1
    ):
        raise ValueError("Unsupported language bundle lock")
    if (
        lock["pack"] != "dj2"
        or not isinstance(lock["version"], str)
        or re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", lock["version"]) is None
    ):
        raise ValueError("A reviewed DJ2 version is required")
    if lock["jvm_args_required"] != [
        "-Domkality.books.locale.forge112=true",
        "-Domkality.appearance.forge112=true",
    ]:
        raise ValueError("Language bundle launch contract changed")
    if (
        not isinstance(lock["locale_archive_sha256"], str)
        or re.fullmatch(r"[a-f0-9]{64}", lock["locale_archive_sha256"]) is None
    ):
        raise ValueError("Invalid locale archive identity")


def compose_locale_bundle(
    *,
    resources: Mapping,
    script: bytes,
    client: bytes,
    lock: Mapping,
    book_review: Mapping,
) -> dict[str, bytes]:
    """Return exactly the pinned files; signing, storage and install stay elsewhere."""
    _validate_lock(lock)
    records = lock["resources"]
    if not isinstance(records, list) or not 1 <= len(records) <= 2048:
        raise ValueError("Invalid language bundle inventory")
    result, names, total = {}, set(), 0
    for row in records:
        if not isinstance(row, dict) or set(row) != {"path", "sha256", "size"}:
            raise ValueError("Invalid language resource descriptor")
        name = row["path"]
        safe_path(name)
        if name.casefold() in names or not (
            name.startswith(("resources/", "licenses/"))
            or name
            in {"config/tips.cfg", "groovy/assets/divine_journey_2/lang/ru_ru.lang"}
        ):
            raise ValueError("Language bundle contains an unexpected path")
        names.add(name.casefold())
        raw = resources.get(name)
        _pinned(raw, row["sha256"], MAX_RESOURCE_BYTES)
        if type(row["size"]) is not int or len(raw) != row["size"]:
            raise ValueError("Language resource length changed")
        total += len(raw)
        if total > MAX_BUNDLE_BYTES:
            raise ValueError("Language bundle size limit exceeded")
        result[name] = raw
    if result.keys() != resources.keys():
        raise ValueError("Missing or extra language resources")
    initial = lock["initial_inventory"]
    if initial != {
        "path": SCRIPT,
        "source_sha256": book_review["source_sha256"],
        "result_sha256": book_review["result_sha256"],
    }:
        raise ValueError("Shared client/server script generation differs")
    result[SCRIPT] = render_initial_book(script, book_review)
    mod = lock["client"]
    if not isinstance(mod, dict) or set(mod) != {"version", "path", "sha256", "size"}:
        raise ValueError("Invalid client component descriptor")
    if (
        not isinstance(mod["version"], str)
        or re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", mod["version"]) is None
        or mod["path"] != "mods/OmkalityClient-" + mod["version"] + ".jar"
    ):
        raise ValueError("Client component generation differs")
    _pinned(client, mod["sha256"], MAX_RESOURCE_BYTES)
    if type(mod["size"]) is not int or len(client) != mod["size"]:
        raise ValueError("Client component length changed")
    result[mod["path"]] = client
    return result
