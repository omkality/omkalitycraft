"""Owner journal for one selected full-release file return, never game lifecycle.

The controller supplies trusted snapshot selection and a Docker ownership fence,
holds the same operation lock and mounts both stopped sources read-only. Uncertain
writes are inspected, never repeated. No auth restore or boot/promotion permit.
"""

import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from omk.backups.backup_store import _directory, _sync_directory
from omk.game import project_policy as policy
from omk.owner import admin_backups as owner
from omk.owner.admin import AdminError, _private_path, _read_json, _write_private
from omk.owner.storage import project_stage as raw
from omk.shared.fs import resolved

PHASES = {
    "planned",
    "raw-requested",
    "raw-staged",
    "policy-requested",
    "files-verified",
}
IMMUTABLE = {
    "schema",
    "operation",
    "server",
    "source",
    "target",
    "current",
    "raw",
    "adapter",
    "current_sha256",
    "fence_sha256",
    "created_at",
    "expires_at",
}


def path(config, operation):
    if not isinstance(operation, str) or not re.fullmatch(r"[a-f0-9]{32}", operation):
        raise AdminError("Invalid project return operation")
    return _private_path(config.private, "project-returns/" + operation + ".json")


def _now():
    return datetime.now(UTC)


def _current(current, world):
    _directory(current)
    policy.shared.ftb.check_runtime(current)
    data, _records, summary = policy.shared._current(current, world)
    if json.loads(data["ops.json"]):
        raise AdminError("Current project return authority must not contain operators")
    properties = policy.shared._read(current, "server.properties")
    policy.protected_properties(properties, properties, world)
    return raw._digest(summary)


def _fence(checkpoint):
    value = checkpoint()
    if not isinstance(value, dict) or len(json.dumps(value).encode()) > 65536:
        raise AdminError("Invalid project return ownership fence")
    # Docker callbacks must return whitelisted metadata, never Config.Env/Args.
    return raw._digest(value)


def _locations(config, source, target, current):
    for p in (source, target, current, config.private):
        _directory(p)
        if not p.is_absolute() or resolved(p) != p.absolute():
            raise AdminError("Project return requires explicit unlinked roots")
    roots = (source, target, current, config.private)
    if any(
        a.is_relative_to(b) or b.is_relative_to(a)
        for i, a in enumerate(roots)
        for b in roots[i + 1 :]
    ):
        raise AdminError("Project return sources, target and journal must be separate")


def _save(config, r, phase):
    r["phase"] = phase
    if len(json.dumps(r).encode()) > 65536:
        raise AdminError("Project return journal exceeds limit")
    _write_private(path(config, r["operation"]), config.private, r)
    _sync_directory(path(config, r["operation"]).parent)
    _sync_directory(config.private)


def read(config, operation):
    r = _read_json(path(config, operation), config.private)
    expected = IMMUTABLE | {"intent_sha256", "phase"}
    if (
        set(r) - expected - {"policy"}
        or not expected <= set(r)
        or type(r["schema"]) is not int
        or r["schema"] != 1
        or r["operation"] != operation
        or r["server"] not in config.servers
        or r["phase"] not in PHASES
        or r["adapter"] != policy.ADAPTER
        or raw._digest({k: r[k] for k in IMMUTABLE}) != r["intent_sha256"]
        or ("policy" in r) != (r["phase"] in {"policy-requested", "files-verified"})
    ):
        raise AdminError("Invalid project return journal")
    return r


def status(config, operation):
    r = read(config, operation)
    return {
        "operation": operation,
        "server": r["server"],
        "phase": r["phase"],
        "files_verified": r["phase"] == "files-verified",
        **policy.FLAGS,
        "current_policy_reconciled": r["phase"] == "files-verified",
    }


