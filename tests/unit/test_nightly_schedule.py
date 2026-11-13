import hashlib
import json
import subprocess
import sys
import threading
from datetime import UTC, datetime, timedelta

import pytest

from omk import (
    admin_backups as backups,
    admin_maintenance as maintenance,
    ingress,
    nightly_cycle as cycle,
    nightly_schedule as schedule,
)
from omk.admin import AdminError, _write_private
from omk.cli import main
from tests.unit import test_nightly_cycle, test_owner_maintenance
from tests.unit.test_operator_commands import config

maintenance_flow = test_owner_maintenance.flow
cycle_flow = test_nightly_cycle.flow


@pytest.fixture
def flow(cycle_flow, monkeypatch):
    value = cycle_flow
    value.clock["value"] = datetime(2026, 11, 12, tzinfo=UTC)
    value.env.update(
        OMK_NIGHTLY_SCHEDULE_ENABLED="true",
        OMK_NIGHTLY_TIMEZONE="UTC",
        OMK_NIGHTLY_LOCAL_TIME="00:10",
    )

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return (
                value.clock["value"].astimezone(tz)
                if tz
                else value.clock["value"].replace(tzinfo=None)
            )

    for module in (backups, maintenance, ingress, test_owner_maintenance):
        monkeypatch.setattr(module, "datetime", Clock)
    value.point["finished"] = (value.clock["value"] - timedelta(seconds=60)).isoformat()
    docker = backups.docker
    stop = maintenance.console_stop

    def engine_docker(*a, **kw):
        if a[0] == "start":
            value.clock["value"] += timedelta(milliseconds=1)
        return docker(*a, **kw)

    def engine_stop(*a, **kw):
        stop(*a, **kw)
        value.point["finished"] = value.clock["value"].isoformat()

    monkeypatch.setattr(backups, "docker", engine_docker)
    monkeypatch.setattr(maintenance, "console_stop", engine_stop)
    ready = value.console.ready

    def current_boot(adapter, *, boot=None):
        result = ready(adapter)
        actual = hashlib.sha256(value.state["started"].encode()).hexdigest()[:32]
        if boot is not None and actual != boot:
            raise AdminError("boot changed")
        return {**result, "boot": actual}

    monkeypatch.setattr(value.console, "ready", current_boot)
    return value


def arm(flow):
    result, _wait = schedule.tick(flow.cfg, "dj2", flow.env)
    assert result["phase"] == "armed"
    return schedule.read(flow.cfg, "dj2")


def due(flow, record):
    flow.clock["value"] = schedule.instant(record["window"]["warnings"][0]["at_utc"])


def reach(flow, phase):
    for _ in range(100):
        result, wait = schedule.tick(flow.cfg, "dj2", flow.env)
        if result["phase"] == phase:
            return result
        assert result["ok"], result
        flow.clock["value"] += timedelta(seconds=wait)
    pytest.fail("Calendar phase was not reached")


def counts(flow):
    return {
        action: flow.actions.count(action)
        for action in (
            "close",
            "stop",
            "backup-prepare",
            "backup-publish",
            "start",
            "open",
        )
    }


def test_disabled_is_default_and_does_not_even_create_a_journal(flow):
    before = sorted(p.name for p in flow.cfg.private.iterdir())
    value, wait = schedule.tick(flow.cfg, "dj2", {})
    assert value["phase"] == "disabled" and wait == 0
    assert (
        sorted(p.name for p in flow.cfg.private.iterdir()) == before
        and not flow.actions
    )
    assert schedule.status(flow.cfg, "dj2")["phase"] == "unplanned"


@pytest.mark.parametrize("flag", [True, False, None, "1", "True", "FALSE", "", []])
def test_invalid_enable_flag_refuses_before_any_effect(flow, flag):
    with pytest.raises(AdminError, match="OMK_NIGHTLY_SCHEDULE_ENABLED"):
        schedule.tick(
            flow.cfg, "dj2", {**flow.env, "OMK_NIGHTLY_SCHEDULE_ENABLED": flag}
        )
    assert not flow.actions and not (flow.cfg.private / "nightly-schedule").exists()


