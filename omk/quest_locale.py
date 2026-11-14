"""Review quest text using pinned bytes; never write a quest database or item NBT."""

import hashlib
import json
import re

from omk.locale_overlay import parse_lang, render_lang

MAX_DATABASE_BYTES = 8 * 1024**2
RUNES = re.compile(r"[\u16a0-\u16ff]+")
HINTS = re.compile(r"§4([A-Za-z0-9])§r")


def render_initial_key_defaults(source: bytes, review: dict) -> bytes:
    """Add a pinned localized key-description alias to DefaultOptions' template only."""
    try:
        if len(source) > 64 * 1024 or _sha(source) != review["source_sha256"]:
            raise ValueError("Initial key template source changed")
        text = source.decode("utf-8")
        lines = text.splitlines()
        required = review["required_lines"]
        added = review["addition"]
        if (
            not isinstance(required, list)
            or not 1 <= len(required) <= 8
            or any(lines.count(line) != 1 for line in required)
            or not isinstance(added, str)
            or re.fullmatch(r"key_[^:\r\n\0]{1,256}:0:NONE", added) is None
            or any(line.startswith(added.split(":", 1)[0] + ":") for line in lines)
            or "\0" in text
        ):
            raise ValueError("Unsafe or repeated initial key alias")
        result = (
            source + (b"" if source.endswith(b"\n") else b"\n") + added.encode() + b"\n"
        )
        if _sha(result) != review["result_sha256"]:
            raise ValueError("Initial key template result changed")
        return result
    except (KeyError, TypeError, UnicodeError) as error:
        raise ValueError("Invalid initial key template review") from error


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate quest database field")
        result[key] = value
    return result


def _database(raw):
    if not isinstance(raw, bytes) or len(raw) > MAX_DATABASE_BYTES:
        raise ValueError("Invalid quest database bytes")
    try:
        data = json.loads(raw, object_pairs_hook=_object)
        if not isinstance(data, dict) or data["format:8"] != "2.0.0":
            raise ValueError("Unknown quest database format")
        for field in ("questDatabase:9", "questLines:9"):
            if not isinstance(data[field], dict) or not data[field]:
                raise ValueError("Missing quest records")
    except (KeyError, TypeError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("Invalid quest database") from error
    return data


def audit_quest_references(database: bytes, english: bytes, russian: bytes) -> dict:
    """Check every title/description, independently of a count of locale keys."""
    data = _database(database)
    en, ru = parse_lang(english), parse_lang(russian)
    keys = []
    try:
        for field, id_field, kind in (
            ("questDatabase:9", "questID:3", "db"),
            ("questLines:9", "lineID:3", "ql"),
        ):
            seen = set()
            for record in data[field].values():
                index = record[id_field]
                if type(index) is not int or index < 0 or index in seen:
                    raise ValueError("Invalid or repeated quest identifier")
                seen.add(index)
                props = record["properties:10"]["betterquesting:10"]
                for source_field, suffix in (("name:8", "title"), ("desc:8", "desc")):
                    key = f"dj2.quest.{kind}.{index}.{suffix}"
                    if props[source_field] != key or key not in en or key not in ru:
                        raise ValueError(
                            "Unresolved or unexpected quest text reference"
                        )
                    if en[key].strip() and not ru[key].strip():
                        raise ValueError("Nonempty quest text became empty")
                    keys.append(key)
    except (KeyError, TypeError) as error:
        raise ValueError("Invalid quest text record") from error
    if len(keys) != len(set(keys)):
        raise ValueError("Repeated quest language reference")
    return {
        "quests": len(data["questDatabase:9"]),
        "chapters": len(data["questLines:9"]),
        "references": len(keys),
        "empty_source_values": sum(not en[key].strip() for key in keys),
        "database_sha256": _sha(database),
    }


def render_quest_locale(
    database: bytes, english: bytes, russian: bytes, profile: dict
) -> bytes:
    """Translate prose and BQ's literal task-name keys without changing gameplay."""
    try:
        if (
            type(profile["schema"]) is not int
            or profile["schema"] != 1
            or profile["pack"] != "DJ2 2.23.4"
        ):
            raise ValueError("Unknown quest review")
        for raw, field in (
            (database, "source_database_sha256"),
            (english, "source_english_sha256"),
            (russian, "previous_russian_sha256"),
        ):
            if _sha(raw) != profile[field]:
                raise ValueError("Quest review source changed")
        audit = audit_quest_references(database, english, russian)
        if any(audit[field] != profile[field] for field in ("quests", "chapters")):
            raise ValueError("Quest review record counts changed")
        updates = profile["updates"]
        labels = profile["literal_task_labels"]
        if (
            not isinstance(updates, list)
            or not 1 <= len(updates) <= 256
            or not isinstance(labels, list)
            or len(labels) > 128
        ):
            raise ValueError("Invalid quest review size")
        en, ru = parse_lang(english), parse_lang(russian)
        changed, guards = {}, {}
        for entry in updates:
            key, text = entry["key"], entry["ru"]
            if (
                re.fullmatch(r"dj2\.quest\.(?:db|ql)\.\d+\.(?:title|desc)", key) is None
                or key in changed
                or _sha(en[key].encode()) != entry["english_sha256"]
                or _sha(ru[key].encode()) != entry["previous_sha256"]
                or RUNES.findall(en[key]) != RUNES.findall(text)
                or HINTS.findall(en[key]) != HINTS.findall(text)
            ):
                raise ValueError("Quest text or puzzle contract changed")
            changed[key], guards[key] = text, entry["english_sha256"]
        db = _database(database)
        records = {q["questID:3"]: q for q in db["questDatabase:9"].values()}
        additions, synthetic = {}, []
        visited = set()
        for label in labels:
            address = (label["quest"], label["task"])
            if address in visited:
                raise ValueError("Repeated task label review")
            visited.add(address)
            task = records[label["quest"]]["tasks:9"][label["task"]]
            name = task["name:8"]
            if (
                task["taskID:8"] != "bq_standard:location"
                or not isinstance(name, str)
                or not name
                or any(c in name for c in "=\r\n\0%")
                or name != name.strip()
                or len(name) > 256
                or name in en
                or name in ru
                or name in additions
                or _sha(name.encode()) != label["source_sha256"]
            ):
                raise ValueError("Unsafe or changed literal task label")
            additions[name] = label["ru"]
            synthetic.append(f"{name}={name}\n")
            guards[name] = label["source_sha256"]
        extended = english.rstrip(b"\r\n") + b"\n" + "".join(synthetic).encode()
        result = render_lang(
            russian,
            extended,
            updates=changed,
            additions=additions,
            expected_source_sha256=guards,
        )
        audit_quest_references(database, english, result)
        return result
    except (KeyError, TypeError, AttributeError) as error:
        raise ValueError("Invalid quest review contract") from error
