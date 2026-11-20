"""Local operator CLI. Never imported or bundled by the player launcher."""

import contextlib
import getpass
import json
import os
import re
import tempfile
import tomllib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from omk.accounts.drasl import DraslClient, DraslError
from omk.labs.recovery.recovery_console import ConsoleConfig
from omk.observability.diagnostic_export import export_bundle
from omk.observability.diagnostics import BoundedLog, regular
from omk.observability.report_store import ReportStore
from omk.owner.owner_access import require_private
from omk.shared.fs import resolved


class AdminError(RuntimeError):
    """Fixed operator-facing error without request/response or credential contents."""


@dataclass(frozen=True)
class OperatorConfig:
    """Describe the private owner configuration and configured server profiles."""

    private: Path
    servers: dict[str, Path]
    auth_origin: str | None
    auth_file: Path
    reports_root: Path
    recovery_consoles: dict[str, ConsoleConfig] = field(default_factory=dict)


def _private_path(root: Path, value: str) -> Path:
    if not isinstance(value, str) or not value or len(value) > 500:
        raise AdminError("Invalid operator file path")
    path = root / value
    if resolved(path) != path.absolute() or not path.absolute().is_relative_to(root):
        raise AdminError(
            "Operator files must stay inside the private .omk-admin folder"
        )
    return path.absolute()


def load_operator_config(path: Path) -> OperatorConfig:
    path = path.absolute()
    if path.parent.name != ".omk-admin" or not regular(path, path.parent):
        raise AdminError("Use an explicit configuration file inside .omk-admin")
    private = resolved(path.parent)
    _require_private(private, directory=True)
    _require_private(path)
    with path.open("rb") as file:
        raw = file.read(65537)
    if len(raw) > 65536:
        raise AdminError("Operator configuration is too large")
    data = tomllib.loads(raw.decode("utf-8"))
    if data.get("schema") != 1 or set(data) - {"schema", "auth", "servers", "reports"}:
        raise AdminError("Invalid operator configuration schema")
    servers, consoles = {}, {}
    entries = data.get("servers", {})
    if not isinstance(entries, dict) or len(entries) > 100:
        raise AdminError("Invalid server allowlist")
    for name, entry in entries.items():
        if (
            not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,47}", name)
            or not isinstance(entry, dict)
            or set(entry) - {"root", "recovery"}
            or "root" not in entry
        ):
            raise AdminError("Invalid server allowlist entry")
        if not isinstance(entry["root"], str) or not entry["root"]:
            raise AdminError("Invalid server folder")
        folder = Path(entry["root"])
        servers[name] = resolved(folder if folder.is_absolute() else private / folder)
        if "recovery" in entry:
            consoles[name] = ConsoleConfig(**entry["recovery"])
            _private_path(private, consoles[name].credential_file)
    auth = data.get("auth", {})
    if not isinstance(auth, dict) or set(auth) - {"origin", "session_file"}:
        raise AdminError("Invalid operator authentication settings")
    origin = DraslClient(auth["origin"]).base_url if "origin" in auth else None
    reports = data.get("reports", {})
    if not isinstance(reports, dict) or set(reports) - {"root"}:
        raise AdminError("Invalid incident inbox settings")
    return OperatorConfig(
        private,
        servers,
        origin,
        _private_path(private, auth.get("session_file", "drasl-session.json")),
        _private_path(private, reports.get("root", "client-reports")),
        consoles,
    )


def _require_private(path, **options):
    try:
        require_private(path, **options)
    except OSError as error:
        raise AdminError(str(error)) from None


def _read_json(path: Path, root: Path):
    if not regular(path, root):
        raise AdminError("Private operator file is missing or linked")
    _require_private(root, directory=True)
    _require_private(path, secret=True)
    with path.open("rb") as file:
        data = file.read(65537)
    if len(data) > 65536:
        raise AdminError("Private operator file is too large")
    value = json.loads(data)
    if not isinstance(value, dict):
        raise AdminError("Invalid private operator file")
    return value