def test_one_calendar_cycle_and_date_fence_survive_restart_and_clock_rollback(flow):
    record = arm(flow)
    assert (
        not flow.actions and not cycle.journal(flow.cfg, record["operation"]).exists()
    )
    due(flow, record)
    result = reach(flow, "complete")
    assert counts(flow) == dict.fromkeys(counts(flow), 1)
    root = cycle.read(flow.cfg, record["operation"])
    assert root["schedule"] == schedule.scope(record)
    assert (
        cycle.status(root)["origin"] == "calendar"
        and not cycle.status(root)["manual_countdown"]
    )
    assert (
        result["cycle_stage"] == "complete" and not result["scheduler_running_verified"]
    )
    assert flow.actions.count("warn-5") == flow.actions.count("warn-1") == 1
    before = counts(flow)
    flow.clock["value"] = datetime(2026, 11, 11, tzinfo=UTC)
    next_record = arm(flow)
    assert next_record["operation"] != record["operation"]
    assert next_record["window"]["local_date"] == "2026-11-13"
    assert next_record["previous"]["phase"] == "complete"
    for _ in range(3):
        value, _ = schedule.tick(flow.cfg, "dj2", flow.env)
        assert (
            value["operation"] == next_record["operation"] and value["phase"] == "armed"
        )
    assert counts(flow) == before


@pytest.mark.parametrize("phase", ["armed", "preparing", "active"])
def test_missed_first_notice_never_turns_into_a_late_restart(flow, phase):
    record = arm(flow)
    due(flow, record)
    if phase != "armed":
        reach(flow, phase)
    flow.clock["value"] += timedelta(hours=2)
    result = reach(flow, "skipped")
    assert result["skip_reason"] in {"missed_window", "first_warning_expired"}
    assert not any(counts(flow).values()) and "warn-5" not in flow.actions
    path = cycle.journal(flow.cfg, record["operation"])
    if path.exists():
        assert cycle.read(flow.cfg, record["operation"])["stage"] == "cancelled"
    assert arm(flow)["window"]["local_date"] == "2026-11-13"


@pytest.mark.parametrize(
    "edge", ["reservation", "root", "activation", "notice", "stop", "publication"]
)
def test_interrupted_calendar_reuses_the_reserved_cycle_and_all_child_ids(
    flow, monkeypatch, edge
):
    record = arm(flow)
    due(flow, record)
    if edge in {"reservation", "activation"}:
        original = schedule.save
        stage = "preparing" if edge == "reservation" else "active"

        def lost(config, r, phase):
            original(config, r, phase)
            if phase == stage:
                monkeypatch.setattr(schedule, "save", original)
                raise KeyboardInterrupt

        monkeypatch.setattr(schedule, "save", lost)
    elif edge == "root":
        original = cycle.prepare

        def lost(*a, **kw):
            original(*a, **kw)
            monkeypatch.setattr(cycle, "prepare", original)
            raise KeyboardInterrupt

        monkeypatch.setattr(cycle, "prepare", lost)
    elif edge == "notice":
        original = flow.console.warn

        def lost(*a, **kw):
            original(*a, **kw)
            monkeypatch.setattr(flow.console, "warn", original)
            raise KeyboardInterrupt

        monkeypatch.setattr(flow.console, "warn", lost)
    elif edge == "stop":
        original = maintenance.console_stop

        def lost(*a, **kw):
            original(*a, **kw)
            monkeypatch.setattr(maintenance, "console_stop", original)
            raise KeyboardInterrupt

        monkeypatch.setattr(maintenance, "console_stop", lost)
    else:
        original = backups.worker

        def lost(target, request):
            result = original(target, request)
            if request["action"] == "publish":
                monkeypatch.setattr(backups, "worker", original)
                raise KeyboardInterrupt
            return result

        monkeypatch.setattr(backups, "worker", lost)
    with pytest.raises(KeyboardInterrupt):
        reach(flow, "complete")
    path = cycle.journal(flow.cfg, record["operation"])
    children = (
        cycle.read(flow.cfg, record["operation"])["children"] if path.exists() else None
    )
    result = reach(flow, "complete")
    assert result["operation"] == record["operation"]
    if children:
        assert cycle.read(flow.cfg, record["operation"])["children"] == children
    assert counts(flow) == dict.fromkeys(counts(flow), 1)
    assert flow.actions.count("warn-5") == 1


