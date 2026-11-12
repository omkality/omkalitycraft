"""Owner calendar, readonly preflight and an explicit recoverable backup cycle."""

import json
import os
import sys
import tomllib
from uuid import uuid4

from omk import (
    admin_backups as backups,
    admin_maintenance as maintenance,
)
from omk.admin import AdminError
from omk.diagnostics import regular
from omk.ftb_backup_policy import ADAPTER, SHA256
from omk.nightly_policy import next_window, settings


def adapter(config, server):
    path = config.private / "nightly.toml"
    if not regular(path, config.private) or (
        os.name != "nt" and path.stat().st_mode & 0o077
    ):
        raise AdminError("Use a private mode-600 .omk-admin/nightly.toml")
    with path.open("rb") as stream:
        raw = stream.read(16385)
    if len(raw) > 16384:
        raise AdminError("Nightly configuration exceeds limit")
    value = tomllib.loads(raw.decode())
    if (
        set(value) != {"schema", "servers"}
        or type(value["schema"]) is not int
        or value["schema"] != 1
        or not isinstance(value["servers"], dict)
        or not 1 <= len(value["servers"]) <= 16
        or set(value["servers"]) - set(config.servers)
        or server not in value["servers"]
        or any(entry != {"adapter": ADAPTER} for entry in value["servers"].values())
    ):
        raise AdminError("Invalid nightly server allowlist or unreviewed adapter")
    return value["servers"][server]["adapter"]


def inspect(config, server, environment=None, *, now=None):
    policy = settings(environment)
    calendar = next_window(policy, now)
    with backups.locked(config):
        expected_adapter = adapter(config, server)
        target, binding = backups.target_for(config, server), maintenance.binding(
            config, server
        )
        backups.local_engine()
        before = maintenance.snapshot(target, binding)
        proof = maintenance.worker(
            {"operation": uuid4().hex, "target": target, "binding": binding},
            "nightly-policy",
        )
        expected_keys = {
            "adapter",
            "artifact_sha256",
            "config_sha256",
            "runtime_sha256",
            "stock_enabled_on_disk",
            "stock_shutdown_on_disk",
            "live_config_verified",
            "other_writers_verified",
        }
        if (
            set(proof) != expected_keys
            or proof["adapter"] != expected_adapter
            or proof["artifact_sha256"] != SHA256
            or any(
                proof[key] is not False
                for key in (
                    "stock_enabled_on_disk",
                    "stock_shutdown_on_disk",
                    "live_config_verified",
                    "other_writers_verified",
                )
            )
            or any(
                not isinstance(proof[key], str)
                or len(proof[key]) != 64
                or any(c not in "0123456789abcdef" for c in proof[key])
                for key in ("runtime_sha256", "config_sha256")
            )
        ):
            raise AdminError("Invalid nightly disk-policy proof")
        if (
            adapter(config, server) != expected_adapter
            or backups.target_for(config, server) != target
            or maintenance.binding(config, server) != binding
            or maintenance.snapshot(target, binding) != before
        ):
            raise AdminError("Nightly target changed during inspection")
        return {
            "ok": True,
            "server": server,
            "mode": "read_only_preflight",
            "source_running": before["running"],
            "disk_policy": proof,
            "policy": policy,
            "next_window": calendar,
            "scheduler_implemented": True,
            "scheduler_enabled": False,
            "activation_approved": False,
            "ready_for_players": False,
        }


def add_parser(actions):
    parser = actions.add_parser(
        "nightly", help="Owner nightly preview, preflight and explicit backup/restart"
    )
    sub = parser.add_subparsers(dest="nightly_action", required=True)
    sub.add_parser("preview")
    sub.add_parser("inspect").add_argument("--server", required=True)
    command = sub.add_parser(
        "run",
        help="One explicit warning/backup/restart cycle, or recovery of the same operation",
    )
    target = command.add_mutually_exclusive_group(required=True)
    target.add_argument("--server")
    target.add_argument("--operation")
    target = sub.add_parser("status").add_mutually_exclusive_group(required=True)
    target.add_argument("--operation")
    target.add_argument("--server")
    sub.add_parser("cancel").add_argument("--operation", required=True)
    sub.add_parser(
        "watch", help="Opt-in calendar service; does not install a host job"
    ).add_argument("--server", required=True)


def run(config, args):
    if args.nightly_action == "watch" or (
        args.nightly_action == "status" and args.server
    ):
        from omk import nightly_schedule as schedule  # noqa: PLC0415

        if args.nightly_action == "status":
            return schedule.status(config, args.server)
        return schedule.watch(
            config,
            args.server,
            notify=lambda v: print(json.dumps(v), file=sys.stderr, flush=True),
        )
    if args.nightly_action in {"run", "status", "cancel"}:
        from omk import nightly_cycle as cycle  # noqa: PLC0415

        if args.nightly_action == "status":
            return cycle.status(cycle.read(config, args.operation))
        if args.nightly_action == "cancel":
            return cycle.cancel(config, args.operation)
        operation = args.operation or cycle.prepare(config, args.server)["operation"]
        print("Nightly operation: " + operation, file=sys.stderr, flush=True)
        try:
            return cycle.run(config, operation=operation)
        except Exception as error:
            return {
                **cycle.status(cycle.read(config, operation)),
                "ok": False,
                "error": (
                    str(error)
                    if isinstance(error, AdminError)
                    else "Nightly interrupted; inspect and resume the recorded operation"
                ),
                "error_type": type(error).__name__,
            }
    if args.nightly_action == "inspect":
        return inspect(config, args.server)
    policy = settings()
    return {
        "ok": True,
        "mode": "calendar_preview",
        "policy": policy,
        "next_window": next_window(policy),
        "scheduler_enabled": False,
        "activation_approved": False,
    }
