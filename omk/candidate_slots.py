"""Owner-only loopback candidate lifecycle. No public ingress or promotion."""

import contextlib
import hashlib
import json
import os
import re
import time
from datetime import UTC, datetime
from uuid import uuid4

from omk import (
    admin_backups as backups,
    admin_maintenance as maintenance,
    admin_reset_staging as staging,
    candidate_slot_spec as template,
)
from omk.admin import AdminError, _private_path, _read_json, _write_private
from omk.backup_store import _sync_directory
from omk.cold_backup_worker import digest
from omk.maintenance_console import stop as console_stop
from omk.profiles import PROJECT_ROOT
from omk.recovery_console import ConsoleConfig, ConsoleError, RecoveryConsole

STAGES = {
    "planned",
    "create-requested",
    "created",
    "start-requested",
    "running",
    "stop-requested",
    "stopped",
    "release-requested",
    "released",
}
LABEL = "omkality.candidate.operation"


def path(config, operation):
    if not isinstance(operation, str) or not re.fullmatch(r"[a-f0-9]{32}", operation):
        raise AdminError("Invalid candidate slot operation")
    return _private_path(config.private, "candidate-slots/" + operation + ".json")


def save(config, r, stage):
    r.update(stage=stage, updated_at=datetime.now(UTC).isoformat())
    if len(json.dumps(r).encode()) > 65536:
        raise AdminError("Candidate slot journal exceeds bound")
    _write_private(path(config, r["operation"]), config.private, r)
    _sync_directory(path(config, r["operation"]).parent)


def read(config, operation):
    r = _read_json(path(config, operation), config.private)
    required = {
        "schema",
        "operation",
        "server",
        "resource_operation",
        "parent_sha256",
        "spec",
        "policy",
        "lifecycle",
        "network",
        "image",
        "metadata_sha256",
        "template_sha256",
        "logging_sha256",
        "command_sha256",
        "created_at",
        "updated_at",
        "stage",
        "proof",
    }
    if (
        type(r.get("schema")) is not int
        or r["schema"] != 1
        or r.get("operation") != operation
        or not required <= set(r)
        or set(r)
        - required
        - {"initial", "boot", "stop_boot", "checkpoint", "release_logs"}
        or r.get("stage") not in STAGES
        or not isinstance(r.get("resource_operation"), str)
        or not re.fullmatch(r"[a-f0-9]{32}", r["resource_operation"])
    ):
        raise AdminError("Invalid candidate slot journal")
    return r


def records(config):
    folder = _private_path(config.private, "candidate-slots")
    if not folder.exists():
        return []
    paths = []
    for p in folder.iterdir():
        if p.suffix == ".log":
            continue
        if len(paths) >= 1000:
            raise AdminError("Candidate journal exceeds supported bound")
        paths.append(p)
    return [read(config, p.stem) for p in paths]


def require_clear(config, resource_operation):
    if any(
        r["resource_operation"] == resource_operation and r["stage"] != "released"
        for r in records(config)
    ):
        raise AdminError(
            "Candidate slot is pending; release it before abandoning the resource operation"
        )


def status(r):
    return {
        "ok": True,
        "operation": r["operation"],
        "server": r["server"],
        "resource_operation": r["resource_operation"],
        "stage": r["stage"],
        "container_id": r.get("initial", {}).get("id"),
        "game_address": "127.0.0.1:" + str(r["spec"]["game_host_port"]),
        "loopback_only": True,
        "health_confirmed": r["stage"] == "running",
        "promoted": False,
        "ready_for_players": False,
    }


def parent(config, r, container=None):
    p = staging.read_record(config, r["resource_operation"])
    if (
        p["stage"] != "runtime-ready"
        or p["server"] != r["server"]
        or digest(p) != r["parent_sha256"]
    ):
        raise AdminError("Candidate parent operation changed or was abandoned")
    staging.stable(config, p, **({"allowed_container": container} if container else {}))
    return p


def current(config, r, container=None):
    p = parent(config, r, container)
    if (
        template.definition(config, r["server"]) != r["spec"]
        or template.network(r["spec"]) != r["network"]
        or digest(template.metadata(config, r["spec"])) != r["metadata_sha256"]
    ):
        raise AdminError("Candidate slot definition, auth metadata or network changed")
    return p


def raw_container(name):
    # A daemon failure must never look like "container absent".
    selector = (
        "id=" + name
        if re.fullmatch(r"[a-f0-9]{64}", name)
        else "name=^/" + re.escape(name) + "$"
    )
    ids = backups.docker("ps", "-aq", "--no-trunc", "--filter", selector).split()
    if not ids:
        return None
    if len(ids) != 1:
        raise AdminError("Ambiguous candidate container lookup")
    raw = backups.docker("inspect", "--type", "container", ids[0])
    rows = json.loads(raw)
    if len(rows) != 1:
        raise AdminError("Ambiguous candidate container")
    return rows[0]