def plan(
    config,
    server,
    source,
    target,
    current,
    *,
    world,
    selection,
    settings,
    checkpoint,
    environment=None,
    operation=None,
):
    """Persist independently selected identity before the first target write."""
    if server not in config.servers or config.servers[server] != current:
        raise AdminError("Current source must match the owner server allowlist")
    _locations(config, source, target, current)
    operation = uuid4().hex if operation is None else operation
    journal = path(config, operation)
    limits = owner.settings(environment)
    with owner.locked(config):
        folder = journal.parent
        if folder.exists() and (
            folder.is_symlink()
            or any(
                not p.is_file()
                or p.is_symlink()
                or not re.fullmatch(r"[a-f0-9]{32}\.json", p.name)
                for p in folder.iterdir()
            )
        ):
            raise AdminError("Project return journal contains foreign entries")
        if journal.exists() or (
            folder.exists() and len(list(folder.iterdir())) >= limits["journal_count"]
        ):
            raise AdminError(
                "Project return journal capacity or operation already used"
            )
        fence = _fence(checkpoint)
        current_hash = _current(current, world)
        expected = raw.plan(
            source,
            target,
            operation=operation,
            world=world,
            selection=selection,
            settings=settings,
        )
        if _fence(checkpoint) != fence or _current(current, world) != current_hash:
            raise AdminError("Project return source changed during planning")
        now = _now()
        r = {
            "schema": 1,
            "operation": operation,
            "server": server,
            "source": str(source),
            "target": str(target),
            "current": str(current),
            "raw": expected,
            "adapter": policy.ADAPTER,
            "current_sha256": current_hash,
            "fence_sha256": fence,
            "created_at": now.isoformat(),
            "expires_at": (
                now + timedelta(seconds=limits["plan_ttl_seconds"])
            ).isoformat(),
        }
        r["intent_sha256"] = raw._digest(r)
        _save(config, r, "planned")
    return status(config, operation)


def _stable(config, r, checkpoint, *, start=False):
    source, target, current = (Path(r[k]) for k in ("source", "target", "current"))
    _locations(config, source, target, current)
    if config.servers.get(r["server"]) != current:
        raise AdminError("Project return current source allowlist changed")
    if (
        _fence(checkpoint) != r["fence_sha256"]
        or _current(current, r["raw"]["world"]) != r["current_sha256"]
    ):
        raise AdminError("Project return ownership or current source changed")
    created, expires = (
        datetime.fromisoformat(r[k]) for k in ("created_at", "expires_at")
    )
    now = _now()
    if (
        created.utcoffset() != timedelta(0)
        or expires.utcoffset() != timedelta(0)
        or expires <= created
    ):
        raise AdminError("Invalid project return lifetime")
    if start and not created <= now <= expires:
        raise AdminError("Project return plan expired or clock moved backwards")
    raw._bound(source, target, r["raw"])
    return source, target, current


def run(config, operation, *, checkpoint):
    """Apply only a known unstarted phase; unknown writes require explicit verify."""
    with owner.locked(config):
        r = read(config, operation)
        if r["phase"] not in {"planned", "raw-staged"}:
            raise AdminError(
                "Project return write already requested; inspect with verify"
            )
        source, target, current = _stable(config, r, checkpoint, start=True)
        if r["phase"] == "planned":
            _save(config, r, "raw-requested")
            raw.stage(source, target, expected=r["raw"])
            _stable(config, r, checkpoint)
            _save(config, r, "raw-staged")
        r["policy"] = policy.plan(
            source, target, current, raw_expected=r["raw"], adapter=r["adapter"]
        )
        _stable(config, r, checkpoint, start=True)
        _save(config, r, "policy-requested")
        policy.stage(
            source, target, current, raw_expected=r["raw"], expected=r["policy"]
        )
        _stable(config, r, checkpoint)
        policy.verify(
            source, target, current, raw_expected=r["raw"], expected=r["policy"]
        )
        _save(config, r, "files-verified")
    return status(config, operation)


def verify(config, operation, *, checkpoint):
    """Inspect uncertain output without file apply; recovery may advance the journal."""
    with owner.locked(config):
        r = read(config, operation)
        if r["phase"] == "planned":
            raise AdminError("Project return has no requested write to verify")
        source, target, current = _stable(config, r, checkpoint)
        if r["phase"] in {"raw-requested", "raw-staged"}:
            raw.verify(source, target, expected=r["raw"])
            _stable(config, r, checkpoint)
            _save(config, r, "raw-staged")
        else:
            policy.verify(
                source, target, current, raw_expected=r["raw"], expected=r["policy"]
            )
            _stable(config, r, checkpoint)
            _save(config, r, "files-verified")
    return status(config, operation)