def _write_private(path: Path, root: Path, value: dict):
    _write_private_text(
        path, root, json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    )


def _write_private_text(path: Path, root: Path, value: str, *, newline=None):
    _private_path(root, str(path.relative_to(root)))
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    _require_private(root, directory=True)
    # A POSIX mode-700 root protects the existing internal journal hierarchy.
    # NTFS traverse bypass means new files also need a private inheritable DACL.
    if os.name == "nt" and path.parent != root:
        _require_private(path.parent, directory=True)
    fd, name = tempfile.mkstemp(prefix=".operator-", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline=newline) as file:
            file.write(value)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _client(config):
    if config.auth_origin is None:
        raise AdminError("Authentication origin is not configured")
    return DraslClient(config.auth_origin)


def _credential(config):
    value = _read_json(config.auth_file, config.private)
    token = value.get("api_token")
    if (
        value.get("schema") != 1
        or value.get("origin") != config.auth_origin
        or not isinstance(token, str)
        or not re.fullmatch(r"[A-Za-z0-9_.~-]{16,8192}", token)
    ):
        raise AdminError(
            "Invalid operator credential or authentication origin mismatch"
        )
    return token


def operator_login(config: OperatorConfig, username: str, password: str):
    client = _client(config)
    result = client.login(username, password)
    if (
        not isinstance(result, dict)
        or result.get("user", {}).get("isAdmin") is not True
    ):
        raise AdminError("This Drasl account is not an administrator")
    token = result.get("apiToken")
    if not isinstance(token, str) or not re.fullmatch(
        r"[A-Za-z0-9_.~-]{16,8192}", token
    ):
        raise AdminError("Invalid operator credential response")
    _write_private(
        config.auth_file,
        config.private,
        {"schema": 1, "origin": client.base_url, "api_token": token},
    )
    return {
        "ok": True,
        "credential_file": str(config.auth_file),
        "password_saved": False,
    }


def _invite(value):
    if (
        not isinstance(value, dict)
        or not isinstance(value.get("code"), str)
        or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value["code"])
    ):
        raise AdminError("Invalid invitation response")
    return {"code": value["code"], "created_at": str(value.get("createdAt", ""))[:100]}


def create_invite(config: OperatorConfig):
    client, token = _client(config), _credential(config)
    invite = _invite(client.request("POST", "/drasl/api/v3/invites", {}, token))
    path = config.private / "invitations" / ("invite-" + uuid4().hex + ".json")
    try:
        _write_private(
            path, config.private, {"schema": 1, "origin": client.base_url, **invite}
        )
    except OSError, AdminError:
        try:
            client.request(
                "DELETE", "/drasl/api/v3/invites/" + invite["code"], token=token
            )
        except Exception:
            raise AdminError(
                "Invitation save failed; check operator invitation inventory before retrying"
            ) from None
        raise AdminError(
            "Invitation save failed; the new invitation was revoked"
        ) from None
    return {"ok": True, "invitation_file": str(path), "single_use": True}


def list_invites(config: OperatorConfig):
    client, token = _client(config), _credential(config)
    values = client.request("GET", "/drasl/api/v3/invites", token=token)
    if not isinstance(values, list) or len(values) > 1000:
        raise AdminError("Invalid invitation inventory response")
    path = config.private / "invitations/inventory.json"
    _write_private(
        path,
        config.private,
        {
            "schema": 1,
            "origin": client.base_url,
            "invites": [_invite(v) for v in values],
        },
    )
    return {"ok": True, "inventory_file": str(path), "count": len(values)}


def revoke_invite(config: OperatorConfig, file: Path):
    file = _private_path(
        config.private, str(file.absolute().relative_to(config.private))
    )
    value = _read_json(file, config.private)
    if value.get("origin") != config.auth_origin or value.get("schema") != 1:
        raise AdminError("Invitation origin mismatch")
    code = _invite(value)["code"]
    try:
        _client(config).request(
            "DELETE", "/drasl/api/v3/invites/" + code, token=_credential(config)
        )
    except DraslError as error:
        if error.status == 404:
            raise AdminError(
                "Invitation was already used, revoked or not found; no account was blocked"
            ) from None
        raise
    _write_private(file, config.private, {**value, "revoked": True})
    return {"ok": True, "invitation_file": str(file), "revoked": True}