def snapshot(r, p, *, lookup=None):
    data = raw_container(
        lookup or r.get("initial", {}).get("id") or r["spec"]["container"]
    )
    if data is None:
        raise AdminError("Candidate container is absent; reconcile the recorded intent")
    spec, policy = r["spec"], r["policy"]
    c, h, s = data["Config"], data["HostConfig"], data["State"]
    expected_ports = {
        str(spec[k + "_container_port"])
        + "/tcp": [{"HostIp": "127.0.0.1", "HostPort": str(spec[k + "_host_port"])}]
        for k in ["game", "rcon"]
    }
    mount = data.get("Mounts", [])
    if (
        data["Name"] != "/" + spec["container"]
        or (c.get("Labels") or {}).get(LABEL) != r["operation"]
        or (c.get("Labels") or {}).get(p["target"]["label"]) != p["target"]["owner"]
        or c["Image"] != p["target"]["image"]
        or data["Image"] != r["image"]["id"]
        or digest(c.get("Cmd")) != r["command_sha256"]
        or digest(c.get("Env")) != r["image"]["env_sha256"]
        or digest(c.get("Entrypoint")) != r["image"]["entrypoint_sha256"]
        or c.get("WorkingDir") != "/srv"
        or c.get("User") not in {"", "0", "root"}
        or h.get("NetworkMode") != spec["network"]
        or h.get("PortBindings") != expected_ports
        or h.get("Memory") != policy["memory_mib"] * 1024**2
        or h.get("NanoCpus") != policy["cpus"] * 10**9
        or h.get("PidsLimit") != policy["pids"]
        or h.get("ReadonlyRootfs") is not True
        or h.get("Privileged") is not False
        or h.get("AutoRemove") is not False
        or h.get("RestartPolicy", {}).get("Name") not in {"no", ""}
        or h.get("CapDrop") != ["ALL"]
        or h.get("SecurityOpt") != ["no-new-privileges:true"]
        or any(
            h.get(k)
            for k in [
                "Binds",
                "VolumesFrom",
                "Devices",
                "DeviceRequests",
                "CapAdd",
                "ExtraHosts",
                "Links",
                "Tmpfs",
                "PidMode",
                "UTSMode",
            ]
        )
        or h.get("LogConfig") != template.docker_log_config(policy)
        or len(mount) != 1
        or mount[0].get("Type") != "volume"
        or mount[0].get("Name") != p["target"]["data_volume"]
        or mount[0].get("Destination") != "/srv"
        or mount[0].get("RW") is not True
        or s.get("Paused") is not False
        or s.get("Restarting") is not False
        or s.get("OOMKilled") is not False
        or data["RestartCount"] != 0
        or s.get("Status") not in {"created", "running", "exited"}
        or (s.get("Running") and data["NetworkSettings"].get("Ports") != expected_ports)
        or (
            s.get("Running")
            and data["NetworkSettings"]
            .get("Networks", {})
            .get(spec["network"], {})
            .get("NetworkID")
            != r["network"]["id"]
        )
    ):
        raise AdminError(
            "Candidate container differs from the owned immutable loopback template"
        )
    result = {
        "id": data["Id"],
        "created": data["Created"],
        "image": data["Image"],
        "started": s["StartedAt"],
        "finished": s["FinishedAt"],
        "status": s["Status"],
        "exit_code": s["ExitCode"],
        "running": s["Running"],
    }
    if "initial" in r and any(
        result[k] != r["initial"][k] for k in ["id", "created", "image"]
    ):
        raise AdminError("Candidate immutable identity changed")
    return result


