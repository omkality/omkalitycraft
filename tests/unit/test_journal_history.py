import copy
import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from omk import (
    admin_backups as backups,
    admin_maintenance as maintenance,
    ingress,
    journal_history as history,
    nightly_cycle as cycle,
    nightly_schedule as schedule,
)
from omk.admin import AdminError, _write_private
from tests.unit import test_nightly_cycle, test_nightly_schedule, test_owner_maintenance

maintenance_flow = test_owner_maintenance.flow
cycle_flow = test_nightly_cycle.flow
schedule_flow = test_nightly_schedule.flow


@pytest.fixture
def flow(cycle_flow, monkeypatch):
    monkeypatch.setattr(
        history.shutil, "disk_usage", lambda _: SimpleNamespace(free=10**12)
    )
    r = cycle.run(cycle_flow.cfg, server="dj2", environment=cycle_flow.env)
    cycle_flow.root = cycle.read(cycle_flow.cfg, r["operation"])
    cycle_flow.env.update(
        OMK_JOURNAL_ARCHIVE_ENABLED="true", OMK_JOURNAL_ARCHIVE_KEEP_CYCLES="1"
    )
    clone(cycle_flow, cycle_flow.root, 1)
    cycle_flow.actions.clear()
    return cycle_flow


def clone(flow, root, offset):
    result = None
    ids = {
        v: hashlib.sha256((v + str(offset)).encode()).hexdigest()[:32]
        for v in [root["operation"], *root["children"].values()]
    }
    for area, r in history.scope(flow.cfg, root):
        raw = json.dumps(r)
        for old, new in ids.items():
            raw = raw.replace(old, new)
        value = json.loads(raw)
        for key in ("created_at", "updated_at"):
            value[key] = (
                datetime.fromisoformat(r[key]) + timedelta(days=offset)
            ).isoformat()
        _write_private(
            history.path(flow.cfg, area, value["operation"]), flow.cfg.private, value
        )
        if area == "nightly":
            result = value
    return result


def originals(flow):
    return {
        history.path(flow.cfg, a, r["operation"]): history.path(
            flow.cfg, a, r["operation"]
        ).read_bytes()
        for a, r in history.scope(flow.cfg, flow.root)
    }


def refuse_effects(flow, monkeypatch):
    def forbidden(*a, **kw):
        pytest.fail("Archived history must not invoke a server or Docker action")

    for module, name in (
        (backups, "docker"),
        (backups, "worker"),
        (maintenance, "current"),
        (maintenance, "worker"),
        (ingress, "current"),
        (ingress, "worker"),
    ):
        monkeypatch.setattr(module, name, forbidden)


def test_disabled_does_not_create_or_move_history(flow):
    before = originals(flow)
    assert history.compact(flow.cfg, "dj2", {}) == {
        "enabled": False,
        "archived_cycles": 0,
    }
    assert not (flow.cfg.private / "journal-history").exists()
    assert all(p.read_bytes() == raw for p, raw in before.items())
    assert not flow.actions


def test_exact_bytes_status_and_links_survive_move_without_replaying(flow, monkeypatch):
    before = originals(flow)
    refuse_effects(flow, monkeypatch)
    result = history.compact(flow.cfg, "dj2", flow.env)
    assert result["archived_cycles"] == 1 and result["files"] == 5
    for p, raw in before.items():
        assert not p.exists()
        header, stored, record = history.archived(flow.cfg, p.parent.name, p.stem)
        assert stored == raw and header["nightly"] == flow.root["operation"]
        assert (
            history.read(flow.cfg, p.parent.name, p.stem) == json.loads(raw) == record
        )
    assert (
        cycle.tick(flow.cfg, flow.root["operation"], flow.env)[0]["stage"] == "complete"
    )
    ids = flow.root["children"]
    assert (
        maintenance.execute(flow.cfg, ids["maintenance"], "status")["backup_operation"]
        == ids["backup"]
    )
    assert ingress.execute(flow.cfg, ids["open"], "status")["stage"] == "confirmed"
    assert history.compact(flow.cfg, "dj2", flow.env)["archived_cycles"] == 0
    assert not flow.actions