def server_diagnostics(config: OperatorConfig, server_id: str):
    if server_id not in config.servers:
        raise AdminError("Server is not in the operator allowlist")
    source = config.servers[server_id]
    if not source.is_dir():
        raise AdminError("Configured server folder is missing")
    return export_bundle(config.private, server_id, server_root=source)


def client_reports(config, args):
    store = ReportStore(config.reports_root)
    if args.reports_action == "list":
        player = UUID(args.player).hex if args.player else None
        values = store.list(player=player)
        path = config.private / "client-report-inventory.json"
        _write_private(path, config.private, {"reports": values})
        return {"ok": True, "inventory_file": str(path), "count": len(values)}
    if args.reports_action == "prune":
        store.prune()
        return {"ok": True, "expired_reports_pruned": True}
    if re.fullmatch(r"[a-f0-9]{32}", args.report_id) is None:
        raise AdminError("Invalid report identifier")
    path = config.private / "report-exports" / (args.report_id + ".json")
    _write_private(path, config.private, store.get(args.report_id))
    return {"ok": True, "report_file": str(path)}


def _console_server(value):
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,47}", value):
        raise ValueError("Invalid server identifier")
    return value


def _add_tps_history_parser(actions):
    history = actions.add_parser("tps-history", help="Read-only bounded TPS history")
    history.add_argument("--server", required=True, type=_console_server)
    history.add_argument("--window", choices=("5m", "15m", "1h", "3h"), default="5m")


def _add_tui_operation_parsers(actions):
    moderation = actions.add_parser("moderation", help="Owner online-player moderation")
    moderation.add_argument("--server", required=True, type=_console_server)
    moderation.add_argument(
        "--command",
        dest="moderation_command",
        required=True,
        choices=["kick", "ban", "mute", "unban"],
    )
    moderation.add_argument("--player", required=True)
    moderation.add_argument("--duration", default="")
    moderation.add_argument("--reason", default="")
    moderation.add_argument("--confirm-ban", action="store_true")
    project = actions.add_parser("project-moderation", help="Project-wide moderation")
    project.add_argument(
        "--command",
        required=True,
        dest="moderation_command",
        choices=["init", "ban", "mute", "unban"],
    )
    project.add_argument("--player", default="")
    project.add_argument("--duration", default="")
    project.add_argument("--reason", default="")
    project.add_argument("--confirm-ban", action="store_true")
    world_reset = actions.add_parser(
        "world-reset", help="Manual staged resource-world reset for the owner TUI"
    )
    world_reset.add_argument("--server", type=_console_server, required=True)
    world_reset.add_argument(
        "--command",
        dest="world_reset_command",
        choices=("inspect", "prepare", "apply", "start"),
        required=True,
    )
    world_reset.add_argument("--confirm", default="")


