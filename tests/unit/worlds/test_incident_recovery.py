"""Regression checks for exact Forge save edits and interrupted staging."""

import base64
import hashlib

import pytest

from omk.backups.stopped_world_backup import inventory
from omk.shared.nbt import Tag, read_nbt
from omk.worlds import (
    forge112_regions as anvil,
    incident_players as players,
    incident_recovery as stage,
    owner_restore_worker as worker,
)
from tests.fixtures.unit.worlds.incident_recovery import (
    POSITION,
    incident,
    records,
    sample,
    selection,
    stack,
)

__all__ = ["incident", "records", "sample"]


def evidence_for(request, args, planned):
    reply = worker.execute(
        {**request, "action": "evidence", "expected": planned}, *args
    )
    payload = base64.b64decode(reply["nbt"], validate=True)
    assert len(payload) == planned["quarantine"]["bytes"]
    assert hashlib.sha256(payload).hexdigest() == planned["quarantine"]["sha256"]
    return payload


@pytest.mark.parametrize("kind", ["inventory", "dropped", "chest", "chest-block"])
def test_stage_exact_selection_and_restore_progress(incident, kind):
    request, args, player_path = incident
    _backup, target, source = args
    request["incident"]["quarantine"] = selection(kind, player_path.stem)
    before = inventory(source / "world", world_name="world")
    planned = worker.execute({**request, "action": "plan"}, *args)
    assert not (target / "world").exists()
    payload = evidence_for(request, args, planned)
    applied = {
        **request,
        "action": "apply",
        "expected": planned,
        "evidence_sha256": planned["quarantine"]["sha256"],
    }
    with pytest.raises(ValueError, match="has not been verified"):
        worker.execute({**applied, "evidence_sha256": "0" * 64}, *args)
    receipt = worker.execute(applied, *args)
    assert receipt == worker.execute({**applied, "action": "verify"}, *args)
    assert inventory(source / "world", world_name="world") == before
    assert set(planned["changes"]) == {
        f"world/playerdata/{player_path.name}",
        "world/data/ftb_lib/players/owner.dat",
    } | ({"world/DIM-1/region/r.-1.-1.mca"} if kind != "inventory" else set())
    original = players.document(player_path, source)[1]
    replacement = players.document(
        target / "world/playerdata" / player_path.name, target
    )[1]
    assert players.coordinates(replacement) == [8.5, 100.0, 8.5]
    assert replacement["Dimension"] == Tag(3, 0)
    assert replacement["XpTotal"] == original["XpTotal"]
    assert replacement["ModData"] == original["ModData"]
    slots = anvil.compounds(replacement, "Inventory")
    assert slots == ([stack(2)] if kind == "inventory" else [stack(1), stack(2)])
    evidence = read_nbt(payload)[1]
    region_file = "world/DIM-1/region/r.-1.-1.mca"
    old, new = (
        anvil.Region(root / region_file, root / "world") for root in (source, target)
    )
    index = 26 + 32 * 26
    assert old.record(index + 1) == new.record(index + 1)
    chunk = new.chunk(index)
    assert anvil.block_id(anvil.sections(chunk), -84, 100, -81) == 0x513F
    if kind == "inventory":
        assert evidence == stack(1)
    elif kind == "dropped":
        assert evidence["Item"] == Tag(10, stack(0, "minecraft:iron_ingot"))
        assert anvil.compounds(chunk, "Entities") == []
    elif kind == "chest":
        assert evidence == stack(4)
        tile = anvil.compounds(chunk, "TileEntities")[0]
        assert anvil.compounds(tile, "Items") == [stack(5, "minecraft:apple")]
    else:
        assert anvil.compounds(evidence, "Items") == [
            stack(4),
            stack(5, "minecraft:apple"),
        ]
        assert not anvil.compounds(chunk, "TileEntities")
        assert anvil.block_id(anvil.sections(chunk), *POSITION) == 0
    with pytest.raises(ValueError, match="already attempted"):
        worker.execute(applied, *args)


def test_changed_source_unsafe_landing_and_forged_plan_refuse_before_writes(incident):
    req, args, player = incident
    _, target, source = args
    req["incident"]["rescue"]["landing"] = [8, 103, 8]
    with pytest.raises(ValueError, match="another saved landing"):
        worker.execute({**req, "action": "plan"}, *args)
    req["incident"]["rescue"]["landing"] = [8, 100, 8]
    planned = worker.execute({**req, "action": "plan"}, *args)
    forged = {**planned, "world_inventory_sha256": "0" * 64}
    with pytest.raises(ValueError, match="changed after planning"):
        worker.execute({**req, "action": "apply", "expected": forged}, *args)
    player.write_bytes(b"changed-on-disk")
    with pytest.raises(ValueError, match="differs from its latest"):
        worker.execute({**req, "action": "apply", "expected": planned}, *args)
    assert not (target / stage.PLAN).exists()
    assert not (target / "world").exists()
    assert (source / "world/level.dat").is_file()


def test_failed_world_write_leaves_no_staged_receipt(incident, monkeypatch):
    req, args, player = incident
    _backup, target, source = args
    req["incident"]["quarantine"] = selection("inventory", player.stem)
    planned = worker.execute({**req, "action": "plan"}, *args)
    evidence_for(req, args, planned)
    bound = {
        **req,
        "expected": planned,
        "evidence_sha256": planned["quarantine"]["sha256"],
    }
    unchanged = inventory(source / "world", world_name="world")
    write = stage.raw._write_edit

    def interrupted(root, name, data):
        if root == target:
            raise OSError(28, "No space left on device")
        return write(root, name, data)

    monkeypatch.setattr(stage.raw, "_write_edit", interrupted)
    with pytest.raises(OSError, match="No space"):
        worker.execute({**bound, "action": "apply"}, *args)
    assert (target / stage.PLAN).is_file()
    assert not (target / stage.DONE).exists()
    assert inventory(source / "world", world_name="world") == unchanged
    with pytest.raises(ValueError):
        worker.execute({**bound, "action": "verify"}, *args)
