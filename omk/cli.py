"""A small operations entry point; destructive world operations are not implemented."""

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from api.settings.content import get_instance_config, get_launcher_manifest_settings
from launcher.paths import default_data_dir
from omk.admin import add_admin_commands, run_admin
from omk.client_crash_lab import add_client_crash_lab
from omk.dj2_lab import add_dj2_lab, run_dj2_lab
from omk.dj2_linux_lab import add_linux_skin_lab, run_linux_skin_lab
from omk.lab import auth_smoke
from omk.profiles import PROJECT_ROOT, load_profiles
from omk.release_cli import add_release_commands, prepare_release


def doctor() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    checks.append(
        {
            "name": "python",
            "ok": sys.version_info >= (3, 14),
            "detail": sys.version.split()[0],
        }
    )
    try:
        profiles = load_profiles()
        checks.append(
            {"name": "server_profiles", "ok": True, "detail": [p.id for p in profiles]}
        )
    except OSError, ValueError, KeyError, TypeError:
        checks.append({"name": "server_profiles", "ok": False})
    try:
        get_launcher_manifest_settings()
        get_instance_config("divinejourney2")
        checks.append({"name": "content_settings", "ok": True})
    except OSError, ValueError:
        checks.append({"name": "content_settings", "ok": False})
    docker = shutil.which("docker")
    available = False
    if docker:
        try:
            result = subprocess.run(
                [docker, "version", "--format", "{{.Server.Version}}"],
                capture_output=True,
                text=True,
                timeout=8,
                check=False,
            )
            available = result.returncode == 0
        except OSError, subprocess.SubprocessError:
            pass
    checks.append({"name": "docker_engine", "ok": available})
    checks.append(
        {
            "name": "auth_lab_config",
            "ok": (PROJECT_ROOT / "deploy/auth-lab/compose.yaml").is_file(),
        }
    )
    return {"ok": all(check["ok"] for check in checks), "checks": checks}


def _add_launcher_parser(sub):
    launcher = sub.add_parser("launcher", help="Open the desktop account prototype")
    launcher.add_argument(
        "--auth-url",
        required=True,
        help="Trusted Drasl origin (HTTPS outside loopback)",
    )
    launcher.add_argument("--data-dir", type=Path, default=default_data_dir())
    launcher.add_argument("--api-url", help="Signed release CDN origin")
    launcher.add_argument("--root", type=Path, help="Portable launcher folder")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="omk", description="OmkalityCraft development and operations tools"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    add_release_commands(sub)
    add_admin_commands(sub)
    sub.add_parser("doctor", help="Check local development prerequisites (read-only)")
    _add_launcher_parser(sub)
    server = sub.add_parser("server", help="Inspect configured server profiles")
    server.add_subparsers(dest="action", required=True).add_parser("list")
    lab = sub.add_parser("lab", help="Disposable integration tests")
    lab_areas = lab.add_subparsers(dest="area", required=True)
    from omk.recovery_lab import add_recovery_lab  # noqa: PLC0415

    add_recovery_lab(
        lab_areas.add_parser(
            "dj2-recovery", help="Fresh Forge WorldEdit snapshot experiment"
        )
    )
    lab_admin = lab_areas.add_parser(
        "admin", help="Disposable operator CLI and client crash inbox"
    )
    lab_admin.add_subparsers(dest="action", required=True).add_parser("smoke")
    add_dj2_lab(
        lab_areas.add_parser(
            "dj2", help="Fresh isolated Forge/FTB/Core integration lab"
        )
    )
    add_linux_skin_lab(
        lab_areas.add_parser(
            "dj2-linux", help="Disposable Linux Docker Forge and desktop skin check"
        )
    )
    add_client_crash_lab(
        lab_areas.add_parser(
            "client-crash",
            help="Real graphical DJ2 crash and private incident delivery lab",
        )
    )
    lab_auth = lab_areas.add_parser("auth")
    lab_auth_actions = lab_auth.add_subparsers(dest="action", required=True)
    lab_auth_actions.add_parser("smoke")
    lab_auth_actions.add_parser(
        "expiry", help="Verify a genuinely expired game session"
    )
    lab_launcher = lab_areas.add_parser(
        "launcher", help="Real Qt UI with disposable Drasl accounts"
    )
    lab_launcher.add_subparsers(dest="action", required=True).add_parser("smoke")
    args = parser.parse_args(argv)
    if args.command == "launcher":
        from launcher.app import run_launcher  # noqa: PLC0415 - optional Qt dependency

        return run_launcher(
            args.auth_url, args.data_dir, api_url=args.api_url, root=args.root
        )
    if args.command == "release":
        report = prepare_release(args)
    elif args.command == "admin":
        report = run_admin(args)
    elif args.command == "doctor":
        report = doctor()
    elif args.command == "server":
        report = {"ok": True, "servers": [p.as_dict() for p in load_profiles()]}
    elif args.area == "dj2-recovery":
        from omk.recovery_lab import run_recovery_lab  # noqa: PLC0415

        report = run_recovery_lab(args)
    elif args.area == "dj2-linux":
        report = run_linux_skin_lab(args)
    elif args.area == "client-crash":
        from omk.client_crash_lab import run_client_crash_lab  # noqa: PLC0415

        report = run_client_crash_lab(args)
    elif args.area == "dj2":
        report = run_dj2_lab(args)
    elif args.area == "admin":
        from omk.operator_lab import operator_smoke  # noqa: PLC0415

        report = operator_smoke()
    else:
        report = auth_smoke(
            with_gui=args.area == "launcher", expiry_only=args.action == "expiry"
        )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1
