import json

import pytest

from omk import (
    resource_reset_runtime as runtime,
    world_cutover_worker as cutover,
)
from tests.unit.test_resource_reset_inventory import (
    records as records,  # noqa: PLC0414 -- pytest fixture export
    sample as sample,  # noqa: PLC0414 -- pytest fixture export
)
from tests.unit.test_resource_reset_runtime import prepared as prepared_runtime
from tests.unit.test_resource_reset_stage import data as data  # noqa: PLC0414


@pytest.fixture
def prepared(data):
    return prepared_runtime.__wrapped__(data)


@pytest.fixture
def exchange(prepared, monkeypatch):
    request, source, storage, target = prepared
    runtime.execute({**request, "action": "runtime-stage"}, source, storage, target)
    request = {
        "schema": 1,
        "action": "plan",
        "operation": "e" * 32,
        "runtime": {**request, "action": "runtime-verify"},
        "expected": None,
        "write_lease": None,
    }
    control = source.parent / "control"
    control.mkdir()
    value = {
        "schema": 1,
        "operation": request["operation"],
        "stage": "planned",
        "write_lease": None,
    }
    (control / "lease.json").write_text(json.dumps(value))
    monkeypatch.setattr(cutover, "CONTROL", control)
    expected = cutover.execute(request, source, storage, target)
    value.update(stage="applying", write_lease="f" * 32)
    (control / "lease.json").write_text(json.dumps(value))
    return (
        {**request, "expected": expected, "write_lease": "f" * 32},
        source,
        storage,
        target,
    )


def execute(exchange, action):
    request, *paths = exchange
    if action in {"revert", "cancel"}:
        control = cutover.CONTROL / "lease.json"
        value = json.loads(control.read_text())
        value["stage"] = "reverting" if action == "revert" else "cancelling"
        if action == "cancel":
            value["write_lease"] = None
            request = {**request, "write_lease": None}
        control.write_text(json.dumps(value))
    return cutover.execute({**request, "action": action}, *paths)


def test_delayed_mutating_helper_cannot_write_after_owner_cancellation(exchange):
    _request, source, _, _ = exchange
    control = cutover.CONTROL / "lease.json"
    value = json.loads(control.read_text())
    value.update(stage="cancelled", write_lease=None)
    control.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="lease"):
        execute(exchange, "apply")
    assert not (source / cutover.ROOT).exists()


def test_older_attempt_cannot_reuse_a_rotated_lease(exchange):
    _request, source, _, _ = exchange
    control = cutover.CONTROL / "lease.json"
    value = json.loads(control.read_text())
    value["write_lease"] = "a" * 32
    control.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="lease"):
        execute(exchange, "apply")
    assert not (source / cutover.ROOT).exists()


def test_revocation_between_renames_requires_a_fresh_attempt(exchange, monkeypatch):
    request, source, storage, target = exchange
    original = cutover.tree(source, request["runtime"])
    move = cutover.move

    def interrupted(src, dest):
        move(src, dest)
        control = cutover.CONTROL / "lease.json"
        value = json.loads(control.read_text())
        value.update(stage="cancelling", write_lease=None)
        control.write_text(json.dumps(value))

    monkeypatch.setattr(cutover, "move", interrupted)
    with pytest.raises(ValueError, match="lease"):
        execute(exchange, "apply")
    assert not (source / "world").exists()
    assert (
        cutover.tree(
            cutover.paths(source, request["operation"]) / "previous", request["runtime"]
        )
        == original
    )
    monkeypatch.setattr(cutover, "move", move)
    fresh = {**request, "action": "recover", "write_lease": "b" * 32}
    control = cutover.CONTROL / "lease.json"
    value = json.loads(control.read_text())
    value.update(stage="applying", write_lease=fresh["write_lease"])
    control.write_text(json.dumps(value))
    monkeypatch.setattr(
        runtime, "_copy", lambda *a: pytest.fail("recovery recopied the world")
    )
    assert cutover.execute(fresh, source, storage, target)["phase"] == "installed"
    with pytest.raises(ValueError, match="lease"):
        execute(exchange, "apply")


def test_install_keeps_exact_previous_world_and_all_runtime_bytes(exchange):
    request, source, _, target = exchange
    original = cutover.tree(source, request["runtime"])
    candidate = cutover.tree(target, request["runtime"])
    before = runtime.files(source, "world")
    assert not (source / cutover.ROOT).exists()
    result = execute(exchange, "apply")
    assert result["phase"] == "installed" and result["old_world_retained"]
    assert not result["server_started"] and not result["ready_for_players"]
    assert result == execute(exchange, "verify")
    root = cutover.paths(source, request["operation"])
    assert cutover.tree(root / "previous", request["runtime"]) == original
    assert cutover.tree(source, request["runtime"]) == candidate
    assert runtime.files(source, "world") == before
    assert cutover.tree(target, request["runtime"]) == candidate
    with pytest.raises(ValueError, match="already attempted"):
        execute(exchange, "apply")


