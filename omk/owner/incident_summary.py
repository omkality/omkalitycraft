"""Extract bounded diagnostic hints from a retained client crash report."""

import hashlib
import re
from uuid import UUID

_MAX_DETAIL_CHARS = 32768
_IDENTIFIER = r"[a-zA-Z_$][a-zA-Z0-9_$]*"
_PACKAGE = rf"(?:{_IDENTIFIER}\.)+"
_QUALIFIED_NAME = _PACKAGE + _IDENTIFIER
_FRAME = re.compile(rf"^at ({_PACKAGE}(?:{_IDENTIFIER}|<init>|<clinit>))\(")
_EXCEPTION = re.compile(rf"^({_QUALIFIED_NAME})(?::|$)")
_LOG_PREFIX = re.compile(r"^(?:\[[^\]\r\n]{1,100}\]\s+){1,2}\[[^\]\r\n]{1,100}\]:\s*")
_INT = r"-?[0-9]{1,10}"
_BLOCK = re.compile(rf"^World: \(({_INT}),\s*({_INT}),\s*({_INT})\)(?:,|$)")
_CHUNK = re.compile(rf"({_INT}),\s*({_INT})")
_REGISTRY_ID = re.compile(r"[a-z0-9_.-]+:[a-z0-9_/.-]+")
_ENTITY_UUID = re.compile(
    r"[a-fA-F0-9]{32}|[a-fA-F0-9]{8}(?:-[a-fA-F0-9]{4}){3}-[a-fA-F0-9]{12}"
)
_NATIVE_SIGNAL = re.compile(
    r"^#\s+(SIGSEGV|SIGBUS|SIGILL|SIGFPE|SIGABRT|"
    r"EXCEPTION_ACCESS_VIOLATION|EXCEPTION_ILLEGAL_INSTRUCTION)\b"
)
_NATIVE_FRAME = re.compile(
    r"^#\s+C\s+\[([a-zA-Z0-9_.-]{1,100})\+(0x[0-9a-fA-F]{1,16})\]"
)
_NATIVE_OOM = re.compile(r"^#\s+Out of Memory Error\b")

_DESCRIPTIONS = {
    "Rendering entity in world": "rendering_entity",
    "Rendering Block Entity": "rendering_block_entity",
    "Rendering screen": "rendering_screen",
    "Ticking entity": "ticking_entity",
    "Ticking block entity": "ticking_block_entity",
    "Exception initializing level": "initializing_level",
    "Exception generating new chunk": "generating_chunk",
}
_SUBJECT_SECTIONS = {
    "rendering_entity": "Entity being rendered",
    "rendering_block_entity": "Block Entity Details",
    "ticking_entity": "Entity being ticked",
    "ticking_block_entity": "Block entity being ticked",
}


def _sections(detail):
    header, sections = [], {}
    selected = header
    for raw in detail[:_MAX_DETAIL_CHARS].splitlines():
        line = raw.strip()
        if line.startswith("-- ") and line.endswith(" --"):
            selected = []
            sections.setdefault(line[3:-3], []).append(selected)
        else:
            selected.append(line)
    return header, sections


def _unique_section(sections, name):
    candidates = sections.get(name, [])
    return candidates[0] if len(candidates) == 1 else []


def _field(lines, name):
    prefix = name + ":"
    values = [line[len(prefix) :].strip() for line in lines if line.startswith(prefix)]
    return values[0] if len(values) == 1 else ""


def _integer(value):
    if re.fullmatch(_INT, value):
        numeric = int(value)
        if -(2**31) <= numeric < 2**31:
            return numeric
    return None


def _coordinates(match):
    if match is None:
        return None
    values = [_integer(part) for part in match.groups()]
    return values if None not in values else None


def _subject(sections, category):
    lines = _unique_section(sections, _SUBJECT_SECTIONS.get(category))
    entity = category in {"rendering_entity", "ticking_entity"}
    label = "Entity Type" if entity else "Name"
    registry = _field(lines, label).partition(" ")[0]
    registry = (
        registry if len(registry) <= 200 and _REGISTRY_ID.fullmatch(registry) else None
    )
    label = "Entity's Block location" if entity else "Block location"
    block = _coordinates(_BLOCK.match(_field(lines, label)))
    identifier = _field(lines, "Entity UUID") if entity else ""
    entity_uuid = UUID(identifier).hex if _ENTITY_UUID.fullmatch(identifier) else None
    if registry is None and block is None and entity_uuid is None:
        return None
    return {"registry_id": registry, "block": block, "entity_uuid": entity_uuid}


def _java_stack(lines):
    causes, frames = [], []
    for line in lines:
        normalized = _LOG_PREFIX.sub("", line).removeprefix("Caused by:").strip()
        if (
            len(causes) < 8
            and (match := _EXCEPTION.match(normalized))
            and len(match[1]) <= 200
            and match[1].endswith(("Exception", "Error", "Throwable"))
        ):
            causes.append(match[1])
        if (
            len(frames) < 8
            and (match := _FRAME.match(normalized))
            and len(match[1]) <= 200
        ):
            frames.append(match[1])
    return causes, frames


def _signature(category, fields):
    if not fields:
        return None
    return hashlib.sha256("\n".join([category, *fields]).encode("ascii")).hexdigest()


def _native(lines):
    signal = next(
        (hit[1] for line in lines if (hit := _NATIVE_SIGNAL.match(line))), None
    )
    frame = next((hit for line in lines if (hit := _NATIVE_FRAME.match(line))), None)
    module = frame[1] if frame else None
    offset = hex(int(frame[2], 16)) if frame else None
    category = (
        "native_out_of_memory"
        if any(_NATIVE_OOM.match(line) for line in lines)
        else "native_crash"
    )
    return {
        "category": category,
        "exception": None,
        "stack_signature": _signature(
            category, [signal or "", module.casefold(), offset] if frame else []
        ),
        "signal": signal,
        "native_module": module,
        "native_offset": offset,
        "level_dimension": None,
        "chunk": None,
        "subject": None,
    }


def summarize_incident(report: dict) -> dict:
    """Describe log evidence without copying messages or making a recovery decision."""
    header, sections = _sections(report["detail"])
    if report["kind"] == "jvm_crash":
        return _native(header)
    causes, frames = _java_stack(header)
    exception = causes[-1] if causes else None
    description = (
        _field(header, "Description") if report["kind"] == "minecraft_crash" else ""
    )
    category = _DESCRIPTIONS.get(
        description, "java_exception" if exception else "unknown"
    )
    if "java.lang.OutOfMemoryError" in causes:
        category, exception = "java_out_of_memory", "java.lang.OutOfMemoryError"
    world_context = category in _SUBJECT_SECTIONS or category in {
        "initializing_level",
        "generating_chunk",
    }
    affected = _unique_section(sections, "Affected level") if world_context else []
    chunk = (
        _unique_section(sections, "Chunk to be generated")
        if category == "generating_chunk"
        else []
    )
    return {
        "category": category,
        "exception": exception,
        "stack_signature": _signature(
            category, [exception or "", *frames] if frames else []
        ),
        "signal": None,
        "native_module": None,
        "native_offset": None,
        "level_dimension": _integer(_field(affected, "Level dimension")),
        "chunk": _coordinates(_CHUNK.fullmatch(_field(chunk, "Location"))),
        "subject": _subject(sections, category),
    }