@pytest.mark.parametrize(
    "action",
    [
        "run",
        "finish",
        "backup-cancel",
        "stop",
        "start",
        "reconcile",
        "cancel",
        "apply",
        "verify",
        "ingress-cancel",
        "save",
    ],
)
def test_archived_mutation_refuses_before_any_effect(flow, monkeypatch, action):
    history.compact(flow.cfg, "dj2", flow.env)
    refuse_effects(flow, monkeypatch)
    ids = flow.root["children"]
    with pytest.raises(AdminError, match="read-only"):
        if action in {"run", "finish"}:
            backups.run(flow.cfg, ids["backup"], finish=action == "finish")
        elif action == "backup-cancel":
            backups.cancel(flow.cfg, ids["backup"])
        elif action in {"stop", "start", "reconcile", "cancel"}:
            maintenance.execute(flow.cfg, ids["maintenance"], action)
        elif action == "save":
            cycle.save(flow.cfg, copy.deepcopy(flow.root), "created")
        else:
            ingress.execute(
                flow.cfg,
                ids["open"],
                "cancel" if action == "ingress-cancel" else action,
            )


@pytest.mark.parametrize(
    "kind,area",
    [("maintenance", "maintenance"), ("backup", "backups"), ("open", "ingress")],
)
def test_archived_child_id_is_never_available_for_reuse(flow, kind, area):
    history.compact(flow.cfg, "dj2", flow.env)
    with pytest.raises(AdminError, match="identity already exists"):
        backups.planned_id(flow.cfg, area, flow.root["children"][kind])
    with pytest.raises(AdminError, match="identity already exists"):
        cycle.prepare(flow.cfg, "dj2", flow.env, _operation=flow.root["operation"])


@pytest.mark.parametrize("cut", range(1, 6))
def test_lost_publish_ack_keeps_all_originals_and_resumes_same_scope(
    flow, monkeypatch, cut
):
    before = originals(flow)
    real = history.publish
    calls = []

    def interrupted(*a):
        real(*a)
        calls.append(a[2])
        if len(calls) == cut:
            raise OSError("lost ACK after durable publication")

    monkeypatch.setattr(history, "publish", interrupted)
    with pytest.raises(OSError):
        history.compact(flow.cfg, "dj2", flow.env)
    assert all(p.read_bytes() == raw for p, raw in before.items())
    monkeypatch.setattr(history, "publish", real)
    # A changed keep policy must still finish interrupted groups.
    env = {**flow.env, "OMK_JOURNAL_ARCHIVE_KEEP_CYCLES": "100"}
    assert history.compact(flow.cfg, "dj2", env)["archived_cycles"] == 1
    assert all(not p.exists() for p in before)
    assert history.inventory(flow.cfg)["files"] == 5


@pytest.mark.parametrize("cut", range(1, 6))
def test_interrupted_unlink_recovers_without_losing_lookup(flow, monkeypatch, cut):
    before = originals(flow)
    real = Path.unlink
    calls = []

    def interrupted(p, *a, **kw):
        real(p, *a, **kw)
        if p in before:
            calls.append(p)
            if len(calls) == cut:
                raise OSError("owner process lost after unlink")

    monkeypatch.setattr(Path, "unlink", interrupted)
    with pytest.raises(OSError):
        history.compact(flow.cfg, "dj2", flow.env)
    assert calls[-1].parent.name != "nightly" or cut == 5
    for p, raw in before.items():
        assert history.read(flow.cfg, p.parent.name, p.stem) == json.loads(raw)
    monkeypatch.setattr(Path, "unlink", real)
    history.compact(flow.cfg, "dj2", flow.env)
    assert all(not p.exists() for p in before)
    assert history.inventory(flow.cfg)["files"] == 5


def test_partial_unpublished_temp_recovers_even_after_keep_policy_changed(flow):
    area, r = history.scope(flow.cfg, flow.root)[0]
    folder = history.path(flow.cfg, area, r["operation"], archived=True).parent
    folder.mkdir(parents=True, mode=0o700)
    temporary = folder / (".history-" + r["operation"] + "-abcdefgh.tmp")
    temporary.write_bytes(b'{"schem')
    temporary.chmod(0o600)
    env = {**flow.env, "OMK_JOURNAL_ARCHIVE_KEEP_CYCLES": "100"}
    assert history.compact(flow.cfg, "dj2", env)["archived_cycles"] == 1
    assert not temporary.exists() and not flow.actions


