"""Opt-in calendar driver of existing owner cycles; never installs a host job."""

import contextlib
import json
import os
import re
from datetime import UTC, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from omk import (
    admin_backups as backups,
    journal_history,
    nightly_cycle as cycle,
    nightly_policy,
)
from omk.admin import AdminError, _private_path, _read_json, _write_private
from omk.backup_store import _sync_directory

TERMINAL = {"complete", "cancelled", "skipped"}
PHASES = TERMINAL | {"armed", "preparing", "active", "failed"}
SKIP_REASONS = {None, "missed_window", "first_warning_expired", "preflight_refused"}
KEYS = {
    "schema",
    "server",
    "operator_root",
    "phase",
    "operation",
    "settings",
    "window",
    "created_at",
    "updated_at",
    "fence",
    "previous",
    "error",
    "skip_reason",
}


def enabled(environment=None):
    env = os.environ if environment is None else environment
    value = env.get("OMK_NIGHTLY_SCHEDULE_ENABLED", "false")
    if not isinstance(value, str) or value not in {"true", "false"}:
        raise AdminError("OMK_NIGHTLY_SCHEDULE_ENABLED must be true or false")
    return value == "true"


def instant(value):
    result = datetime.fromisoformat(value)
    if result.utcoffset() is None:
        raise ValueError("Calendar timestamp requires an offset")
    return result.astimezone(UTC)


def journal(config, server):
    if not isinstance(server, str) or server not in config.servers:
        raise AdminError("Calendar server is not in the owner allowlist")
    return _private_path(config.private, "nightly-schedule/" + server + ".json")


def scope(r):
    return {
        "reserved_at": r["created_at"],
        "window_sha256": backups.digest(r["window"]),
    }


def fence(r):
    return {
        "timezone": r["settings"]["calendar"]["timezone"],
        "local_date": r["window"]["local_date"],
        "restart_utc": r["window"]["restart_utc"],
    }


def save(config, r, phase):
    r.update(phase=phase, updated_at=cycle.now().isoformat())
    if len(json.dumps(r).encode()) > 65536:
        raise AdminError("Calendar journal exceeds limit")
    path = journal(config, r["server"])
    _write_private(path, config.private, r)
    _sync_directory(path.parent)


def validate_error(value):
    if value is not None and (
        set(value) != {"type", "phase"}
        or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", value["type"])
        or value["phase"] not in PHASES
    ):
        raise ValueError("Invalid calendar error summary")


def read(config, server):
    r = _read_json(journal(config, server), config.private)
    try:
        if (
            set(r) != KEYS
            or type(r["schema"]) is not int
            or r["schema"] != 1
            or r["server"] != server
            or r["phase"] not in PHASES
            or not isinstance(r["operation"], str)
            or not re.fullmatch(r"[a-f0-9]{32}", r["operation"])
            or not isinstance(r["operator_root"], str)
            or r["skip_reason"] not in SKIP_REASONS
        ):
            raise ValueError
        first = instant(r["window"]["warnings"][0]["at_utc"])
        if nightly_policy.next_window(r["settings"]["calendar"], first) != r["window"]:
            raise ValueError
        instant(r["created_at"])
        instant(r["updated_at"])
        if r["fence"] is not None:
            f = r["fence"]
            if set(f) != {"timezone", "local_date", "restart_utc"}:
                raise ValueError
            # Reuse the validated timezone grammar, not an arbitrary resource name.
            nightly_policy.settings({"OMK_NIGHTLY_TIMEZONE": f["timezone"]})
            if (
                instant(f["restart_utc"])
                .astimezone(ZoneInfo(f["timezone"]))
                .date()
                .isoformat()
                != f["local_date"]
            ):
                raise ValueError
        if r["phase"] != "armed" and r["fence"] != fence(r):
            raise ValueError
        validate_error(r["error"])
        if r["previous"] is not None and (
            set(r["previous"])
            != {"phase", "operation", "restart_utc", "error", "skip_reason"}
            or r["previous"]["phase"] not in TERMINAL
        ):
            raise ValueError
        if r["previous"] is not None:
            p = r["previous"]
            if (
                not re.fullmatch(r"[a-f0-9]{32}", p["operation"])
                or p["skip_reason"] not in SKIP_REASONS
            ):
                raise ValueError
            instant(p["restart_utc"])
            validate_error(p["error"])
    except KeyError, TypeError, ValueError, IndexError, AdminError:
        raise AdminError("Invalid private nightly calendar journal") from None
    return r