@pytest.mark.parametrize("leg", [1, 2])
def test_interruption_after_rename_recovers_without_recopy(exchange, monkeypatch, leg):
    original_move = cutover.move
    calls = []

    def interrupted(source, dest):
        original_move(source, dest)
        calls.append((source, dest))
        if len(calls) == leg:
            raise OSError("lost process after a durable rename")

    monkeypatch.setattr(cutover, "move", interrupted)
    with pytest.raises(OSError):
        execute(exchange, "apply")
    assert execute(exchange, "verify")["phase"] == (
        "parked" if leg == 1 else "installed"
    )
    monkeypatch.setattr(cutover, "move", original_move)
    monkeypatch.setattr(
        runtime, "_copy", lambda *a: pytest.fail("Recovery repeated the file copy")
    )
    assert execute(exchange, "recover")["phase"] == "installed"
    assert execute(exchange, "verify")["phase"] == "installed"


@pytest.mark.parametrize("leg", [1, 2])
def test_prestart_revert_can_finish_after_interruption(exchange, monkeypatch, leg):
    request, source, _, _ = exchange
    original = cutover.tree(source, request["runtime"])
    execute(exchange, "apply")
    move = cutover.move
    count = []

    def interrupted(src, dst):
        move(src, dst)
        count.append(1)
        if len(count) == leg:
            raise OSError("interrupted revert")

    monkeypatch.setattr(cutover, "move", interrupted)
    with pytest.raises(OSError):
        execute(exchange, "revert")
    assert execute(exchange, "verify-revert")["phase"] == (
        "reverting" if leg == 1 else "reverted"
    )
    monkeypatch.setattr(cutover, "move", move)
    assert execute(exchange, "revert")["phase"] == "reverted"
    assert cutover.tree(source, request["runtime"]) == original
    root = cutover.paths(source, request["operation"])
    assert (root / "rejected/world/level.dat").is_file()
    with pytest.raises(ValueError, match=r"reverted|lease"):
        execute(exchange, "recover")


def test_partial_copy_cannot_be_repeated_but_original_can_be_retained_and_cancelled(
    exchange, monkeypatch
):
    request, source, _, _ = exchange
    original = cutover.tree(source, request["runtime"])
    copy_file = runtime._copy
    calls = []

    def interrupted(*args):
        copy_file(*args)
        calls.append(1)
        raise OSError("simulated ENOSPC during copy")

    monkeypatch.setattr(runtime, "_copy", interrupted)
    with pytest.raises(OSError):
        execute(exchange, "apply")
    with pytest.raises(ValueError):
        execute(exchange, "verify")
    with pytest.raises(ValueError, match="already attempted"):
        execute(exchange, "apply")
    assert execute(exchange, "cancel")["phase"] == "cancelled"
    assert cutover.tree(source, request["runtime"]) == original and len(calls) == 1
    assert list((cutover.paths(source, request["operation"]) / "next/world").rglob("*"))


@pytest.mark.parametrize(
    "change",
    ["world", "runtime", "candidate", "receipt", "identity", "unknown", "backup"],
)
def test_changed_input_refuses_without_renames(exchange, monkeypatch, change):
    request, source, storage, target = exchange
    if change == "world":
        (source / "world/level.dat").write_bytes(b"changed")
    elif change == "runtime":
        (source / "server.properties").write_bytes(b"changed")
    elif change == "candidate":
        (target / "world/level.dat").write_bytes(b"changed")
    elif change == "receipt":
        (target / runtime.DONE).write_text("{}")
    elif change == "identity":
        request["expected"]["dimension"] = 0
    elif change == "unknown":
        (target / "foreign").write_bytes(b"unknown")
    else:
        (storage / "incoming.zip").write_bytes(b"partial publication")
    monkeypatch.setattr(cutover, "move", lambda *a: pytest.fail("Renamed after drift"))
    with pytest.raises(ValueError):
        execute(exchange, "apply")
    assert not cutover.paths(source, request["operation"]).exists()


def test_changed_installed_world_cannot_be_rolled_back_silently(exchange):
    _, source, _, _ = exchange
    execute(exchange, "apply")
    (source / "world/new-player-progress.dat").write_bytes(
        b"accepted writes must survive"
    )
    with pytest.raises(ValueError, match=r"changed|ambiguous"):
        execute(exchange, "revert")
    assert (
        source / "world/new-player-progress.dat"
    ).read_bytes() == b"accepted writes must survive"


def test_existing_retained_generations_count_towards_staging_budget(
    exchange, monkeypatch
):
    request, source, _, _ = exchange
    monkeypatch.setattr(
        cutover,
        "history_bytes",
        lambda root: request["runtime"]["policy"]["staging_bytes"],
    )
    with pytest.raises(OSError, match="budget"):
        execute(exchange, "apply")
    assert not (source / cutover.ROOT).exists()


def test_rename_does_not_overwrite_existing_destination(tmp_path):
    source, destination = tmp_path / "first", tmp_path / "second"
    source.mkdir()
    destination.mkdir()
    with pytest.raises(ValueError, match="overwrite"):
        cutover.move(source, destination)
    assert source.is_dir() and destination.is_dir()
