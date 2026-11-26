import pytest

from omk.owner.incident_summary import summarize_incident
from tests.fixtures.unit.launcher.client_incidents import report

_TILE = """
-- Block entity being ticked --
Details:
    Name: minecraft:furnace // example.Furnace
    Block location: World: (-17,68,4), Chunk: (at 15,4,4 in -2,0)
"""


def test_ticking_block_signature_ignores_source_line_numbers():
    detail = (
        "Description: Ticking block entity\n"
        "java.lang.IllegalStateException: private text\n"
        "    at example.Furnace.<init>(Furnace.java:21)\n" + _TILE
    )
    first = summarize_incident(report(detail=detail))
    second = summarize_incident(report(detail=detail.replace("java:21", "java:322")))
    assert first["category"] == "ticking_block_entity"
    assert first["exception"] == "java.lang.IllegalStateException"
    assert first["subject"] == {
        "registry_id": "minecraft:furnace",
        "block": [-17, 68, 4],
        "entity_uuid": None,
    }
    assert (
        first["stack_signature"]
        and first["stack_signature"] == second["stack_signature"]
    )
    changed_stack = summarize_incident(
        report(detail=detail.replace("Furnace.<init>", "Furnace.tick"))
    )
    assert first["stack_signature"] != changed_stack["stack_signature"]


@pytest.mark.parametrize(
    ("description", "details", "category"),
    [
        ("Rendering screen", _TILE, "rendering_screen"),
        ("Exception generating new chunk", _TILE, "generating_chunk"),
        ("Ticking block entity", _TILE + _TILE, "ticking_block_entity"),
        (
            "Ticking block entity",
            "-- Affected level --\nLevel spawn location: World: (16,60,24)",
            "ticking_block_entity",
        ),
        (
            "Rendering Block Entity",
            " " * 32768
            + _TILE.replace("Block entity being ticked", "Block Entity Details"),
            "rendering_block_entity",
        ),
    ],
    ids=["screen", "chunk-generation", "duplicated-section", "spawn", "oversized"],
)
def test_other_or_ambiguous_sections_do_not_supply_a_subject(
    description, details, category
):
    outcome = summarize_incident(
        report(detail=f"Description: {description}\n" + details)
    )
    assert outcome["category"] == category
    assert outcome["subject"] is None


def test_chunk_generation_uses_chunk_coordinates_in_the_matching_section():
    detail = """Description: Exception generating new chunk
java.lang.IllegalStateException: synthetic
    at example.Generator.generate(Generator.java:15)

-- Chunk to be generated --
Details:
    Location: -12,3

-- Affected level --
Details:
    Level dimension: 7
"""
    outcome = summarize_incident(report(detail=detail))
    assert outcome["category"] == "generating_chunk"
    assert outcome["chunk"] == [-12, 3]
    assert outcome["level_dimension"] == 7
    assert outcome["subject"] is None


@pytest.mark.parametrize(
    ("kind", "detail", "category", "signal", "module"),
    [
        (
            "jvm_crash",
            "# EXCEPTION_ACCESS_VIOLATION (0xc0000005) at pc=0x123\n# C  [OpenAL64.dll+0x00020ddd]\n"
            + _TILE,
            "native_crash",
            "EXCEPTION_ACCESS_VIOLATION",
            "OpenAL64.dll",
        ),
        (
            "jvm_crash",
            "# SIGSEGV (0xb) at pc=0x123\n# V  [libjvm.so+0x00020ddd]\n",
            "native_crash",
            "SIGSEGV",
            "libjvm.so",
        ),
        (
            "jvm_crash",
            "# SIGSEGV (0xb) at pc=0x123\n# v  [libjvm.dylib+0x20ddd]\n",
            "native_crash",
            "SIGSEGV",
            "libjvm.dylib",
        ),
        (
            "jvm_crash",
            "#  Out of Memory Error (allocation.cpp:44)",
            "native_out_of_memory",
            None,
            None,
        ),
        (
            "abnormal_exit",
            "[08:01:01] [Client thread/ERROR]: java.lang.OutOfMemoryError: Java heap space\n"
            + _TILE,
            "java_out_of_memory",
            None,
            None,
        ),
        ("abnormal_exit", "No Java stack trace was available.", "unknown", None, None),
    ],
)
def test_native_and_memory_errors_do_not_supply_recovery_targets(
    kind, detail, category, signal, module
):
    outcome = summarize_incident(report(kind=kind, detail=detail))
    assert outcome["category"] == category
    assert outcome["signal"] == signal
    assert outcome["native_module"] == module
    assert outcome["native_offset"] == ("0x20ddd" if module else None)
    assert outcome["level_dimension"] is None
    assert outcome["subject"] is None
