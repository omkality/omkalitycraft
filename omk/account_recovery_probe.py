"""Exercise owner recovery only inside the explicit disposable Linux DJ2 lab."""

import contextlib
import json
import secrets
import socket
import time
from uuid import UUID

from omk.account_recovery import execute, prepare, status
from omk.account_recovery_abort_lab import abrupt_exit
from omk.admin import OperatorConfig, _write_private
from omk.dj2_commands_lab import FIRST
from omk.dj2_linux_lab import JAVA_IMAGE, LinuxServer
from omk.forge_player import LabPlayer
from omk.recovery_console import ConsoleConfig, RecoveryConsole


class RecoveryServer(LinuxServer):
    def __init__(self, *args, rcon_port):
        super().__init__(*args)
        if not 1024 <= rcon_port <= 65535 or rcon_port in {25576, 25586}:
            raise ValueError("Invalid disposable recovery console port")
        with socket.socket() as check:
            check.bind(("127.0.0.1", rcon_port))
        self.rcon_port = rcon_port
        self.rcon_password = secrets.token_urlsafe(32)

    def prepare(self, dest, args, client):
        props = dest / "server.properties"
        lines = [
            line
            for line in props.read_text().splitlines()
            if not line.startswith(("enable-rcon=", "rcon.port=", "rcon.password="))
        ]
        props.write_text(
            "\n".join(lines)
            + "\nenable-rcon=true\n"
            + f"rcon.port={self.rcon_port}\nrcon.password={self.rcon_password}\n"
        )
        return super().prepare(dest, args, client)

    def command(self, **kwargs):
        command = super().command(**kwargs)
        index = command.index(JAVA_IMAGE)
        return [
            *command[:index],
            "--publish",
            f"127.0.0.1:{self.rcon_port}:{self.rcon_port}",
            *command[index:],
        ]


def exercise_owner(accounts, mods, console, expect, report, lab, server):
    private = lab / ".omk-admin"
    private.mkdir(mode=0o700)
    cfg = OperatorConfig(
        private,
        {"dj2": lab},
        accounts.client.base_url,
        private / "drasl-session.json",
        private / "reports",
        {"dj2": ConsoleConfig(server.rcon_port, "rcon.json")},
    )
    _write_private(
        cfg.auth_file,
        private,
        {
            "schema": 1,
            "origin": cfg.auth_origin,
            "api_token": accounts.admin["apiToken"],
        },
    )
    _write_private(private / "rcon.json", private, {"password": server.rcon_password})
    inventory = RecoveryConsole(cfg.recovery_consoles["dj2"], server.rcon_password)
    inventory.ready()
    expect(True, "owner_rcon_requires_connection_adapter_capability")
    expect(inventory.online() == {}, "owner_rcon_empty_inventory_positive_control")
    invitation = accounts.client.request(
        "POST", "/drasl/api/v3/invites", {}, accounts.admin["apiToken"]
    )["code"]
    other_password = secrets.token_urlsafe(24)
    accounts.client.register("omk_bystander", other_password, invitation)
    other = accounts.services[1].login("omk_bystander", other_password).session
    original = accounts.final_recovered_session
    with (
        LabPlayer(accounts.client, original, 25576, mods) as player,
        LabPlayer(accounts.client, other, 25576, mods) as bystander,
    ):
        ids = inventory.online()
        expect(
            len(ids) == 2 and UUID(original.player_uuid) in {UUID(k) for k in ids},
            "owner_rcon_reports_real_uuid_inventory",
        )
        _console_denials(player, bystander, original, console, expect, lab)
        plan = prepare(cfg, FIRST)
        expect(
            len(plan["players"]) == 1 and plan["servers"] == ["dj2"],
            "owner_plan_preserves_existing_profile",
        )
        delivered = []
        result = execute(cfg, plan["account"], emit=delivered.append)
        expect(
            result["ok"] and len(delivered) == 1,
            "owner_engine_complete_single_password_delivery_callback",
        )
        deadline = time.monotonic() + 8
        while player.error is None and time.monotonic() < deadline:
            time.sleep(0.05)
        expect(
            player.error is not None and "omk_account_recovery" in player.error,
            "owner_rcon_uuid_kick_disconnects_real_forge_actor",
        )
        expect(
            list(inventory.online().values()) == ["omk_bystander"]
            and bystander.error is None,
            "owner_recovery_keeps_unrelated_actor_connected",
        )
        journal = status(cfg, plan["account"])["recovery"]
        text = json.dumps(journal)
        expect(
            journal["stage"] == "complete"
            and delivered[0] not in text
            and server.rcon_password not in text,
            "owner_journal_has_no_generated_or_console_password",
        )
        accounts.final_owner_password = delivered[0]
    from omk.dj2_account_recovery_lab import _invalid_sessions  # noqa: PLC0415

    _invalid_sessions(accounts, [original], expect, "owner_reset")
    renewed = accounts.services[0].login(FIRST, accounts.final_owner_password).session
    expect(
        renewed.player_uuid == original.player_uuid, "owner_reset_keeps_profile_uuid"
    )
    with LabPlayer(accounts.client, renewed, 25576, mods) as player:
        expect(player.dimension == 0, "owner_new_password_passes_real_forge_login")
        expect(
            "Found"
            in console(
                "testfor "
                + FIRST
                + ' {Inventory:[{Slot:8b,id:"minecraft:emerald",Count:7}],XpLevel:12}'
            ),
            "owner_reset_keeps_real_inventory_and_levels",
        )
    _pending_login(cfg, accounts, renewed, mods, inventory, expect, report)
    abrupt_exit(cfg, accounts, mods, expect, report)
    console("save-all flush")
    report["owner_workflow"] = {
        "real_drasl_and_rcon_and_forge": True,
        "unrelated_actor_preserved": True,
        "interactive_terminal_delivery_automated": False,
        "pending_pre_authenticated_handshake_tested": True,
        "process_exit_before_password_delivery_tested": True,
    }