def add_admin_commands(sub):
    from omk.accounts.account_recovery import add_recovery_parser  # noqa: PLC0415
    from omk.deployment.ingress import add_parser as add_ingress_parser  # noqa: PLC0415
    from omk.owner.admin_backups import add_backup_parser  # noqa: PLC0415
    from omk.owner.admin_maintenance import add_maintenance_parser  # noqa: PLC0415
    from omk.owner.admin_nightly import (  # noqa: PLC0415
        add_parser as add_nightly_parser,
    )
    from omk.owner.admin_resource_reset import (  # noqa: PLC0415
        add_resource_reset_parser,
    )
    from omk.owner.admin_restores import add_restore_parser  # noqa: PLC0415
    from omk.owner.admin_storage import (  # noqa: PLC0415
        add_parser as add_storage_parser,
    )
    from omk.worlds.world_cutover import (  # noqa: PLC0415
        add_parser as add_cutover_parser,
    )

    admin = sub.add_parser(
        "admin", help="Local operator tools; not part of the player launcher"
    )
    admin.add_argument("--config", type=Path, required=True)
    admin.add_argument(
        "--result-version",
        type=int,
        choices=[1],
        help="Opt into the versioned backup/restore/maintenance result contract",
    )
    actions = admin.add_subparsers(dest="admin_action", required=True)
    overview = actions.add_parser(
        "overview", help="Read-only owner TUI overview (separate schema)"
    )
    overview.add_argument("--server", type=_console_server)
    _add_tps_history_parser(actions)
    console = actions.add_parser("console", help="Fixed owner RCON commands")
    console.add_argument("--server", required=True, type=_console_server)
    console.add_argument(
        "--command",
        dest="console_command",
        required=True,
        choices=["players", "tps", "save"],
    )
    console.add_argument("--confirm-save", action="store_true")
    _add_tui_operation_parsers(actions)
    add_recovery_parser(actions)
    add_backup_parser(actions)
    add_maintenance_parser(actions)
    add_restore_parser(actions)
    add_resource_reset_parser(actions)
    add_ingress_parser(actions)
    add_cutover_parser(actions)
    add_storage_parser(actions)
    add_nightly_parser(actions)
    login = actions.add_parser(
        "login", help="Save a separate Drasl operator API credential"
    )
    login.add_argument("--username", required=True)
    diagnostics = actions.add_parser(
        "diagnostics", help="Read-only server diagnostic export"
    )
    diagnostics.add_argument("server")
    playtime = actions.add_parser(
        "playtime", help="Read saved server play ticks by account UUID"
    )
    playtime.add_argument("server")
    playtime.add_argument("player", help="Minecraft account UUID, not a nickname")
    reports = actions.add_parser(
        "reports", help="Read the private local client incident inbox"
    )
    report_actions = reports.add_subparsers(dest="reports_action", required=True)
    listing = report_actions.add_parser("list")
    listing.add_argument("--player", help="Optional Minecraft UUID")
    exporting = report_actions.add_parser("export")
    exporting.add_argument("--id", dest="report_id", required=True)
    report_actions.add_parser("prune")
    access = actions.add_parser(
        "access", help="Registration invitations, not Minecraft OP"
    )
    invites = access.add_subparsers(dest="access_action", required=True)
    invites.add_parser("invite")
    invites.add_parser("invites")
    revoke = invites.add_parser("revoke-invite")
    revoke.add_argument("--invitation-file", type=Path, required=True)


def run_admission(config, args):
    from omk.deployment.ingress import run as run_ingress  # noqa: PLC0415
    from omk.owner.admin_nightly import run as run_nightly  # noqa: PLC0415
    from omk.owner.admin_storage import run as run_storage  # noqa: PLC0415
    from omk.worlds.world_cutover import run as run_cutover  # noqa: PLC0415

    return {
        "ingress": run_ingress,
        "world-cutovers": run_cutover,
        "storage": run_storage,
        "nightly": run_nightly,
    }[args.admin_action](config, args)


