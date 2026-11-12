"""One explicit backup/restart transaction using existing owner services.

The daily scheduler is deliberately separate. Each short step holds the shared
owner lock; waiting releases it so status/cancel and a second recovery process
can observe the same durable child identities without repeating side effects.
"""

import json
import os
import re
import time
from datetime import UTC, datetime
from uuid import uuid4

from omk import (
    admin_backups as backups,
    admin_maintenance as maintenance,
    admin_nightly,
    admin_storage,
    ingress,
    ingress_template,
    nightly_policy,
    storage_estate,
)
from omk.admin import AdminError, _private_path, _read_json, _write_private
from omk.backup_store import _sync_directory
from omk.maintenance_console import MaintenanceConsole
from omk.storage_policy import storage_plan

TERMINAL = {"complete", "cancelled"}
STAGES = TERMINAL | {
    "created",
    "warnings",
    "warning-requested",
    "closing",
    "stopping",
    "backing-up",
    "starting",
    "opening",
}
KEYS = {
    "schema",
    "operation",
    "server",
    "stage",
    "created_at",
    "updated_at",
    "operator_root",
    "target",
    "binding",
    "settings",
    "initial",
    "disk",
    "loaded",
    "gate",
    "children",
    "deadline",
    "warned",
    "admission",
    "resumed",
}


def now():
    return datetime.now(UTC)


def pause(seconds):
    time.sleep(seconds)


def policy(environment=None):
    env = dict(os.environ if environment is None else environment)
    project = storage_plan(env)
    if not project["ok"]:
        raise AdminError(project["error"])
    # A composed write may strengthen the individual backup's reserve, never
    # weaken the project reserve. The effective value is frozen in both journals.
    reserve = max(
        backups.settings(env)["reserve_bytes"],
        project["budgets_gib"]["reserve"] * 1024**3,
    )
    env["OMK_BACKUP_RESERVE_BYTES"] = str(reserve)
    raw = env.get("OMK_NIGHTLY_WARNING_GRACE_SECONDS", "30")
    if (
        not isinstance(raw, str)
        or not raw.isascii()
        or not raw.isdecimal()
        or len(raw) > 2
        or not 1 <= int(raw) <= 60
    ):
        raise AdminError("Invalid OMK_NIGHTLY_WARNING_GRACE_SECONDS")
    return {
        "calendar": nightly_policy.settings(env),
        "maintenance": maintenance.settings(env),
        "backup": backups.settings(env),
        "project": project,
        "storage_limits": admin_storage.limits(env),
        "ingress": ingress_template.settings(env),
        "warning_grace_seconds": int(raw),
    }, env


def journal(config, operation):
    if not isinstance(operation, str) or not re.fullmatch(r"[a-f0-9]{32}", operation):
        raise AdminError("Invalid nightly operation identity")
    return _private_path(config.private, "nightly/" + operation + ".json")


def save(config, record, stage):
    record.update(stage=stage, updated_at=now().isoformat())
    if len(json.dumps(record).encode()) > 65536:
        raise AdminError("Nightly journal exceeds limit")
    _write_private(journal(config, record["operation"]), config.private, record)
    _sync_directory(journal(config, record["operation"]).parent)


def read(config, operation):
    r = _read_json(journal(config, operation), config.private)
    if (
        set(r) != KEYS
        or type(r.get("schema")) is not int
        or r["schema"] != 1
        or r["operation"] != operation
        or r["server"] not in config.servers
        or r["stage"] not in STAGES
        or not isinstance(r["children"], dict)
        or set(r["children"]) != {"maintenance", "backup", "close", "open"}
        or len({operation, *r["children"].values()}) != 5
        or any(
            not isinstance(v, str) or not re.fullmatch(r"[a-f0-9]{32}", v)
            for v in r["children"].values()
        )
        or not isinstance(r["warned"], list)
        or r["warned"]
        != r["settings"]["calendar"]["warnings_seconds"][: len(r["warned"])]
    ):
        raise AdminError("Invalid nightly journal")
    return r


def status(r):
    return {
        "ok": True,
        "operation": r["operation"],
        "server": r["server"],
        "stage": r["stage"],
        "children": r["children"],
        "deadline": r["deadline"],
        "warnings_confirmed": r["warned"],
        "manual_countdown": True,
        "scheduler_enabled": False,
        "ready_for_players": False,
    }