def _pending_login(cfg, accounts, session, mods, inventory, expect, report):
    # Hold a genuine authenticated connection before the Forge mod handshake.
    pending = LabPlayer(accounts.client, session, 25576, mods)
    with pending.login as held:
        expect(
            held[1].authenticated,
            "owner_pending_login_passes_initial_auth_positive_control",
        )
        pending.login = contextlib.nullcontext(held)
        report["pending_login_was_listed"] = (
            str(UUID(session.player_uuid)) in inventory.online()
        )
        plan = prepare(cfg, FIRST)
        delivered = []
        result = execute(cfg, plan["account"], emit=delivered.append)
        expect(
            result["ok"] and len(delivered) == 1,
            "owner_pending_login_recovery_engine_completed",
        )
        entered = False
        try:
            with pending:
                entered = pending.entity_id is not None
        except OSError, ValueError, RuntimeError:
            pass
        report["pending_login_survived_reset"] = entered
        rejection_confirmed = not entered and "omk_account_recovery" in (
            pending.error or ""
        )
        report["pending_login_explicit_rejection_confirmed"] = rejection_confirmed
        expect(
            rejection_confirmed,
            "owner_pending_login_cannot_finish_after_token_revocation",
        )
    accounts.final_owner_password = delivered[0]
    fresh = accounts.services[0].login(FIRST, delivered[0]).session
    with LabPlayer(accounts.client, fresh, 25576, mods) as player:
        expect(
            player.dimension == 0, "owner_after_pending_reset_new_password_still_works"
        )


def _console_denials(player, bystander, original, console, expect, lab):
    # Test beyond vanilla permission denial: even an OP player must not drain others.
    console("op " + FIRST)
    console("op omk_bystander")
    try:
        for actor, request, label in [
            (
                player,
                "/list omk-recovery version",
                "owner_adapter_version_is_console_only",
            ),
            (
                bystander,
                f"/list omk-recovery drain {UUID(original.player_uuid)} {FIRST}",
                "owner_adapter_drain_is_console_only",
            ),
        ]:
            actor.messages.clear()
            actor.command(request)
            try:
                actor.wait(
                    lambda a=actor: any(
                        "OMK_RECOVERY_ERROR console_only" in json.dumps(m)
                        for m in tuple(a.messages)
                    )
                )
            finally:
                # Only game chat/error, no Drasl/RCON credentials; private lab evidence.
                (lab / (label + ".json")).write_text(
                    json.dumps(
                        {"messages": list(actor.messages), "game_error": actor.error}
                    ),
                    encoding="utf-8",
                )
            expect(player.error is None and bystander.error is None, label)
    finally:
        console("deop " + FIRST)
        console("deop omk_bystander")