def runtime_proof(config, r, p, container=None):
    # Full receipt verification plus template pins/properties, always readonly.
    value = staging.worker(
        p, "runtime-verify", **({"allowed_container": container} if container else {})
    )
    request = {
        "runtime": {
            "schema": 1,
            "action": "runtime-verify",
            "operation": p["operation"],
            "world": p["source"]["world"],
            "dimension": p["dimension"],
            "position": "auto",
            "snapshot": p["snapshot"],
            "world_max_bytes": p["settings"]["world_max_bytes"],
            "preflight_options": p["preflight_options"],
            "policy": {
                k: p["settings"][k]
                for k in ["max_bytes", "max_count", "staging_bytes", "reserve_bytes"]
            },
            "expected": p["expected"],
            "runtime_expected": p["runtime_expected"],
        },
        "binding": {
            k: r["spec"][k] for k in ["game_container_port", "rcon_container_port"]
        },
    }
    request["binding"].update(
        template_sha256=r["template_sha256"], logging_sha256=r["logging_sha256"]
    )
    args = [
        "run",
        "--rm",
        "--pull",
        "never",
        "-i",
        "--name",
        "omk-slot-proof-" + r["operation"],
        "--label",
        LABEL + "=" + r["operation"],
        "--network",
        "none",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges:true",
        "--memory",
        str(p["settings"]["helper_memory_mib"]) + "m",
        "--cpus",
        str(p["settings"]["helper_cpus"]),
        "--pids-limit",
        "32",
        "--log-driver",
        "none",
    ]
    for name, destination in [
        (p["source"]["data_volume"], "server"),
        (p["source"]["store_volume"], "backup"),
        (p["target"]["data_volume"], "target"),
    ]:
        args += ["--mount", f"type=volume,source={name},target=/{destination},readonly"]
    for name in ["omk", "launcher", "profiles"]:
        args += [
            "--mount",
            f"type=bind,source={PROJECT_ROOT/name},target=/src/{name},readonly",
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
        "omk.candidate_slot_worker",
        stdin=json.dumps(request),
        timeout=p["settings"]["timeout_seconds"],
        allowed_codes=(0, 1),
    )
    if len(raw.encode()) > 65536:
        raise AdminError("Candidate proof response exceeds bound")
    proof = json.loads(raw)
    if (
        proof.get("ok") is not True
        or proof.get("proof", {}).get("runtime_receipt_sha256") != digest(value)
        or proof["proof"].get("binding_sha256") != digest(request["binding"])
    ):
        raise AdminError(
            "Candidate template proof refused; inspect private runtime and binding"
        )
    return proof["proof"]


def plan(config, resource_operation, environment=None):
    with backups.locked(config):
        p = staging.read_record(config, resource_operation)
        if p["stage"] != "runtime-ready":
            raise AdminError("Candidate launch requires completed runtime preparation")
        rows = records(config)
        lifecycle = maintenance.settings(environment)
        if len(rows) >= lifecycle["journal_count"] or any(
            r["stage"] != "released" and r["server"] == p["server"] for r in rows
        ):
            raise AdminError(
                "Resolve existing candidate slots or archive terminal history"
            )
        staging.stable(config, p)
        spec = template.definition(config, p["server"])
        policy = template.settings(environment)
        for name in config.servers:
            try:
                source = backups.target_for(config, name)
            except AdminError:
                if name == p["server"]:
                    raise
                continue
            if source["container"] == spec["container"]:
                raise AdminError("Candidate container name aliases a source")
        if raw_container(spec["container"]) is not None:
            raise AdminError(
                "Candidate name must be absent, never adopt an existing container"
            )
        public = template.metadata(config, spec)
        _, profile_sha = template.profile()
        r = {
            "schema": 1,
            "operation": uuid4().hex,
            "server": p["server"],
            "resource_operation": resource_operation,
            "parent_sha256": digest(p),
            "spec": spec,
            "policy": policy,
            "lifecycle": lifecycle,
            "network": template.network(spec),
            "image": template.image(p["target"]["image"]),
            "metadata_sha256": digest(public),
            "template_sha256": profile_sha,
            "logging_sha256": hashlib.sha256(
                (PROJECT_ROOT / "profiles/runtime/log4j-java8.json").read_bytes()
            ).hexdigest(),
            "command_sha256": digest(template.command(spec, policy, public)),
            "created_at": datetime.now(UTC).isoformat(),
        }
        r["proof"] = runtime_proof(config, r, p)
        current(config, r)
        save(config, r, "planned")
        return status(r)


def creation(config, r, p):
    spec, policy = r["spec"], r["policy"]
    logs = template.docker_log_config(policy)["Config"]
    args = [
        "create",
        "--pull",
        "never",
        "--name",
        spec["container"],
        "--label",
        LABEL + "=" + r["operation"],
        "--label",
        p["target"]["label"] + "=" + p["target"]["owner"],
        "--network",
        spec["network"],
        "--memory",
        str(policy["memory_mib"]) + "m",
        "--cpus",
        str(policy["cpus"]),
        "--pids-limit",
        str(policy["pids"]),
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges:true",
        "--ulimit",
        "core=0",
        "--workdir",
        "/srv",
        "--log-driver",
        "local",
        "--log-opt",
        "max-size=" + logs["max-size"],
        "--log-opt",
        "max-file=" + logs["max-file"],
        "--mount",
        f"type=volume,source={p['target']['data_volume']},target=/srv",
    ]
    for k in ["game", "rcon"]:
        args += [
            "--publish",
            f"127.0.0.1:{spec[k+'_host_port']}:{spec[k+'_container_port']}",
        ]
    return backups.docker(
        *args,
        p["target"]["image"],
        *template.command(spec, policy, template.metadata(config, spec)),
    )


