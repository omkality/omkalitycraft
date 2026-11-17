"""Bounded read-only projection of allowlisted servers and recent live journals.

No runtime probe, lock acquisition, credentials, audit write or scheduler dispatch.
The view is sampled across files, not an atomic snapshot of the estate.
"""

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from omk.admin import AdminError, _private_path, load_operator_config
from omk.owner_metrics import Metric
from omk.owner_result import TERMINAL, OperationView, ServerId

MAX_CANDIDATES = 2000
MAX_OPERATIONS = 128


class Overview(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal[1] = 1
    action: Literal["owner.overview"] = "owner.overview"
    ok: bool
    server_ids: list[ServerId] = Field(default_factory=list, max_length=100)
    operations: list[OperationView] = Field(
        default_factory=list, max_length=MAX_OPERATIONS
    )
    skipped: int = Field(default=0, ge=0, le=MAX_OPERATIONS)
    truncated: bool = False
    selected_server: ServerId | None = None
    metrics_status: Literal["disabled", "available", "partial", "unavailable"] = (
        "disabled"
    )
    metrics: list[Metric] = Field(default_factory=list, max_length=6)
    error: Literal["invalid_configuration", "overview_unavailable"] | None = None


def sample(config, server=None):
    from omk import (  # noqa: PLC0415
        admin_backups,
        admin_maintenance,
        admin_restores,
        owner_metrics,
    )

    readers = {
        "backups": admin_backups.read_record,
        "maintenance": admin_maintenance.read_record,
        "restores": admin_restores.read_record,
    }
    candidates = []
    truncated = False
    # Scan each directory with an explicit bound; never recursively walk userdata.
    for kind in readers:
        folder = _private_path(config.private, kind)
        if not folder.exists():
            continue
        for count, entry in enumerate(folder.iterdir()):
            if count >= MAX_CANDIDATES:
                truncated = True
                break
            if not re.fullmatch(r"[a-f0-9]{32}\.json", entry.name):
                continue
            candidates.append((entry.lstat().st_mtime_ns, kind, entry.stem))
    candidates.sort(reverse=True)
    truncated |= len(candidates) > MAX_OPERATIONS
    operations, skipped = [], 0
    for _, kind, identity in candidates[:MAX_OPERATIONS]:
        try:
            record = readers[kind](config, identity)
            operation = OperationView(
                id=identity,
                kind=kind,
                server_id=record["server"],
                phase=record["stage"],
                terminal=record["stage"] in TERMINAL[kind],
                backup_operation_id=record.get("backup_operation"),
            )
            if operation.server_id not in config.servers:
                raise ValueError("Server no longer allowlisted")
            operations.append(operation)
        except AdminError, OSError, ValueError, KeyError, TypeError:
            skipped += 1
    selected = (
        server if server is not None else next(iter(sorted(config.servers)), None)
    )
    if selected is not None and selected not in config.servers:
        raise AdminError("Unknown server")
    metric_status, metrics = owner_metrics.sample(config, selected)
    return Overview(
        ok=True,
        server_ids=sorted(config.servers),
        operations=operations,
        skipped=skipped,
        truncated=truncated,
        selected_server=selected,
        metrics_status=metric_status,
        metrics=metrics,
    ).model_dump(mode="json")


def run(path, server=None):
    try:
        config = load_operator_config(path)
    except Exception:
        return Overview(ok=False, error="invalid_configuration").model_dump(mode="json")
    try:
        return sample(config, server)
    except Exception:
        # No paths, credential material or raw journal errors cross this boundary.
        return Overview(ok=False, error="overview_unavailable").model_dump(mode="json")