def console(config, r):
    endpoint, password = maintenance.credential(config, r["server"])
    return MaintenanceConsole(endpoint, password)


def frozen(config, r, environment=None, *, closed=False):
    settings, env = policy(environment)
    if (
        settings != r["settings"]
        or str(config.servers[r["server"]]) != r["operator_root"]
        or (
            backups.target_for(config, r["server"]) != r["target"]
            or maintenance.binding(config, r["server"]) != r["binding"]
            or admin_nightly.adapter(config, r["server"]) != r["disk"]["adapter"]
        )
    ):
        raise AdminError(
            "Nightly configuration or policy changed; inspect before continuing"
        )
    ingress.guard(config, r["server"], r["gate"], closed=closed)
    current = maintenance.snapshot(r["target"], r["binding"])
    if any(
        current[k] != r["initial"][k]
        for k in ("container", "image", "created", "restart_count", "source", "store")
    ):
        raise AdminError("Nightly source identity changed")
    return current, env


def disk(config, r, *, post_start=False):
    proof = maintenance.worker(
        {"operation": r["operation"], "target": r["target"], "binding": r["binding"]},
        "nightly-policy",
    )
    # The existing maintenance start verifies the full stopped runtime before
    # launching Java. Forge then rewrites generated properties/caches and docs.
    # Across that boot, retain exact FTB artifact/config checks; a whole-tree
    # byte comparison is valid before start, not after those normal writes.
    keys = set(r["disk"]) - ({"runtime_sha256"} if post_start else set())
    if set(proof) != set(r["disk"]) or any(proof[k] != r["disk"][k] for k in keys):
        raise AdminError("Nightly runtime or stock backup configuration changed")


def running(config, r, environment=None, *, resumed=False, closed=False):
    current, env = frozen(config, r, environment, closed=closed)
    expected = r["resumed"]["source"] if resumed else r["initial"]
    if current != expected or not current["running"]:
        raise AdminError("Nightly source is not the expected running boot")
    if not resumed:
        disk(config, r)
    boot = r["resumed"]["loaded"]["boot"] if resumed else r["loaded"]["boot"]
    console(config, r).ready(r["disk"]["adapter"], boot=boot)
    return env


def stopped(config, r, environment=None):
    from omk.world_cutover import for_window  # noqa: PLC0415

    current, env = frozen(config, r, environment, closed=True)
    window = maintenance.read_record(config, r["children"]["maintenance"])
    if (
        window["stage"] != "stopped"
        or current != {**r["initial"], "running": False}
        or (
            backups.checkpoint(r["target"]) != window["checkpoint"]
            or for_window(config, window["operation"]) is not None
        )
    ):
        raise AdminError(
            "Nightly requires its unchanged stopped source, without world installation"
        )
    disk(config, r)
    return env


def admission(config, r, env):
    report = storage_estate.inspect(config, env)
    budget = report["budget"]
    if (
        not budget["observed_within_limits"]
        or not budget["declared_operation_limits"]["compatible"]
    ):
        raise AdminError(
            "Nightly project budgets or declared caps do not fit; inspect storage estate"
        )
    sources = [
        e
        for e in report["resources"]
        if e["server"] == r["server"] and e["role"] == "source"
    ]
    if len(sources) != 1 or "active_world" not in sources[0]["categories"]:
        raise AdminError("Nightly world is missing from the project census")
    world = sources[0]["categories"]["active_world"]
    required = (
        max(world["apparent_bytes"], world["allocated_bytes"])
        + 16 * 1024**2
        + world["files"] * 2048
    )
    stage = budget["categories"]["staging"]
    available = budget["filesystems"][0]["available_bytes"]
    reserve = r["settings"]["backup"]["reserve_bytes"]
    if (
        required > r["settings"]["backup"]["staging_bytes"]
        or stage["charged_bytes"] + 2 * required > stage["limit_bytes"]
        or available < 2 * required + reserve
    ):
        raise AdminError("Nightly staging or shared free reserve is insufficient")
    return {
        "at": now().isoformat(),
        "available_bytes": available,
        "required_staging_bytes": 2 * required,
        "reserve_bytes": reserve,
    }