def test_conflicting_live_copy_and_damaged_archive_fail_closed(flow):
    before = originals(flow)
    history.compact(flow.cfg, "dj2", flow.env)
    p = next(iter(before))
    p.write_bytes(before[p] + b" ")
    p.chmod(0o600)
    with pytest.raises(AdminError, match="conflicts"):
        history.read(flow.cfg, p.parent.name, p.stem)
    p.unlink()
    old = history.path(flow.cfg, p.parent.name, p.stem, archived=True)
    raw = old.read_bytes()
    old.write_bytes(raw[:-1] + b"X")
    with pytest.raises(AdminError, match="damaged"):
        history.read(flow.cfg, p.parent.name, p.stem)


@pytest.mark.parametrize(
    "kind,field",
    [
        ("maintenance", "backup_operation"),
        ("maintenance", "binding"),
        ("backup", "checkpoint"),
        ("backup", "settings"),
        ("open", "deployment"),
        ("close", "wanted"),
    ],
)
def test_wrong_completed_cross_reference_never_moves_a_file(flow, kind, field):
    area = {"maintenance": "maintenance", "backup": "backups"}.get(kind, "ingress")
    p = history.path(flow.cfg, area, flow.root["children"][kind])
    r = json.loads(p.read_bytes())
    r[field] = "wrong"
    _write_private(p, flow.cfg.private, r)
    before = originals_without_validation(flow)
    with pytest.raises(AdminError):
        history.compact(flow.cfg, "dj2", flow.env)
    assert history.inventory(flow.cfg)["files"] == 0
    assert all(p.read_bytes() == raw for p, raw in before.items())


def originals_without_validation(flow):
    return {
        p: p.read_bytes()
        for area in history.AREAS
        for p in (flow.cfg.private / area).glob("*.json")
    }


def test_full_history_does_not_evict_and_refuses_before_next_warning(flow, monkeypatch):
    clone(flow, flow.root, 2)
    env = {**flow.env, "OMK_JOURNAL_ARCHIVE_MAX_FILES": "5"}
    refuse_effects(flow, monkeypatch)
    with pytest.raises(AdminError, match="history is full"):
        cycle.prepare(flow.cfg, "dj2", env)
    assert history.inventory(flow.cfg)["files"] == 5
    assert cycle.read(flow.cfg, flow.root["operation"]) == flow.root
    assert not flow.actions


@pytest.mark.parametrize("low", ["bytes", "reserve"])
def test_no_publication_or_cleanup_when_budget_is_insufficient(flow, monkeypatch, low):
    before = originals(flow)
    env = flow.env.copy()
    if low == "bytes":
        env["OMK_JOURNAL_ARCHIVE_MAX_BYTES"] = "1"
    else:
        monkeypatch.setattr(
            history.shutil,
            "disk_usage",
            lambda _: SimpleNamespace(free=history.policy(env)["reserve_bytes"]),
        )
    with pytest.raises(AdminError):
        history.compact(flow.cfg, "dj2", env)
    assert history.inventory(flow.cfg)["files"] == 0
    assert all(p.read_bytes() == raw for p, raw in before.items())


def test_nonterminal_and_cancelled_roots_are_never_archived(flow):
    for stage in ("warnings", "cancelled"):
        r = copy.deepcopy(flow.root)
        r["stage"] = stage
        _write_private(cycle.journal(flow.cfg, r["operation"]), flow.cfg.private, r)
        before = originals_without_validation(flow)
        assert history.compact(flow.cfg, "dj2", flow.env)["archived_cycles"] == 0
        assert all(p.read_bytes() == raw for p, raw in before.items())


def test_batch_limit_makes_progress_and_keeps_the_newest_scope(flow):
    latest = clone(flow, flow.root, 2)
    env = {**flow.env, "OMK_JOURNAL_ARCHIVE_BATCH_CYCLES": "1"}
    assert history.compact(flow.cfg, "dj2", env)["archived_cycles"] == 1
    assert history.compact(flow.cfg, "dj2", env)["archived_cycles"] == 1
    assert history.compact(flow.cfg, "dj2", env)["archived_cycles"] == 0
    assert history.inventory(flow.cfg)["files"] == 10
    assert cycle.journal(flow.cfg, latest["operation"]).exists()