def test_ordinary_failure_needs_owner_recovery_and_is_not_blindly_retried(
    flow, monkeypatch
):
    record = arm(flow)
    due(flow, record)
    original = backups.worker

    def lost(target, request):
        result = original(target, request)
        if request["action"] == "publish":
            raise OSError("potentially sensitive connection detail")
        return result

    monkeypatch.setattr(backups, "worker", lost)
    for _ in range(100):
        result, wait = schedule.tick(flow.cfg, "dj2", flow.env)
        flow.clock["value"] += timedelta(seconds=wait)
        if not result["ok"]:
            break
    assert (
        result["phase"] == "failed"
        and flow.gate["closed"]
        and not flow.state["running"]
    )
    before = flow.actions.copy()
    assert schedule.tick(flow.cfg, "dj2", flow.env)[0]["phase"] == "failed"
    assert flow.actions == before
    assert "sensitive" not in json.dumps(schedule.status(flow.cfg, "dj2"))
    monkeypatch.setattr(backups, "worker", original)
    cycle.run(flow.cfg, operation=record["operation"], environment=flow.env)
    result, _ = schedule.tick(flow.cfg, "dj2", flow.env)
    assert result["phase"] == "complete" and result["error"] is None
    assert flow.actions.count("stop") == 1


@pytest.mark.parametrize("change", ["budget", "closed"])
def test_preflight_failure_consumes_slot_without_notices_or_lifecycle_effects(
    flow, change
):
    record = arm(flow)
    due(flow, record)
    if change == "budget":
        flow.budget["observed_within_limits"] = False
    else:
        flow.gate["closed"] = True
    reach(flow, "preparing")
    result, _ = schedule.tick(flow.cfg, "dj2", flow.env)
    assert not result["ok"] and result["phase"] == "skipped"
    assert not cycle.journal(flow.cfg, record["operation"]).exists()
    assert not any(counts(flow).values()) and "warn-5" not in flow.actions
    assert arm(flow)["window"]["local_date"] == "2026-11-13"


def test_future_policy_change_replans_but_attempted_policy_change_refuses(flow):
    old = arm(flow)
    flow.env["OMK_NIGHTLY_LOCAL_TIME"] = "00:20"
    new = arm(flow)
    assert new["operation"] != old["operation"] and new["window"][
        "restart_utc"
    ].endswith("00:20:00+00:00")
    assert not flow.actions
    due(flow, new)
    reach(flow, "active")
    flow.env["OMK_BACKUP_MAX_COUNT"] = "3"
    result, _ = schedule.tick(flow.cfg, "dj2", flow.env)
    assert result["phase"] == "failed" and "warn-5" not in flow.actions


def test_two_ingress_slots_are_required_before_any_warning(flow):
    record = arm(flow)
    due(flow, record)
    folder = flow.cfg.private / "ingress"
    folder.mkdir()
    for index in range(cycle.policy(flow.env)[0]["maintenance"]["journal_count"] - 1):
        (folder / (format(index, "032x") + ".json")).write_text("{}")
    result, _ = schedule.tick(flow.cfg, "dj2", flow.env)
    assert not result["ok"] and result["phase"] == "skipped" and not flow.actions


def test_countdown_and_ttl_are_checked_before_any_notice(flow):
    with pytest.raises(AdminError, match="TTL"):
        cycle.prepare(
            flow.cfg,
            "dj2",
            {
                **flow.env,
                "OMK_NIGHTLY_WARNINGS_SECONDS": "60,1",
                "OMK_MAINTENANCE_PLAN_TTL_SECONDS": "60",
            },
        )
    assert not flow.actions


def test_busy_owner_is_waited_without_converting_action_errors_to_busy(flow):
    started, release = threading.Event(), threading.Event()

    def owner():
        with backups.locked(flow.cfg):
            started.set()
            release.wait(5)

    thread = threading.Thread(target=owner)
    thread.start()
    try:
        assert started.wait(2)
        value, wait = schedule.tick(flow.cfg, "dj2", flow.env)
        assert value["phase"] == "busy" and wait == 1 and not flow.actions
    finally:
        release.set()
        thread.join(2)
    assert arm(flow)["phase"] == "armed"


