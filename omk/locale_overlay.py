"""Bounded, data-only Minecraft .lang review; never edits quests or scripts."""

import hashlib
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


def _check_source_guards(source, changed, guards):
    if guards is None:
        return
    if not isinstance(guards, dict) or guards.keys() != changed.keys():
        raise ValueError("Invalid translation source guards")
    for key, expected in guards.items():
        if (
            key not in source
            or not isinstance(expected, str)
            or re.fullmatch(r"[a-f0-9]{64}", expected) is None
            or hashlib.sha256(source[key].encode("utf-8")).hexdigest() != expected
        ):
            raise ValueError("Translation source changed or guard is invalid")


def _reviewed_text(value):
    if (
        not isinstance(value, str)
        or any(c in value for c in "\r\n\0")
        or len(value.encode("utf-8")) > MAX_LANG_BYTES
    ):
        raise ValueError("Invalid reviewed locale text")
    return value


def _reviewed_edit(value, edit):
    if not isinstance(edit, dict):
        raise ValueError("Invalid reviewed locale edit")
    if edit.get("kind") == "replace" and edit.keys() == {"kind", "old", "new"}:
        old, new = _reviewed_text(edit["old"]), _reviewed_text(edit["new"])
        if not old or value.count(old) != 1:
            raise ValueError("Ambiguous reviewed locale replacement")
        return value.replace(old, new, 1)
    if edit.get("kind") == "truncate_before" and edit.keys() == {"kind", "marker"}:
        marker = _reviewed_text(edit["marker"])
        if not marker or value.count(marker) != 1:
            raise ValueError("Ambiguous reviewed locale boundary")
        return value.partition(marker)[0]
    raise ValueError("Invalid reviewed locale edit")


def edit_reviewed_value(value: str, *, expected_previous_sha256: str, edits) -> str:
    """Apply bounded literal edits to one pinned RU value; no regex or file writes."""
    _reviewed_text(value)
    if (
        not isinstance(expected_previous_sha256, str)
        or re.fullmatch(r"[a-f0-9]{64}", expected_previous_sha256) is None
        or hashlib.sha256(value.encode("utf-8")).hexdigest() != expected_previous_sha256
    ):
        raise ValueError("The previous locale value changed or its guard is invalid")
    if not value or not isinstance(edits, (list, tuple)) or not 1 <= len(edits) <= 8:
        raise ValueError("Invalid reviewed locale edit count")
    for edit in edits:
        value = _reviewed_text(_reviewed_edit(value, edit))
        if not value:
            raise ValueError("Reviewed locale edits removed the entire value")
    return value


def render_lang(
    base: bytes,
    english: bytes,
    *,
    updates=None,
    additions=None,
    removals=(),
    expected_source_sha256=None,
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
    changed = {**updates, **additions}
    _check_source_guards(source, changed, expected_source_sha256)
    for key, value in changed.items():
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
