"""Actual child exit during password delivery in the owned recovery fixture only."""

import json
import subprocess
import sys

from omk.account_recovery import execute, prepare, status
from omk.dj2_commands_lab import FIRST
from omk.forge_player import LabPlayer
from omk.profiles import PROJECT_ROOT


def abrupt_exit(cfg, accounts, mods, expect, report):
    plan = prepare(cfg, FIRST)
    path = cfg.private / "operator.toml"
    path.write_text(
        "schema=1\n[auth]\norigin="
        + json.dumps(cfg.auth_origin)
        + "\n[servers.dj2]\nroot="
        + json.dumps(str(cfg.servers["dj2"]))
        + '\n[servers.dj2.recovery]\nadapter="omk-core112-rcon-v1"\n'
        + f'port={cfg.recovery_consoles["dj2"].port}\ncredential_file="rcon.json"\n',
        encoding="utf-8",
    )
    path.chmod(0o600)
    previous = accounts.services[0].store.load()
    child = subprocess.run(
        [
            sys.executable,
            "-c",
            "import os,sys; from pathlib import Path; from omk.admin import load_operator_config; "
            "from omk.account_recovery import execute; "
            "execute(load_operator_config(Path(sys.argv[1])),sys.argv[2],emit=lambda _:os._exit(73))",
            str(path),
            plan["account"],
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        timeout=60,
        check=False,
    )
    expect(
        child.returncode == 73 and not child.stdout and not child.stderr,
        "owner_child_exits_without_secret_output_or_finally",
    )
    journal = status(cfg, plan["account"])["recovery"]
    expect(
        journal["stage"] == "password_delivery",
        "owner_abrupt_exit_preserves_incomplete_journal_stage",
    )
    delivered = []
    try:
        execute(cfg, plan["account"], emit=delivered.append)
    except Exception:
        expect(not delivered, "owner_abrupt_exit_requires_explicit_resume")
    else:
        raise RuntimeError("owner_abrupt_exit_was_silently_retried")
    result = execute(cfg, plan["account"], resume=True, emit=delivered.append)
    expect(
        result["ok"] and len(delivered) == 1,
        "owner_resume_releases_process_lock_and_delivers_fresh_password",
    )
    expect(
        status(cfg, plan["account"])["recovery"]["attempt"] == 2,
        "owner_resume_records_second_attempt",
    )
    from omk.dj2_account_recovery_lab import _invalid_sessions  # noqa: PLC0415

    _invalid_sessions(accounts, [previous], expect, "owner_after_abrupt_exit")
    final = accounts.services[0].login(FIRST, delivered[0]).session
    with LabPlayer(accounts.client, final, 25576, mods) as player:
        expect(
            player.dimension == 0,
            "owner_after_abrupt_exit_resume_real_forge_login_succeeds",
        )
    report["abrupt_exit_code"] = child.returncode