def test_preflight_reclaims_completed_slots_before_a_new_countdown(flow):
    for offset in (2, 3, 4):
        clone(flow, flow.root, offset)
    env = {
        **flow.env,
        "OMK_MAINTENANCE_JOURNAL_COUNT": "8",
        "OMK_BACKUP_JOURNAL_COUNT": "8",
    }
    result = cycle.prepare(flow.cfg, "dj2", env)
    assert result["stage"] == "created"
    assert history.inventory(flow.cfg)["files"] == 20
    assert len(list((flow.cfg.private / "ingress").glob("*.json"))) == 2
    assert not any(
        a.startswith("warn") or a in {"stop", "start", "close", "open"}
        for a in flow.actions
    )


def test_another_servers_scope_is_not_moved(flow):
    foreign = clone(flow, flow.root, 2)
    flow.cfg.servers["gtnh"] = flow.cfg.servers["dj2"]
    before = {}
    for area, r in history.scope(flow.cfg, foreign):
        r["server"] = "gtnh"
        p = history.path(flow.cfg, area, r["operation"])
        _write_private(p, flow.cfg.private, r)
        before[p] = p.read_bytes()
    assert history.compact(flow.cfg, "dj2", flow.env)["archived_cycles"] == 1
    assert all(p.read_bytes() == raw for p, raw in before.items())


@pytest.mark.parametrize("field", ["area", "operation", "nightly", "sha256"])
def test_damaged_archive_receipt_refuses_lookup(flow, field):
    history.compact(flow.cfg, "dj2", flow.env)
    op = flow.root["children"]["maintenance"]
    p = history.path(flow.cfg, "maintenance", op, archived=True)
    head, payload = p.read_bytes().split(b"\n", 1)
    header = json.loads(head)
    header[field] = "a" * (64 if field == "sha256" else 32)
    p.write_bytes(json.dumps(header).encode() + b"\n" + payload)
    with pytest.raises(AdminError):
        maintenance.read_record(flow.cfg, op)


@pytest.mark.parametrize(
    "key,value",
    [
        ("ENABLED", "yes"),
        ("ENABLED", True),
        ("KEEP_CYCLES", "0"),
        ("KEEP_CYCLES", "101"),
        ("BATCH_CYCLES", "0"),
        ("MAX_FILES", "4"),
        ("MAX_FILES", "20001"),
        ("MAX_BYTES", "0"),
        ("MAX_BYTES", "-1"),
        ("MAX_BYTES", "１０"),
    ],
)
def test_invalid_archive_policy_refuses(key, value):
    with pytest.raises(AdminError):
        history.policy({"OMK_JOURNAL_ARCHIVE_" + key: value})


def test_calendar_adopts_complete_root_from_history_after_lost_final_ack(
    schedule_flow, monkeypatch
):
    f = schedule_flow
    monkeypatch.setattr(
        history.shutil, "disk_usage", lambda _: SimpleNamespace(free=10**12)
    )
    reservation = test_nightly_schedule.arm(f)
    test_nightly_schedule.due(f, reservation)
    test_nightly_schedule.reach(f, "complete")
    f.root = cycle.read(f.cfg, reservation["operation"])
    clone(f, f.root, 1)
    cursor = schedule.read(f.cfg, "dj2")
    schedule.save(f.cfg, cursor, "active")
    env = {
        **f.env,
        "OMK_JOURNAL_ARCHIVE_ENABLED": "true",
        "OMK_JOURNAL_ARCHIVE_KEEP_CYCLES": "1",
    }
    assert history.compact(f.cfg, "dj2", env)["archived_cycles"] == 1
    before = f.actions.copy()
    result, _ = schedule.tick(f.cfg, "dj2", env)
    assert result["phase"] == "complete" and result["cycle_stage"] == "complete"
    assert f.actions == before
    result, _ = schedule.tick(f.cfg, "dj2", env)
    assert (
        result["phase"] == "armed"
        and result["previous"]["operation"] == f.root["operation"]
    )