def choose(settings, clock, previous=None):
    anchor = (
        max(clock, instant(previous["restart_utc"]) + timedelta(microseconds=1))
        if previous
        else clock
    )
    for _ in range(4):
        window = nightly_policy.next_window(settings["calendar"], anchor)
        target = instant(window["restart_utc"])
        if previous is None or (
            target > instant(previous["restart_utc"])
            and target.astimezone(ZoneInfo(previous["timezone"])).date().isoformat()
            > previous["local_date"]
        ):
            return window
        anchor = instant(window["warnings"][0]["at_utc"]) + timedelta(microseconds=1)
    raise AdminError("No calendar window beyond the recorded date fence")


def arm(config, server, settings, old=None):
    previous = None
    if old is not None:
        previous = (
            old["previous"]
            if old["phase"] == "armed"
            else {k: old[k] for k in ("phase", "operation", "error", "skip_reason")}
            | {"restart_utc": old["window"]["restart_utc"]}
        )
    r = {
        "schema": 1,
        "server": server,
        "operator_root": str(config.servers[server]),
        "phase": "armed",
        "operation": uuid4().hex,
        "settings": settings,
        "window": choose(settings, cycle.now(), old["fence"] if old else None),
        "created_at": cycle.now().isoformat(),
        "updated_at": "",
        "fence": old["fence"] if old else None,
        "previous": previous,
        "error": None,
        "skip_reason": None,
    }
    if journal_history.present(config, "nightly", r["operation"]):
        raise AdminError("Calendar cycle identity collision")
    save(config, r, "armed")
    return r


def child(config, r):
    value = cycle.read(config, r["operation"])
    if (
        value.get("schedule") != scope(r)
        or value["server"] != r["server"]
        or value["operator_root"] != r["operator_root"]
        or value["settings"] != r["settings"]
        or instant(value["created_at"]) < instant(r["created_at"])
    ):
        raise AdminError("Calendar child differs from its durable reservation")
    return value


def status(config, server):
    if not journal(config, server).exists():
        return {
            "ok": True,
            "server": server,
            "phase": "unplanned",
            "scheduler_running_verified": False,
        }
    return view(config, read(config, server))


def view(config, r):
    exists = journal_history.present(config, "nightly", r["operation"])
    try:
        value = child(config, r) if exists and r["phase"] != "armed" else None
    except AdminError:
        if r["phase"] != "failed":
            raise
        value = None
    return {
        "ok": r["phase"] != "failed" and r["error"] is None,
        "server": r["server"],
        "phase": r["phase"],
        "operation": r["operation"],
        "window": r["window"],
        "previous": r["previous"],
        "error": r["error"],
        "skip_reason": r["skip_reason"],
        "cycle_stage": value["stage"] if value else None,
        "scheduler_running_verified": False,
        "ready_for_players": False,
    }


def waiting(config, r, settings, env):
    if journal_history.present(config, "nightly", r["operation"]):
        raise AdminError("Unexpected child before calendar preparation")
    if (
        settings != r["settings"]
        or str(config.servers[r["server"]]) != r["operator_root"]
    ):
        return arm(config, r["server"], settings, r), 0
    late = (cycle.now() - instant(r["window"]["warnings"][0]["at_utc"])).total_seconds()
    if late < 0:
        return r, -late
    r["fence"] = fence(r)
    if late > settings["warning_grace_seconds"]:
        r["skip_reason"] = "missed_window"
        save(config, r, "skipped")
    else:
        cycle.capacity(config, settings, server=r["server"], environment=env)
        save(config, r, "preparing")
    return r, 0


