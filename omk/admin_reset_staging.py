"""Owner preparation of a separate reset candidate/runtime; no live promotion."""

import json
import re
from datetime import UTC, datetime
from uuid import uuid4

from omk import (
    admin_backups as backups,
    admin_maintenance as maintenance,
    owner_volumes,
)
from omk.admin import AdminError, _private_path, _read_json, _write_private
from omk.backup_store import _sync_directory
from omk.cold_backup_worker import digest
from omk.profiles import PROJECT_ROOT
from omk.resource_reset_preflight import settings as preflight_settings

STAGES = {
    "planned",
    "staging",
    "incomplete",
    "staged",
    "abandoned",
    "runtime-planned",
    "runtime-writing",
    "runtime-incomplete",
    "runtime-ready",
}


def journal(config, operation):
    if not isinstance(operation, str) or not re.fullmatch(r"[a-f0-9]{32}", operation):
        raise AdminError("Invalid resource staging operation identifier")
    return _private_path(config.private, "resource-resets/" + operation + ".json")


def read_record(config, operation):
    record = _read_json(journal(config, operation), config.private)
    required = {
        "schema",
        "operation",
        "server",
        "maintenance_operation",
        "maintenance_sha256",
        "backup_operation",
        "backup_sha256",
        "dimension",
        "source",
        "target",
        "settings",
        "preflight_options",
        "created_at",
        "updated_at",
        "operator_root",
        "checkpoint",
        "destination",
        "snapshot",
        "expected",
        "stage",
    }
    if (
        type(record.get("schema")) is not int
        or record.get("schema") != 1
        or record.get("operation") != operation
        or not required <= set(record)
        or set(record)
        - required
        - {
            "result",
            "failure_type",
            "runtime_expected",
            "runtime_created_at",
            "runtime_result",
        }
        or record.get("stage") not in STAGES
        or not isinstance(record.get("maintenance_operation"), str)
        or not re.fullmatch(r"[a-f0-9]{32}", record["maintenance_operation"])
        or not isinstance(record.get("server"), str)
    ):
        raise AdminError("Invalid resource staging journal")
    return record


def records(config):
    folder = _private_path(config.private, "resource-resets")
    if not folder.exists():
        return []
    paths = []
    for path in folder.iterdir():
        if len(paths) >= 1000:
            raise AdminError("Resource staging journal exceeds its supported bound")
        paths.append(path)
    return [read_record(config, path.stem) for path in paths]


def list_operations(config, server):
    if server not in config.servers:
        raise AdminError("Server is not in the operator allowlist")
    with backups.locked(config):
        return {
            "ok": True,
            "operations": [status(r) for r in records(config) if r["server"] == server],
        }


def require_clear(config, maintenance_operation):
    if any(
        r["maintenance_operation"] == maintenance_operation
        and r["stage"] != "abandoned"
        for r in records(config)
    ):
        raise AdminError(
            "Resource candidate is pending; explicitly abandon it before resuming or closing this maintenance window"
        )


def save(config, record, stage):
    record.update(stage=stage, updated_at=datetime.now(UTC).isoformat())
    if len(json.dumps(record).encode()) > 65536:
        raise AdminError("Resource staging journal exceeds limit")
    _write_private(journal(config, record["operation"]), config.private, record)
    _sync_directory(config.private / "resource-resets")


def status(record):
    expected = record["expected"]
    return {
        "ok": True,
        "operation": record["operation"],
        "server": record["server"],
        "stage": record["stage"],
        "maintenance_operation": record["maintenance_operation"],
        "backup_operation": record["backup_operation"],
        "dimension": record["dimension"],
        "target_volume": record["target"]["data_volume"],
        "snapshot": expected["snapshot"],
        "landing": expected["position"],
        "retained_files": expected["retained_files"],
        "omitted_files": expected["omitted_files"],
        "changed_files": expected["changed_files"],
        "runtime_prepared": "runtime_result" in record,
        "source_changes": False,
        "promoted": False,
        "ready_for_start": False,
        "ready_for_players": False,
    }