def capture_created(config, r):
    p = staging.read_record(config, r["resource_operation"])
    snap = snapshot(r, p, lookup=r["spec"]["container"])
    if (
        snap["status"] != "created"
        or not snap["started"].startswith("0001-")
        or datetime.fromisoformat(snap["created"].replace("Z", "+00:00"))
        <= datetime.fromisoformat(p["checkpoint"]["finished"].replace("Z", "+00:00"))
    ):
        raise AdminError("Candidate creation is unconfirmed or was already started")
    current(config, r, snap["id"])
    if runtime_proof(config, r, p, snap["id"]) != r["proof"]:
        raise AdminError("Candidate changed during creation")
    r["initial"] = snap
    save(config, r, "created")
    return status(r)


def console(config, r):
    original, password = maintenance.credential(config, r["server"])
    return (
        ConsoleConfig(r["spec"]["rcon_host_port"], original.credential_file),
        password,
    )


def wait_started(config, r):
    deadline = time.monotonic() + r["lifecycle"]["start_timeout_seconds"]
    boot = None
    healthy = None
    endpoint, password = console(config, r)
    while True:
        p = current(config, r, r["initial"]["id"])
        s = snapshot(r, p)
        if not s["running"] or s["started"] == r["initial"]["started"]:
            raise AdminError(
                "Candidate start unconfirmed; reconcile without a second start"
            )
        if datetime.fromisoformat(
            s["started"].replace("Z", "+00:00")
        ) <= datetime.fromisoformat(
            p["checkpoint"]["finished"].replace("Z", "+00:00")
        ) or (
            boot and s != boot
        ):
            raise AdminError("Candidate lifecycle changed during readiness")
        boot = s
        logs = backups.docker(
            "logs", "--since", s["started"], "--tail", "4000", s["id"]
        )
        if len(logs.encode()) > r["policy"]["log_bytes"] or any(
            x in logs
            for x in [
                "Encountered an unexpected exception",
                "This crash report has been saved to:",
            ]
        ):
            raise AdminError("Candidate boot contains fatal or oversized logs")
        try:
            if re.search(r"Done \([^\r\n]{1,64}\)!", logs):
                RecoveryConsole(endpoint, password).ready()
                healthy = healthy if healthy is not None else time.monotonic()
                if time.monotonic() - healthy >= r["lifecycle"]["ready_stable_seconds"]:
                    r["boot"] = boot
                    save(config, r, "running")
                    return status(r)
            else:
                healthy = None
        except ConsoleError, OSError, UnicodeError:
            healthy = None
        if time.monotonic() >= deadline:
            raise AdminError(
                "Candidate readiness timed out; reconcile the same start intent"
            )
        time.sleep(r["lifecycle"]["poll_milliseconds"] / 1000)


def wait_stopped(config, r):
    deadline = time.monotonic() + r["lifecycle"]["stop_timeout_seconds"]
    while True:
        p = current(config, r, r["initial"]["id"])
        s = snapshot(r, p)
        if s["started"] != r["stop_boot"]["started"]:
            raise AdminError("Candidate restarted during stop")
        if not s["running"]:
            target = {
                **p["source"],
                "container": s["id"],
                "data_volume": p["target"]["data_volume"],
                "source_owner": p["target"]["owner"],
                "label": p["target"]["label"],
            }
            r["checkpoint"] = backups.checkpoint(target)
            save(config, r, "stopped")
            return status(r)
        if time.monotonic() >= deadline:
            raise AdminError("Candidate stop unconfirmed; no force kill was sent")
        time.sleep(r["lifecycle"]["poll_milliseconds"] / 1000)


def log_path(config, r):
    return _private_path(config.private, "candidate-slots/" + r["operation"] + ".log")


def retained_logs(config, r, text=None):
    p = log_path(config, r)
    expected = r["release_logs"]
    if not p.exists() and text is not None:
        with p.open("xb") as stream:
            p.chmod(0o600)
            stream.write(text.encode())
            stream.flush()
            os.fsync(stream.fileno())
        _sync_directory(p.parent)
    if (
        not p.exists()
        or p.is_symlink()
        or p.is_junction()
        or p.stat().st_size > r["policy"]["log_bytes"]
        or (os.name != "nt" and p.stat().st_mode & 0o077)
    ):
        raise AdminError("Candidate retained logs missing, linked or oversized")
    raw = p.read_bytes()
    if {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()} != expected:
        raise AdminError("Candidate retained logs do not match release intent")


