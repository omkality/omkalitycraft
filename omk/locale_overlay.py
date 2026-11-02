"""Bounded, data-only Minecraft .lang review; never edits quests or scripts."""

import re
from collections import Counter

MAX_LANG_BYTES = 2 * 1024**2
FORMAT = re.compile(
    r"%(?:%|n|(?:(\d+)\$)?[-#+ 0,(<]*\d*(?:\.\d+)?(t[A-Za-z]|T[A-Za-z]|[A-Za-z]))"
)


def parse_lang(raw: bytes) -> dict[str, str]:
    if len(raw) > MAX_LANG_BYTES or b"\0" in raw:
        raise ValueError("Invalid or oversized language file")
    text = raw.decode("utf-8-sig")
    result = {}
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if "=" not in line:
            raise ValueError("Invalid language entry")
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or len(key) > 256 or key in result:
            raise ValueError("Empty, oversized or duplicate language key")
        result[key] = value
    return result


def format_signature(value: str) -> tuple:
    positional, indexed = [], Counter()
    for match in FORMAT.finditer(value):
        index, kind = match.groups()
        if kind is None:  # Literal percent and book paragraph markers take no argument.
            continue
        token = match.group()
        if index is None:
            positional.append(token)
        else:
            indexed[token] += 1
    return tuple(positional), tuple(sorted(indexed.items()))


def audit_lang(
    english: bytes, russian: bytes, previous_english: bytes | None = None
) -> dict:
    source, locale = parse_lang(english), parse_lang(russian)
    shared = source.keys() & locale.keys()
    result = {
        "source_keys": len(source),
        "locale_keys": len(locale),
        "missing": sorted(source.keys() - locale.keys()),
        "extra": sorted(locale.keys() - source.keys()),
        "format_mismatches": sorted(
            key
            for key in shared
            if format_signature(source[key]) != format_signature(locale[key])
        ),
        "game_tested": False,
    }
    if previous_english is not None:
        previous = parse_lang(previous_english)
        result["changed_source_values"] = sorted(
            key
            for key in previous.keys() & source.keys()
            if previous[key] != source[key]
        )
    return result


def render_lang(
    base: bytes, english: bytes, *, updates=None, additions=None, removals=()
) -> bytes:
    """Preserve unrelated lines; each changed key must match the new English contract."""
    old, source = parse_lang(base), parse_lang(english)
    updates, additions, removals = (
        dict(updates or {}),
        dict(additions or {}),
        set(removals),
    )
    if (
        not updates.keys() <= old.keys()
        or additions.keys() & old.keys()
        or updates.keys() & additions.keys()
        or not removals <= old.keys()
        or removals & (updates.keys() | additions.keys())
    ):
        raise ValueError("Ambiguous or unknown translation change")
    for key, value in {**updates, **additions}.items():
        if (
            key not in source
            or not isinstance(value, str)
            or any(c in value for c in "\r\n\0")
            or format_signature(value) != format_signature(source[key])
        ):
            raise ValueError("Translation does not match the new source contract")
    result = []
    for line in base.decode("utf-8-sig").splitlines(keepends=True):
        output_line = line
        if not line.lstrip().startswith("#") and "=" in line:
            key = line.split("=", 1)[0].strip()
            if key in removals:
                continue
            if key in updates:
                ending = (
                    "\r\n"
                    if line.endswith("\r\n")
                    else "\n" if line.endswith("\n") else ""
                )
                output_line = key + "=" + updates[key] + ending
        result.append(output_line)
    if additions:
        if result and not result[-1].endswith("\n"):
            result.append("\n")
        result.extend(
            key + "=" + value + "\n" for key, value in sorted(additions.items())
        )
    raw = (b"\xef\xbb\xbf" if base.startswith(b"\xef\xbb\xbf") else b"") + "".join(
        result
    ).encode("utf-8")
    parse_lang(
        raw
    )  # Check final size, collisions and syntax before any caller writes it.
    return raw