def backup_for(config, record):
    backup = backups.read_record(config, record["backup_operation"])
    if (
        backup.get("stage") != "complete"
        or backup.get("server") != record["server"]
        or backup.get("target") != record["source"]
        or backup.get("checkpoint") != record["checkpoint"]
        or backup.get("operator_root") != record["operator_root"]
        or backup.get("settings") != record["settings"]
        or ("backup_sha256" in record and digest(backup) != record["backup_sha256"])
    ):
        raise AdminError(
            "Resource staging requires the completed backup of this exact clean stop"
        )
    return backup


def stable(config, record, *, allowed_container=None):
    window = maintenance.read_record(config, record["maintenance_operation"])
    if (
        window.get("stage") != "stopped"
        or digest(window) != record["maintenance_sha256"]
        or window.get("server") != record["server"]
        or window.get("target") != record["source"]
        or window.get("checkpoint") != record["checkpoint"]
        or str(config.servers[record["server"]]) != record["operator_root"]
        or backups.target_for(config, record["server"]) != record["source"]
        or owner_volumes.target_for(
            config, record["server"], record["source"], "resource-resets.toml"
        )
        != record["target"]
    ):
        raise AdminError("Resource staging configuration or maintenance window changed")
    maintenance.current(config, window)
    if (
        backups.checkpoint(record["source"]) != record["checkpoint"]
        or owner_volumes.destination(
            record["target"],
            unused=True,
            **({"allowed_container": allowed_container} if allowed_container else {}),
        )
        != record["destination"]
    ):
        raise AdminError("Resource staging source lifecycle or destination changed")
    backup = backup_for(config, record)
    if backup["source"]["runtime_sha256"] != window["runtime"]["runtime_sha256"]:
        raise AdminError(
            "Resource staging runtime changed after the clean maintenance stop"
        )