def prepare(config, server, environment=None):
    settings, env = policy(environment)
    with backups.locked(config):
        folder = _private_path(config.private, "nightly")
        if folder.exists():
            rows = list(folder.iterdir())
            if len(rows) >= settings["maintenance"]["journal_count"]:
                raise AdminError("Archive terminal nightly journals before planning")
            for path in rows:
                other = read(config, path.stem)
                if other["server"] == server and other["stage"] not in TERMINAL:
                    raise AdminError("Resume or cancel the existing nightly operation")
        ingress.operations_clear(config, server)
        gate, state = ingress.capture(config, server)
        if state["closed"]:
            raise AdminError(
                "Nightly run requires an already open source; it never opens a deliberately closed service"
            )
        ingress.source_ready(config, server, gate)
        preflight = admin_nightly.inspect(config, server, env)
        target, endpoint = backups.target_for(config, server), maintenance.binding(
            config, server
        )
        initial = maintenance.snapshot(target, endpoint)
        if not initial["running"]:
            raise AdminError("Nightly run requires the running source")
        r = {
            "schema": 1,
            "operation": uuid4().hex,
            "server": server,
            "stage": "created",
            "created_at": now().isoformat(),
            "updated_at": "",
            "operator_root": str(config.servers[server]),
            "target": target,
            "binding": endpoint,
            "settings": settings,
            "initial": initial,
            "disk": preflight["disk_policy"],
            "loaded": None,
            "gate": gate,
            "children": {
                name: uuid4().hex for name in ("maintenance", "backup", "close", "open")
            },
            "deadline": None,
            "warned": [],
            "admission": None,
            "resumed": None,
        }
        r["loaded"] = console(config, r).ready(r["disk"]["adapter"])
        if (
            journal(config, r["operation"]).exists()
            or len({r["operation"], *r["children"].values()}) != 5
        ):
            raise AdminError("Nightly operation identities collide")
        r["admission"] = admission(config, r, env)
        record = {
            "operation": r["children"]["backup"],
            "target": target,
            "settings": settings["backup"],
        }
        backups.worker(target, backups.request_for(record, "inspect"))
        running(config, r, environment)
        save(config, r, "created")
        return status(r)


def tick(config, operation, environment=None):
    from omk.nightly_steps import advance  # noqa: PLC0415

    with backups.locked(config):
        r = read(config, operation)
        if r["stage"] in TERMINAL:
            return status(r), 0
        wait = advance(config, r, environment)
        return status(r), wait


def run(config, *, server=None, operation=None, environment=None):
    if (server is None) == (operation is None):
        raise AdminError("Select either a new nightly server or an existing operation")
    operation = (
        prepare(config, server, environment)["operation"]
        if server is not None
        else operation
    )
    while True:
        result, wait = tick(config, operation, environment)
        if result["stage"] in TERMINAL:
            return result
        if wait > 0:
            pause(min(wait, 1))


def cancel(config, operation, environment=None):
    with backups.locked(config):
        r = read(config, operation)
        if r["stage"] == "cancelled":
            return status(r)
        if r["stage"] not in {
            "created",
            "warnings",
            "warning-requested",
            "closing",
            "stopping",
        }:
            raise AdminError(
                "Nightly cannot cancel after stop/backup/start; inspect and resume its children"
            )
        current = maintenance.snapshot(r["target"], r["binding"])
        if current != r["initial"]:
            raise AdminError(
                "Nightly cancellation requires its unchanged running source"
            )
        path = maintenance.journal(config, r["children"]["maintenance"])
        if path.exists():
            m = maintenance.read_record(config, path.stem)
            if m["stage"] != "planned":
                raise AdminError("Nightly maintenance is already attempted")
        close_path = ingress.journal(config, r["children"]["close"])
        if close_path.exists():
            gate = ingress.read(config, close_path.stem)
            if gate["stage"] == "planned":
                ingress.abandon_close_plan(config, gate["operation"])
            elif gate["stage"] == "applying":
                ingress.execute(config, gate["operation"], "verify")
        if path.exists():
            maintenance.execute(
                config, m["operation"], "cancel", environment=environment
            )
        save(config, r, "cancelled")
        return status(r)