@pytest.mark.parametrize("change", ["schema", "window", "server", "origin", "keys"])
def test_corrupt_calendar_journal_refuses_without_any_effect(flow, change):
    r = arm(flow)
    if change == "schema":
        r["schema"] = True
    elif change == "window":
        r["window"]["local_date"] = "2026-12-01"
    elif change == "server":
        r["server"] = "foreign"
    elif change == "origin":
        r["operation"] = "../escape"
    else:
        r["unexpected"] = True
    _write_private(schedule.journal(flow.cfg, "dj2"), flow.cfg.private, r)
    with pytest.raises(AdminError):
        schedule.tick(flow.cfg, "dj2", flow.env)
    assert not flow.actions


def test_cli_disabled_watch_and_readonly_calendar_status(flow, capsys):
    args = ["admin", "--config", str(flow.cfg.private / "operator.toml"), "nightly"]
    assert main([*args, "watch", "--server", "dj2"]) == 0
    assert json.loads(capsys.readouterr().out)["phase"] == "disabled"
    r = arm(flow)
    before = schedule.journal(flow.cfg, "dj2").read_bytes()
    assert main([*args, "status", "--server", "dj2"]) == 0
    assert json.loads(capsys.readouterr().out)["operation"] == r["operation"]
    assert schedule.journal(flow.cfg, "dj2").read_bytes() == before


def test_calendar_activation_finishes_after_exactly_one_cycle(flow):
    record = arm(flow)
    due(flow, record)
    notices = []

    def notify(value):
        notices.append(value["phase"])
        if value["phase"] == "complete":
            flow.env["OMK_NIGHTLY_SCHEDULE_ENABLED"] = "false"

    result = schedule.watch(flow.cfg, "dj2", flow.env, notify=notify)
    assert result["phase"] == "complete" and notices[-1] == "complete"
    assert counts(flow) == dict.fromkeys(counts(flow), 1)