def worker(record, action, *, allowed_container=None):
    source, target, policy = record["source"], record["target"], record["settings"]
    # Never let Docker create an absent named volume on --mount.
    backups.volume(source)
    backups.volume(source, True)
    owner_volumes.destination(
        target,
        unused=True,
        **({"allowed_container": allowed_container} if allowed_container else {}),
    )
    request = {
        "schema": 1,
        "action": action,
        "operation": record["operation"],
        "world": source["world"],
        "dimension": record["dimension"],
        "position": "auto",
        "snapshot": record["snapshot"],
        "world_max_bytes": policy["world_max_bytes"],
        "preflight_options": record["preflight_options"],
        "policy": {
            k: policy[k]
            for k in ("max_bytes", "max_count", "staging_bytes", "reserve_bytes")
        },
    }
    runtime = action.startswith("runtime-")
    if action != "plan":
        request["expected"] = record["expected"]
    if runtime and action != "runtime-plan":
        request["runtime_expected"] = record["runtime_expected"]
    writable = action in {"stage", "runtime-stage"}
    args = [
        "run",
        "--rm",
        "--pull",
        "never",
        "-i",
        "--name",
        "omk-reset-stage-" + record["operation"],
        "--label",
        "omkality.reset.staging=" + record["operation"],
        "--network",
        "none",
        "--read-only",
        "--log-driver",
        "none",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges:true",
        "--memory",
        str(policy["helper_memory_mib"]) + "m",
        "--cpus",
        str(policy["helper_cpus"]),
        "--pids-limit",
        "32",
        "--mount",
        f"type=volume,source={source['data_volume']},target=/server,readonly",
        "--mount",
        f"type=volume,source={source['store_volume']},target=/backup,readonly",
        "--mount",
        f"type=volume,source={target['data_volume']},target=/target"
        + ("" if writable else ",readonly"),
    ]
    for module in ("omk", "launcher", "profiles"):
        args += [
            "--mount",
            f"type=bind,source={PROJECT_ROOT/module},target=/src/{module},readonly",
        ]
    raw = backups.docker(
        *args,
        "--workdir",
        "/src",
        "--env",
        "PYTHONDONTWRITEBYTECODE=1",
        backups.IMAGE,
        "python",
        "-m",
        "omk.resource_reset_runtime" if runtime else "omk.resource_reset_stage",
        stdin=json.dumps(request),
        timeout=policy["timeout_seconds"],
        allowed_codes=(0, 1),
    )
    if len(raw.encode()) > 65536:
        raise AdminError("Resource staging response exceeded limit")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise AdminError("Invalid resource staging worker response")
    result = value.get("result")
    if (
        value.get("ok") is not True
        or not isinstance(result, dict)
        or result.get("ready_for_start") is not False
    ):
        kind = value.get("error_type", "InvalidResponse")
        if not isinstance(kind, str) or not re.fullmatch(r"[A-Za-z]{1,64}", kind):
            kind = "InvalidResponse"
        raise AdminError(
            "Resource staging refused ("
            + kind
            + "); inspect the private journal and retained target"
        )
    if runtime:
        if (
            result.get("operation") != record["operation"]
            or result.get("ready_for_players") is not False
            or (
                result.get("data_plan_sha256") != digest(record["expected"])
                if action == "runtime-plan"
                else result.get("runtime_plan_sha256")
                != digest(record["runtime_expected"])
                or result.get("runtime_prepared") is not True
                or result.get("promoted") is not False
            )
        ):
            raise AdminError("Runtime worker returned a different identity or receipt")
    elif action == "plan":
        if (
            any(
                result.get(k) != request[k]
                for k in ("operation", "world", "dimension", "snapshot")
            )
            or result.get("preflight", {}).get("policy") != record["preflight_options"]
        ):
            raise AdminError(
                "Resource staging worker returned a different plan identity"
            )
    elif (
        result.get("operation") != record["operation"]
        or result.get("staged") is not True
        or result.get("promoted") is not False
        or result.get("plan_sha256") != digest(record["expected"])
    ):
        raise AdminError("Resource staging worker returned a different receipt")
    return result


def plan(
    config, server, dimension, maintenance_operation, backup_operation, environment=None
):
    with backups.locked(config):
        backups.local_engine()
        source = backups.target_for(config, server)
        target = owner_volumes.target_for(
            config, server, source, "resource-resets.toml"
        )
        if type(dimension) is not int or dimension != target["dimension"]:
            raise AdminError(
                "Dimension differs from the explicit resource staging allowlist"
            )
        window = maintenance.read_record(config, maintenance_operation)
        if window.get("stage") != "stopped" or window.get("server") != server:
            raise AdminError("Resource staging requires a stopped maintenance window")
        previous = records(config)
        policy = backups.settings(environment)
        if len(previous) >= policy["journal_count"]:
            raise AdminError(
                "Resource staging journal limit reached; archive abandoned records"
            )
        if any(
            r["stage"] != "abandoned"
            and (
                r["server"] == server
                or r["target"]["data_volume"] == target["data_volume"]
            )
            for r in previous
        ):
            raise AdminError(
                "Resolve the existing resource candidate before planning another"
            )
        record = {
            "schema": 1,
            "operation": uuid4().hex,
            "server": server,
            "maintenance_operation": maintenance_operation,
            "maintenance_sha256": digest(window),
            "backup_operation": backup_operation,
            "dimension": dimension,
            "source": source,
            "target": target,
            "settings": policy,
            "preflight_options": preflight_settings(environment),
            "created_at": datetime.now(UTC).isoformat(),
            "operator_root": str(config.servers[server]),
            "checkpoint": window["checkpoint"],
            "destination": owner_volumes.destination(target, unused=True),
        }
        backup = backup_for(config, record)
        record["backup_sha256"] = digest(backup)
        record["snapshot"] = backup["result"]["id"]
        stable(config, record)
        record["expected"] = worker(record, "plan")
        if (
            record["expected"].get("source") != backup["source"]
            or record["expected"].get("archive_sha256") != backup["result"]["sha256"]
        ):
            raise AdminError(
                "Resource candidate differs from the completed backup source"
            )
        stable(config, record)
        save(config, record, "planned")
        return status(record)


