"""Local operator CLI. Never imported or bundled by the player launcher."""

import contextlib
import getpass
import json
import os
import re
import tempfile
import tomllib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from omk.diagnostic_export import export_bundle
from omk.diagnostics import BoundedLog, regular
from omk.drasl import DraslClient
from omk.fs import resolved
from omk.report_store import ReportStore


class AdminError(RuntimeError):
    """Fixed operator-facing error without request/response or credential contents."""


@dataclass(frozen=True)
class OperatorConfig:
    private: Path
    servers: dict[str, Path]
    auth_origin: str | None
    auth_file: Path
    reports_root: Path


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
    if os.name != "nt" and private.stat().st_mode & 0o077:
        raise AdminError("The private operator directory requires mode 700")
    with path.open("rb") as file:
        raw = file.read(65537)
    if len(raw) > 65536:
        raise AdminError("Operator configuration is too large")
    data = tomllib.loads(raw.decode("utf-8"))
    if data.get("schema") != 1 or set(data) - {"schema", "auth", "servers", "reports"}:
        raise AdminError("Invalid operator configuration schema")
    servers = {}
    entries = data.get("servers", {})
    if not isinstance(entries, dict) or len(entries) > 100:
        raise AdminError("Invalid server allowlist")
    for name, entry in entries.items():
        if (
            not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,47}", name)
            or not isinstance(entry, dict)
            or set(entry) != {"root"}
        ):
            raise AdminError("Invalid server allowlist entry")
        if not isinstance(entry["root"], str) or not entry["root"]:
            raise AdminError("Invalid server folder")
        folder = Path(entry["root"])
        servers[name] = resolved(folder if folder.is_absolute() else private / folder)
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
    )


def _read_json(path: Path, root: Path):
    if not regular(path, root):
        raise AdminError("Private operator file is missing or linked")
    if os.name != "nt" and path.stat().st_mode & 0o077:
        raise AdminError(
            "Operator credentials must be readable only by their owner (mode 600)"
        )
    with path.open("rb") as file:
        data = file.read(65537)
    if len(data) > 65536:
        raise AdminError("Private operator file is too large")
    value = json.loads(data)
    if not isinstance(value, dict):
        raise AdminError("Invalid private operator file")
    return value


def _write_private(path: Path, root: Path, value: dict):
    _private_path(root, str(path.relative_to(root)))
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, name = tempfile.mkstemp(prefix=".operator-", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            file.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
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
    except OSError:
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
    _client(config).request(
        "DELETE", "/drasl/api/v3/invites/" + code, token=_credential(config)
    )
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


def add_admin_commands(sub):
    admin = sub.add_parser(
        "admin", help="Local operator tools; not part of the player launcher"
    )
    admin.add_argument("--config", type=Path, required=True)
    actions = admin.add_subparsers(dest="admin_action", required=True)
    login = actions.add_parser(
        "login", help="Save a separate Drasl operator API credential"
    )
    login.add_argument("--username", required=True)
    diagnostics = actions.add_parser(
        "diagnostics", help="Read-only server diagnostic export"
    )
    diagnostics.add_argument("server")
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


def run_admin(args):
    config = None
    operation = args.admin_action + (
        ":" + args.access_action if args.admin_action == "access" else ""
    )
    if args.admin_action == "reports":
        operation += ":" + args.reports_action
    try:
        config = load_operator_config(args.config)
        if args.admin_action == "login":
            result = operator_login(
                config, args.username, getpass.getpass("Drasl administrator password: ")
            )
        elif args.admin_action == "diagnostics":
            result = server_diagnostics(config, args.server)
        elif args.admin_action == "reports":
            result = client_reports(config, args)
        else:
            result = {
                "invite": lambda: create_invite(config),
                "invites": lambda: list_invites(config),
                "revoke-invite": lambda: revoke_invite(config, args.invitation_file),
            }[args.access_action]()
    except Exception as error:
        result = {
            "ok": False,
            "error": (
                str(error)
                if isinstance(error, AdminError)
                else "Operator operation failed; check configuration, permissions and service availability"
            ),
            "error_type": type(error).__name__,
        }
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