def test_two_real_processes_share_one_future_reservation(tmp_path):
    cfg, path = config(tmp_path)
    code = (
        "from pathlib import Path;import json,sys;from omk.admin import load_operator_config;"
        "from omk.nightly_schedule import tick\nc=load_operator_config(Path(sys.argv[1]));"
        "print(json.dumps(tick(c,'dj2',{'OMK_NIGHTLY_SCHEDULE_ENABLED':'true'})[0]))"
    )
    children = [
        subprocess.Popen(
            [sys.executable, "-c", code, str(path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for _ in range(2)
    ]
    values = []
    for process in children:
        out, error = process.communicate(timeout=15)
        assert process.returncode == 0, error
        values.append(json.loads(out))
    record = schedule.read(cfg, "dj2")
    assert {v["operation"] for v in values if v["phase"] == "armed"} == {
        record["operation"]
    }
    assert all(v["phase"] in {"armed", "busy"} for v in values)
    assert not cycle.journal(cfg, record["operation"]).exists()


@pytest.mark.parametrize(
    "zone,clock,target",
    [
        ("Europe/Warsaw", "2026-03-28T20:00:00+00:00", "2026-03-30"),
        ("Europe/Warsaw", "2026-10-24T20:00:00+00:00", "2026-10-25"),
    ],
)
def test_calendar_preserves_gap_and_first_fold_policy(flow, zone, clock, target):
    flow.clock["value"] = schedule.instant(clock)
    flow.env.update(OMK_NIGHTLY_TIMEZONE=zone, OMK_NIGHTLY_LOCAL_TIME="02:30")
    r = arm(flow)
    assert r["window"]["local_date"] == target
    if "10-25" in target:
        assert r["window"]["restart_utc"] == "2026-10-25T00:30:00+00:00"


def test_second_fold_does_not_retry_a_failed_first_occurrence(flow):
    flow.clock["value"] = schedule.instant("2026-10-24T20:00:00+00:00")
    flow.env.update(
        OMK_NIGHTLY_TIMEZONE="Europe/Warsaw", OMK_NIGHTLY_LOCAL_TIME="02:30"
    )
    r = arm(flow)
    due(flow, r)
    flow.budget["observed_within_limits"] = False
    reach(flow, "preparing")
    assert not schedule.tick(flow.cfg, "dj2", flow.env)[0]["ok"]
    flow.clock["value"] = schedule.instant("2026-10-25T01:00:00+00:00")
    future = arm(flow)
    assert future["window"]["local_date"] == "2026-10-26"
    assert not any(counts(flow).values())


def test_foreign_preexisting_cycle_is_never_adopted_or_overwritten(flow):
    r = arm(flow)
    cycle.prepare(flow.cfg, "dj2", flow.env, _operation=r["operation"])
    path = cycle.journal(flow.cfg, r["operation"])
    before = path.read_bytes()
    value, _ = schedule.tick(flow.cfg, "dj2", flow.env)
    assert value["phase"] == "failed" and path.read_bytes() == before
    assert not any(counts(flow).values()) and "warn-5" not in flow.actions


@pytest.mark.parametrize("operation", ["", "../escape", True, "a" * 31])
def test_internal_preallocation_validates_identity_before_preflight(flow, operation):
    with pytest.raises(AdminError):
        cycle.prepare(flow.cfg, "dj2", flow.env, _operation=operation)
    assert not flow.actions


def test_disabling_an_active_watch_does_not_change_the_saved_cycle(flow):
    r = arm(flow)
    due(flow, r)
    reach(flow, "active")
    before = cycle.journal(flow.cfg, r["operation"]).read_bytes()
    snapshot = schedule.journal(flow.cfg, "dj2").read_bytes()
    flow.env["OMK_NIGHTLY_SCHEDULE_ENABLED"] = "false"
    assert schedule.tick(flow.cfg, "dj2", flow.env)[0]["phase"] == "disabled"
    assert cycle.journal(flow.cfg, r["operation"]).read_bytes() == before
    assert schedule.journal(flow.cfg, "dj2").read_bytes() == snapshot


def test_policy_change_after_completion_keeps_the_previous_date_fence(flow):
    r = arm(flow)
    due(flow, r)
    reach(flow, "complete")
    before = counts(flow)
    flow.env.update(
        OMK_NIGHTLY_LOCAL_TIME="23:50", OMK_NIGHTLY_TIMEZONE="Europe/Moscow"
    )
    future = arm(flow)
    target = schedule.instant(future["window"]["restart_utc"])
    assert target.date().isoformat() > r["window"]["local_date"]
    assert counts(flow) == before


def test_watch_does_not_spam_logs_while_another_owner_holds_lock(flow, monkeypatch):
    monkeypatch.setattr(schedule, "tick", lambda *a: ({"ok": True, "phase": "busy"}, 1))
    notices = []
    result = schedule.run_due(
        flow.cfg, "dj2", flow.env, notify=lambda v: notices.append(v["phase"])
    )
    assert notices == [] and result["phase"] == "busy"


def test_minute_trigger_does_not_wait_for_a_future_daily_window(flow, monkeypatch):
    monkeypatch.setattr(
        cycle, "pause", lambda *_: pytest.fail("Future window must return")
    )
    notices = []
    first = schedule.run_due(flow.cfg, "dj2", flow.env, notify=notices.append)
    second = schedule.run_due(flow.cfg, "dj2", flow.env, notify=notices.append)
    assert first["phase"] == second["phase"] == "armed"
    assert first["operation"] == second["operation"]
    assert counts(flow) == dict.fromkeys(counts(flow), 0)
    assert notices == []


def test_minute_trigger_can_wait_for_warning_then_never_repeat_the_date(flow):
    record = arm(flow)
    due(flow, record)
    flow.clock["value"] -= timedelta(seconds=50)
    result = schedule.run_due(flow.cfg, "dj2", flow.env)
    assert result["phase"] == "complete"
    before = counts(flow)
    later = schedule.run_due(flow.cfg, "dj2", flow.env)
    assert later["phase"] == "armed"
    assert later["window"]["local_date"] > result["window"]["local_date"]
    assert counts(flow) == before == dict.fromkeys(before, 1)


def test_scheduled_cli_is_disabled_by_default_and_rejects_operation(flow, capsys):
    args = [
        "admin",
        "--config",
        str(flow.cfg.private / "operator.toml"),
        "nightly",
        "run",
    ]
    assert main([*args, "--server", "dj2", "--scheduled"]) == 0
    assert json.loads(capsys.readouterr().out)["phase"] == "disabled"
    assert main([*args, "--operation", "a" * 32, "--scheduled"]) == 1
    assert (
        "Scheduled activation requires a server"
        in json.loads(capsys.readouterr().out)["error"]
    )