def runtime_action(config, record, action, environment):
    if action == "runtime-plan":
        if record["stage"] != "staged" or "runtime_expected" in record:
            raise AdminError("Runtime planning requires an unchanged data-only stage")
        if record["settings"] != backups.settings(environment) or record[
            "preflight_options"
        ] != preflight_settings(environment):
            raise AdminError("Runtime policy differs from the frozen source backup")
        record["runtime_expected"] = worker(record, action)
        record["runtime_created_at"] = datetime.now(UTC).isoformat()
        stable(config, record)
        save(config, record, "runtime-planned")
        return status(record)
    if action == "runtime-stage":
        if record["stage"] != "runtime-planned":
            raise AdminError("Runtime preparation was already attempted or not planned")
        age = (
            datetime.now(UTC) - datetime.fromisoformat(record["runtime_created_at"])
        ).total_seconds()
        if (
            not 0 <= age <= record["settings"]["plan_ttl_seconds"]
            or record["settings"] != backups.settings(environment)
            or record["preflight_options"] != preflight_settings(environment)
        ):
            raise AdminError("Runtime plan is stale or policy changed")
        save(config, record, "runtime-writing")
        try:
            result = worker(record, action)
        except Exception as error:
            record["failure_type"] = type(error).__name__
            save(config, record, "runtime-incomplete")
            raise AdminError(
                "Runtime incomplete; verify a complete receipt or abandon; never repeat"
            ) from None
    elif action == "runtime-verify":
        if record["stage"] not in {
            "runtime-writing",
            "runtime-incomplete",
            "runtime-ready",
        }:
            raise AdminError("No attempted runtime preparation to verify")
        result = worker(record, action)
    else:
        raise AdminError("Unsupported runtime action")
    stable(config, record)
    record["runtime_result"] = result
    save(config, record, "runtime-ready")
    return status(record)


def execute(config, operation, action, environment=None):
    with backups.locked(config):
        record = read_record(config, operation)
        if action == "status" or (
            action == "abandon" and record["stage"] == "abandoned"
        ):
            return status(record)
        backups.local_engine()
        if action == "abandon":
            from omk.candidate_slots import require_clear  # noqa: PLC0415

            require_clear(config, operation)
        stable(config, record)
        if action == "abandon":
            save(config, record, "abandoned")
            return status(record)
        if action.startswith("runtime-"):
            return runtime_action(config, record, action, environment)
        if action == "verify":
            if "runtime_expected" in record:
                raise AdminError(
                    "Use runtime-verify after runtime planning; data verify cannot downgrade it"
                )
            if record["stage"] not in {"staging", "incomplete", "staged"}:
                raise AdminError("No attempted resource candidate to verify")
            result = worker(record, "verify")
        elif action == "stage":
            age = (
                datetime.now(UTC) - datetime.fromisoformat(record["created_at"])
            ).total_seconds()
            if (
                record["stage"] != "planned"
                or not 0 <= age <= record["settings"]["plan_ttl_seconds"]
                or record["settings"] != backups.settings(environment)
                or record["preflight_options"] != preflight_settings(environment)
            ):
                raise AdminError(
                    "Resource staging plan is stale, changed or already attempted"
                )
            save(config, record, "staging")
            try:
                result = worker(record, "stage")
            except Exception as error:
                record["failure_type"] = type(error).__name__
                save(config, record, "incomplete")
                raise AdminError(
                    "Resource staging incomplete; verify a complete receipt or abandon; never repeat stage"
                ) from None
        else:
            raise AdminError("Unsupported resource staging action")
        stable(config, record)
        record["result"] = result
        save(config, record, "staged")
        return status(record)