def reconcile_release(config, r):
    if raw_container(r["spec"]["container"]) is not None:
        raise AdminError(
            "Candidate release remains unconfirmed; no repeat removal was sent"
        )
    current(config, r)
    retained_logs(config, r)
    save(config, r, "released")
    return status(r)


def request_reconcile(config, r, p, environment):
    if r["stage"] == "create-requested":
        return capture_created(config, r)
    if r["stage"] == "start-requested":
        return wait_started(config, r)
    if r["stage"] == "stop-requested":
        return wait_stopped(config, r)
    if r["stage"] == "release-requested":
        return reconcile_release(config, r)
    raise AdminError("No candidate intent needs reconciliation")


def request_create(config, r, p, environment):
    if (
        r["stage"] != "planned"
        or template.settings(environment) != template.complete_policy(r["policy"])
        or maintenance.settings(environment) != r["lifecycle"]
        or not 0
        <= (datetime.now(UTC) - datetime.fromisoformat(r["created_at"])).total_seconds()
        <= r["lifecycle"]["plan_ttl_seconds"]
    ):
        raise AdminError("Candidate plan stale, changed or already attempted")
    if raw_container(r["spec"]["container"]) is not None:
        raise AdminError("Candidate name was taken after planning")
    if (
        runtime_proof(config, r, p) != r["proof"]
        or template.profile()[1] != r["template_sha256"]
    ):
        raise AdminError("Candidate runtime/template changed")
    save(config, r, "create-requested")
    creation(config, r, p)
    return capture_created(config, r)


def request_start(config, r, p, environment):
    if r["stage"] != "created":
        raise AdminError("Candidate start was already attempted or is not created")
    cid = r["initial"]["id"]
    s = snapshot(r, p)
    if s != r["initial"] or runtime_proof(config, r, p, cid) != r["proof"]:
        raise AdminError("Candidate changed before first start")
    save(config, r, "start-requested")
    backups.docker("start", cid)
    return wait_started(config, r)


def request_stop(config, r, p, environment):
    if r["stage"] not in {"running", "start-requested"}:
        raise AdminError("Candidate has no running start to stop")
    r["stop_boot"] = snapshot(r, p)
    save(config, r, "stop-requested")
    endpoint, password = console(config, r)
    with contextlib.suppress(ConsoleError, OSError, UnicodeError):
        console_stop(endpoint, password)
    return wait_stopped(config, r)


def request_release(config, r, p, environment):
    if r["stage"] == "planned":
        if raw_container(r["spec"]["container"]) is not None:
            raise AdminError("Cannot cancel a taken candidate name")
        save(config, r, "released")
        return status(r)
    if r["stage"] not in {"created", "stopped"}:
        raise AdminError(
            "Release requires a never-started or verified clean stopped candidate"
        )
    cid = r["initial"]["id"]
    s = snapshot(r, p)
    if s["running"] or (r["stage"] == "created" and s != r["initial"]):
        raise AdminError("Candidate lifecycle changed before release")
    if r["stage"] == "stopped":
        t = {
            **p["source"],
            "container": cid,
            "data_volume": p["target"]["data_volume"],
            "source_owner": p["target"]["owner"],
            "label": p["target"]["label"],
        }
        if backups.checkpoint(t) != r["checkpoint"]:
            raise AdminError("Candidate clean stop changed")
    logs = backups.docker("logs", "--tail", "4000", cid)
    if len(logs.encode()) > r["policy"]["log_bytes"]:
        raise AdminError("Candidate logs exceed retention bound")
    r["release_logs"] = {
        "bytes": len(logs.encode()),
        "sha256": hashlib.sha256(logs.encode()).hexdigest(),
    }
    save(config, r, "release-requested")
    retained_logs(config, r, logs)
    backups.docker("rm", cid)
    return reconcile_release(config, r)


def execute(config, operation, action, environment=None):
    with backups.locked(config):
        r = read(config, operation)
        if action == "status" or (action == "release" and r["stage"] == "released"):
            return status(r)
        if action == "reconcile" and r["stage"] == "create-requested":
            return capture_created(config, r)
        p = current(config, r, r.get("initial", {}).get("id"))
        handler = {
            "reconcile": request_reconcile,
            "create": request_create,
            "start": request_start,
            "stop": request_stop,
            "release": request_release,
        }.get(action)
        if handler is None:
            raise AdminError("Unsupported candidate action")
        return handler(config, r, p, environment)