def _execute_admin(config, args):
    if args.admin_action == "login":
        result = operator_login(
            config, args.username, getpass.getpass("Drasl administrator password: ")
        )
    elif args.admin_action in {"diagnostics", "playtime"}:
        from omk.game.player_time import saved_playtime  # noqa: PLC0415

        result = {
            "diagnostics": lambda: server_diagnostics(config, args.server),
            "playtime": lambda: saved_playtime(config, args.server, args.player),
        }[args.admin_action]()
    elif args.admin_action == "reports":
        result = client_reports(config, args)
    elif args.admin_action == "recover-account":
        from omk.accounts.account_recovery import run_recovery  # noqa: PLC0415

        result = run_recovery(config, args)
    elif args.admin_action == "resource-resets":
        from omk.owner.admin_resource_reset import run_resource_reset  # noqa: PLC0415

        result = run_resource_reset(config, args)
    elif args.admin_action == "maintenance":
        from omk.owner.admin_maintenance import run_maintenance  # noqa: PLC0415

        result = run_maintenance(config, args)
    elif args.admin_action in {"ingress", "world-cutovers", "storage", "nightly"}:
        result = run_admission(config, args)
    elif args.admin_action in {"backups", "restores"}:
        from omk.owner.admin_backups import run_backups  # noqa: PLC0415
        from omk.owner.admin_restores import run_restores  # noqa: PLC0415

        result = {"backups": run_backups, "restores": run_restores}[args.admin_action](
            config, args
        )
    else:
        result = {
            "invite": lambda: create_invite(config),
            "invites": lambda: list_invites(config),
            "revoke-invite": lambda: revoke_invite(config, args.invitation_file),
        }[args.access_action]()
    return result


def run_admin(args):
    if args.admin_action == "world-reset" and args.result_version is None:
        from omk.owner.panels.owner_world_reset import run  # noqa: PLC0415

        return run(args.config, args.server, args.world_reset_command, args.confirm)
    if args.admin_action == "project-moderation" and args.result_version is None:
        from omk.game.project_moderation import run  # noqa: PLC0415

        return run(
            args.config,
            args.moderation_command,
            args.player,
            duration=args.duration,
            reason=args.reason,
            confirmed=args.confirm_ban,
        )
    if args.admin_action == "moderation" and args.result_version is None:
        from omk.owner.panels.owner_moderation import run  # noqa: PLC0415

        return run(
            args.config,
            args.server,
            args.moderation_command,
            args.player,
            duration=args.duration,
            reason=args.reason,
            confirmed=args.confirm_ban,
        )
    if args.admin_action == "tps-history" and args.result_version is None:
        from omk.owner.panels.owner_tps_history import run  # noqa: PLC0415

        return run(args.config, args.server, args.window)
    if args.admin_action == "console" and args.result_version is None:
        from omk.owner.panels.owner_console import run  # noqa: PLC0415

        return run(
            args.config, args.server, args.console_command, confirmed=args.confirm_save
        )
    if args.admin_action == "overview" and args.result_version is None:
        from omk.owner.panels.owner_overview import run  # noqa: PLC0415

        return run(args.config, args.server)
    config = None
    operation = args.admin_action
    suffix = {
        "access": "access_action",
        "reports": "reports_action",
        "recover-account": "recovery_action",
        "backups": "backup_action",
        "maintenance": "maintenance_action",
        "restores": "restore_action",
        "resource-resets": "resource_reset_action",
        "ingress": "ingress_action",
        "world-cutovers": "cutover_action",
        "storage": "storage_action",
        "nightly": "nightly_action",
    }.get(args.admin_action)
    if suffix:
        operation += ":" + getattr(args, suffix)
    versioned = getattr(args, "result_version", None) == 1
    if versioned:
        from omk.owner import owner_result  # noqa: PLC0415

        action = operation.replace(":", ".")
        if action not in owner_result.SUPPORTED:
            return owner_result.failure(action, args, "unsupported_action")
    caught_error = None
    try:
        config = load_operator_config(args.config)
        result = _execute_admin(config, args)
    except Exception as error:
        caught_error = error
        result = {
            "ok": False,
            "error": (
                str(error)
                if isinstance(error, AdminError)
                else "Operator operation failed; check configuration, permissions and service availability"
            ),
            "error_type": type(error).__name__,
        }
    if versioned:
        result = owner_result.project(
            action, args, result, error=caught_error, configuring=config is None
        )
    if config is not None:
        with contextlib.suppress(OSError):
            BoundedLog(config.private / "audit.jsonl", limit=1024**2).write(
                json.dumps(
                    {
                        "time": datetime.now(UTC).isoformat(),
                        "operation": operation,
                        "ok": result["ok"],
                    }
                )
                + "\n"
            )
    return result
