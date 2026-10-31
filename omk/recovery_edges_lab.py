"""Characterize native WorldEdit entity/partial-archive behavior in a new lab only."""

import zipfile

from omk.dj2_commands_lab import _response
from omk.recovery_preflight_lab import preflight

TAGS = {
    "original": "omk_recovery_original",
    "outside": "omk_recovery_outside",
    "new": "omk_recovery_new",
}


def entity_count(console, tag):
    return console(f"testfor @e[type=armor_stand,tag={tag}]").count("Found ")


def seed_edges(console, expect):
    for kind, x in [("original", 131.5), ("outside", 137.5)]:
        console(
            f"summon minecraft:armor_stand {x} 241 133.5 "
            f'{{Tags:["{TAGS[kind]}"],NoGravity:1b,Invulnerable:1b}}'
        )
        expect(
            entity_count(console, TAGS[kind]) == 1, "fixture_" + kind + "_entity_exists"
        )
    for x in (143, 144):
        console(f"setblock {x} 241 132 minecraft:gold_block")
        expect(
            "Successfully found"
            in console(f"testforblock {x} 241 132 minecraft:gold_block"),
            f"cross_chunk_fixture_{x}_created",
        )


def damage_edges(console, expect):
    console(f'kill @e[type=armor_stand,tag={TAGS["original"]}]')
    console(
        "summon minecraft:armor_stand 132.5 241 133.5 "
        f'{{Tags:["{TAGS["new"]}"],NoGravity:1b,Invulnerable:1b}}'
    )
    expect(
        entity_count(console, TAGS["original"]) == 0, "original_entity_really_removed"
    )
    expect(entity_count(console, TAGS["new"]) == 1, "post_snapshot_entity_really_added")
    for x in (143, 144):
        console(f"setblock {x} 241 132 minecraft:obsidian")


def characterize_entities(console, expect, report, prefix):
    counts = {key: entity_count(console, tag) for key, tag in TAGS.items()}
    report.setdefault("native_entity_observations", {})[prefix] = counts
    expect(
        counts["original"] == 0,
        prefix + "native_snapshot_does_not_restore_destroyed_armor_stand",
    )
    expect(
        counts["new"] == 1, prefix + "native_snapshot_keeps_post_snapshot_armor_stand"
    )
    expect(counts["outside"] == 1, prefix + "outside_entity_unchanged")


def make_partial_snapshot(source, target):
    # Deliberately remove chunk (9,8) only in a new experimental ZIP, never a world.
    with (
        zipfile.ZipFile(source) as incoming,
        zipfile.ZipFile(target, "x", zipfile.ZIP_DEFLATED) as outgoing,
    ):
        for info in incoming.infolist():
            if info.file_size > 128 * 1024**2:
                raise ValueError("Partial lab fixture exceeds size limit")
            data = incoming.read(info)
            if info.filename == "lab-world/region/r.0.0.mca":
                data = bytearray(data)
                offset = 4 * (9 + 8 * 32)
                if len(data) < 8192 or data[offset : offset + 4] == b"\0" * 4:
                    raise ValueError(
                        "Missing positive-control chunk for partial archive"
                    )
                data[offset : offset + 4] = b"\0" * 4
            outgoing.writestr(info.filename, data)


def check_partial_snapshot(actor, console, snapshots, expect, report):
    source, partial = snapshots / "before-grief.zip", snapshots / "partial.zip"
    bounds = ((143, 241, 132), (144, 241, 132))
    expect(
        preflight(source, *bounds)["chunks"] == 2,
        "complete_cross_chunk_snapshot_passes_preflight",
    )
    make_partial_snapshot(source, partial)
    try:
        preflight(partial, *bounds)
    except ValueError:
        expect(True, "missing_chunk_rejected_before_apply_by_preflight")
    else:
        raise RuntimeError("Incomplete snapshot passed preflight")
    for x in (143, 144):
        expect(
            "Successfully found"
            in console(f"testforblock {x} 241 132 minecraft:obsidian"),
            f"preflight_did_not_modify_live_block_{x}",
        )
    # Intentionally bypass the read-only guard ONLY to measure native behavior in
    # this disposable lab; this is not the administrative recovery workflow.
    _response(actor, "//pos1 143,241,132", "First position set")
    _response(actor, "//pos2 144,241,132", "Second position set")
    _response(actor, "/snap use partial.zip", "Snapshot set")
    _response(actor, "//restore", "Restored; 1 missing chunks and 0 other errors.")
    report["native_partial_restore_response"] = list(actor.messages)
    expect(
        "Successfully found"
        in console("testforblock 143 241 132 minecraft:gold_block"),
        "native_partial_restore_already_modified_available_chunk",
    )
    expect(
        "Successfully found" in console("testforblock 144 241 132 minecraft:obsidian"),
        "native_partial_restore_left_missing_chunk_damaged",
    )
    _response(actor, "//undo", "Undo successful")
    for x in (143, 144):
        expect(
            "Successfully found"
            in console(f"testforblock {x} 241 132 minecraft:obsidian"),
            f"immediate_native_partial_undo_returns_lab_block_{x}",
        )
    report["partial_restore_is_atomic"] = False
    report["preflight_scope"] = {"min": list(bounds[0]), "max": list(bounds[1])}