def attempted(config, r, settings, env):
    exists = journal_history.present(config, "nightly", r["operation"])
    value = child(config, r) if exists else None
    if value and value["stage"] in cycle.TERMINAL:
        r["error"] = None
        save(config, r, value["stage"])
        return r, 0
    if r["phase"] == "failed":
        return r, 0
    if (
        settings != r["settings"]
        or str(config.servers[r["server"]]) != r["operator_root"]
    ):
        raise AdminError("Calendar configuration changed during its attempted cycle")
    if r["phase"] == "preparing":
        # prepare is read-only until its atomic root journal. A lost acknowledgement
        # adopts that exact child, never allocates a second set of lifecycle IDs.
        if value is None:
            if (
                cycle.now() - instant(r["window"]["warnings"][0]["at_utc"])
            ).total_seconds() > settings["warning_grace_seconds"]:
                r["skip_reason"] = "missed_window"
                save(config, r, "skipped")
                return r, 0
            cycle.prepare(
                config, r["server"], env, _operation=r["operation"], _schedule=scope(r)
            )
            child(config, r)
        save(config, r, "active")
        return r, 0
    if value is None:
        raise AdminError("Attempted calendar child is missing; never recreate it")
    if (
        not value["warned"]
        and value["stage"] in {"created", "warnings", "warning-requested"}
        and (
            cycle.now() - instant(r["window"]["warnings"][0]["at_utc"])
        ).total_seconds()
        > settings["warning_grace_seconds"]
    ):
        cycle.cancel(config, value["operation"], env)
        r["skip_reason"] = "first_warning_expired"
        save(config, r, "skipped")
        return r, 0
    result, wait = cycle.tick(config, r["operation"], env)
    if result["stage"] in cycle.TERMINAL:
        save(config, r, result["stage"])
    return r, wait


def advance(config, r, settings, env):
    if r["phase"] in TERMINAL:
        return arm(config, r["server"], settings, r), 0
    if r["phase"] == "armed":
        return waiting(config, r, settings, env)
    return attempted(config, r, settings, env)


def tick(config, server, environment=None):
    journal(config, server)
    if not enabled(environment):
        return {
            "ok": True,
            "server": server,
            "phase": "disabled",
            "scheduler_enabled": False,
        }, 0
    settings, env = cycle.policy(environment)
    with contextlib.ExitStack() as locks:
        try:
            locks.enter_context(backups.locked(config))
        except backups.OwnerBusy:
            return {"ok": True, "server": server, "phase": "busy"}, 1
        if not journal(config, server).exists():
            return view(config, arm(config, server, settings)), 0
        r = read(config, server)
        try:
            r, wait = advance(config, r, settings, env)
        except Exception as error:
            name = type(error).__name__
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", name):
                name = "OperationError"
            r["error"] = {"type": name, "phase": r["phase"]}
            r["fence"] = fence(r)
            r["skip_reason"] = (
                "preflight_refused"
                if not journal_history.present(config, "nightly", r["operation"])
                else None
            )
            save(config, r, "skipped" if r["skip_reason"] else "failed")
            wait = 0
        return view(config, r), wait


def run_due(config, server, environment=None, *, notify=None):
    """One bounded calendar activation for a host timer, never wait for tomorrow.

    A minute timer can activate this before the first warning. Existing durable
    date/operation fences still own duplicate suppression and crash recovery.
    """
    last = None
    operation = None
    while True:
        value, wait = tick(config, server, environment)
        if value["phase"] in {"busy", "disabled"}:
            return value
        early = 0
        if value["phase"] == "armed":
            early = (
                instant(value["window"]["warnings"][0]["at_utc"]) - cycle.now()
            ).total_seconds()
            if early > 60:
                return value  # No per-minute full-state logging while idle.
        key = backups.digest(value)
        if key != last and notify is not None:
            notify(value)
        last = key
        if not value["ok"] or value["phase"] in TERMINAL | {"disabled", "failed"}:
            return value
        if operation is not None and value["operation"] != operation:
            return value  # Rearming must not start a second date in one process.
        operation = value["operation"]
        if value["phase"] == "armed":
            wait = max(wait, early)
        cycle.pause(min(wait, 1) if wait > 0 else 0.1)


def watch(config, server, environment=None, *, notify=None):
    """Compatibility entry point; now finishes after one timer activation."""
    return run_due(config, server, environment, notify=notify)
