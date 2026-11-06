"""Existing FTB command/claim scenarios in a fresh, owned Linux Docker world."""

import hashlib
import json
from pathlib import Path
from uuid import UUID, uuid4

from omk.dj2_commands_lab import run_command_checks
from omk.dj2_lab import (
    _accounts,
    _catalog_report,
    _console_sender,
    _copy_server,
    _protocol_tests,
    _wait_server,
    approved_mods,
)
from omk.dj2_linux_lab import JAVA_IMAGE, LinuxServer, inspect_owned
from omk.mod_components import add_pack_inputs
from omk.operator_lab import _cleanup
from omk.profiles import PROJECT_ROOT

SUITES = ("claim-edges", "explosions")
# Reviewed 2.23.4 startup catalog is 2,551,543 bytes (registered mod permissions).
CATALOG_LIMIT = 4 * 1024**2


def add_linux_runtime_inputs(parser):
    add_pack_inputs(parser)
    for name in ("server-source", "agent", "core", "mods-json"):
        parser.add_argument("--" + name, type=Path, required=True)


def add_claim_regression_lab(parser):
    add_linux_runtime_inputs(parser)
    parser.add_argument("--suite", choices=(*SUITES, "all"), default="all")


def _validate(args):
    if args.suite not in (*SUITES, "all"):
        raise ValueError("Unknown Linux claim suite")
    validate_linux_runtime_inputs(args)


def validate_linux_runtime_inputs(args):
    for path in (
        args.agent,
        args.core,
        args.mods_json,
        args.server_source / "forge-1.12.2-14.23.5.2860.jar",
    ):
        if not path.is_file():
            raise ValueError("Required Linux claim lab input missing")
    approved_mods(args.mods_json)


def _catalog(server, dest):
    if inspect_owned("volume", server.volume, server.run_id) is None:
        raise ValueError("Claim lab volume missing")
    raw = server.helper(
        f"head -c {CATALOG_LIMIT + 1} /srv/omk-command-catalog.json",
        readonly_volume=True,
    ).stdout
    if len(raw.encode("utf-8")) > CATALOG_LIMIT:
        raise ValueError("Claim lab catalog too large")
    metadata = json.loads(raw)
    if not isinstance(metadata, dict):
        raise ValueError("Invalid claim lab catalog")
    # Read only the startup catalog, not running world/player data. The existing
    # common guard validator receives the same bytes as on the native runtime.
    with (dest / "omk-command-catalog.json").open("x", encoding="utf-8") as out:
        out.write(raw)


def _artifact_hashes(args, dest):
    paths = [
        args.core,
        args.agent,
        *(
            dest / "mods" / name
            for name in (
                "FTBUtilities-5.4.1.131.jar",
                "FTBLib-5.4.7.2.jar",
                "ironchest-1.12.2-7.0.72.847.jar",
            )
        ),
        dest / "forge-1.12.2-14.23.5.2860.jar",
    ]
    if getattr(args, "pack_fix", None) is not None:
        paths.append(args.pack_fix)
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def _finish(server, compose, report):
    try:
        server.close(report)
    except Exception as error:
        report["server_cleanup_error_type"] = type(error).__name__
        report["ok"] = False
    try:
        report["temporary_auth_removed"] = _cleanup(None, None, compose)
    except Exception as error:
        report["auth_cleanup_error_type"] = type(error).__name__
        report["temporary_auth_removed"] = False
    report["ok"] = (
        report["ok"]
        and report.get("owned_game_clean_exit", False)
        and report["temporary_auth_removed"]
    )


def run_claim_regression_lab(args):
    _validate(args)
    run_id = uuid4().hex[:10]
    lab = PROJECT_ROOT / ".local" / ("claim-regression-" + run_id)
    lab.mkdir()
    project = "omk-claims-" + run_id
    compose = [
        "docker",
        "compose",
        "--project-name",
        project,
        "-f",
        str(PROJECT_ROOT / "deploy/auth-lab/compose.yaml"),
    ]
    server = LinuxServer(lab, run_id, project + "_default")
    report = {
        "ok": False,
        "checks": [],
        "lab": lab.relative_to(PROJECT_ROOT).as_posix(),
        "suites": list(SUITES) if args.suite == "all" else [args.suite],
        "linux_java_image": JAVA_IMAGE,
        "graphical_client": False,
    }

    def state(phase):
        (lab / "status.json").write_text(
            json.dumps({"phase": phase, "checks": len(report["checks"])}),
            encoding="utf-8",
        )

    def expect(ok, label):
        if not ok:
            raise RuntimeError(label)
        report["checks"].append(label)
        state(label)

    try:
        state("preparing_fresh_owned_claim_lab")
        dest, mods = _copy_server(args, lab)
        report["artifact_sha256"] = _artifact_hashes(args, dest)
        client, _, first, second = _accounts(compose, lab)
        report["java_runtime"] = server.prepare(dest, args, client)
        process = server.start()
        _wait_server(process, server.log, state)
        _catalog(server, dest)
        _catalog_report(dest, report, True, expect, True)
        console = _console_sender(process, server.log)
        ops = json.loads(
            server.helper("cat /srv/ops.json", readonly_volume=True).stdout
        )
        actor_ids = {UUID(s.player_uuid) for s in (first, second)}
        expect(
            all(UUID(row["uuid"]) not in actor_ids for row in ops),
            "neither_authenticated_actor_is_an_operator",
        )
        report["service_operator_count"] = len(ops)
        _protocol_tests(client, first, second, mods, process, server.log, expect)
        for suite in report["suites"]:
            state("running_" + suite)
            restart = run_command_checks(
                client,
                first,
                second,
                mods,
                console,
                expect,
                report,
                suite=suite,
                mute_guard=True,
                claim_guard=True,
            )
            if restart:
                raise RuntimeError("Unexpected restart requested by claim suite")
        report["ok"] = True
    except Exception as error:
        report["error_type"] = type(error).__name__
        report["error"] = (
            str(error)[:1800]
            if isinstance(error, (RuntimeError, ValueError))
            else "Claim lab failed; inspect isolated data"
        )
    finally:
        _finish(server, compose, report)
        state("complete" if report["ok"] else "failed")
        (lab / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
