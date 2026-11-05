"""Characterize account recovery on fresh Drasl + Linux Forge, never live accounts.

This is a laboratory command, not the production owner reset interface. In
particular a successful password reset alone must not be called a live kick.
"""

import json
import re
import secrets
import subprocess
import time
from types import SimpleNamespace
from uuid import UUID, uuid4

from launcher.accounts import AccountService
from launcher.storage import FileSessionStore
from omk.dj2_claim_regression_lab import (
    _artifact_hashes,
    _finish,
    add_linux_runtime_inputs,
    validate_linux_runtime_inputs,
)
from omk.dj2_commands_lab import FIRST, _contains, _response
from omk.dj2_lab import _console_sender, _copy_server, _wait_server
from omk.dj2_linux_lab import JAVA_IMAGE, LinuxServer
from omk.drasl import DraslClient, DraslError
from omk.forge_player import LabPlayer
from omk.forge_probe import probe_login
from omk.lab import _expect_denied
from omk.profiles import PROJECT_ROOT


def add_account_recovery_lab(parser):
    add_linux_runtime_inputs(parser)


def _accounts(compose, lab):
    subprocess.run(
        [*compose, "up", "--detach", "--pull", "never"],
        capture_output=True,
        check=True,
        timeout=60,
    )
    client = DraslClient("http://127.0.0.1:25586")
    for _ in range(60):
        try:
            client.request("GET", "/authlib-injector")
            break
        except OSError, DraslError:
            time.sleep(0.2)
    else:
        raise RuntimeError("Fresh recovery auth service did not become ready")
    logs = subprocess.check_output([*compose, "logs", "--no-color", "drasl"], text=True)
    bootstrap = re.search(r"invite=([A-Za-z0-9_-]+)", logs)
    if bootstrap is None:
        raise RuntimeError("Fresh recovery auth bootstrap invitation missing")
    admin = client.register("omk_lab_admin", secrets.token_urlsafe(24), bootstrap[1])
    invitation = client.request("POST", "/drasl/api/v3/invites", {}, admin["apiToken"])[
        "code"
    ]
    password = secrets.token_urlsafe(24)
    user = client.register(FIRST, password, invitation)
    stores = [FileSessionStore(lab / f"account-{i}/session.json") for i in range(2)]
    services = [AccountService(client, store) for store in stores]
    sessions = [service.login(FIRST, password).session for service in services]
    # All management credentials and plaintext passwords stay in memory. Only
    # revocable game tokens are saved, exclusively under this fresh lab folder.
    return SimpleNamespace(
        client=client,
        admin=admin,
        user=user,
        password=password,
        services=services,
        stores=stores,
        sessions=sessions,
    )


def _denied(operation, expect, label, statuses=frozenset({400, 401, 403})):
    _expect_denied(operation, set(statuses))
    expect(True, label)


def _invalid_sessions(accounts, sessions, expect, prefix):
    client = accounts.client
    for index, session in enumerate(sessions):
        _denied(
            lambda s=session: client.refresh(s.access_token, s.client_token),
            expect,
            f"{prefix}_session_{index}_refresh_rejected",
        )
        _denied(
            lambda s=session: client.request(
                "POST",
                "/auth/validate",
                {"accessToken": s.access_token, "clientToken": s.client_token},
            ),
            expect,
            f"{prefix}_session_{index}_validate_rejected",
        )
        _denied(
            lambda s=session: client.request(
                "POST",
                "/session/minecraft/join",
                {
                    "accessToken": s.access_token,
                    "selectedProfile": UUID(s.player_uuid).hex,
                    "serverId": "omk-recovery-negative-" + uuid4().hex,
                },
            ),
            expect,
            f"{prefix}_session_{index}_join_rejected",
        )


def _still_connected(player, console, expect, label):
    marker = "OmkRecovery" + uuid4().hex
    player.messages.clear()
    console("say " + marker)
    player.wait(lambda: any(marker in json.dumps(m) for m in tuple(player.messages)))
    expect(player.error is None, label)


def _kick(player, console, expect, label):
    # Fixed fixture name, never a command composed from API/owner input.
    console("kick " + FIRST + " omk_recovery_lab")
    deadline = time.monotonic() + 12
    while player.error is None and time.monotonic() < deadline:
        time.sleep(0.05)
    expect(player.error is not None and "omk_recovery_lab" in player.error, label)


def _permissions(accounts, expect):
    client, session = accounts.client, accounts.sessions[0]
    user_id = accounts.user["user"]["uuid"]
    target = "/drasl/api/v3/users/" + str(UUID(user_id))
    token = accounts.admin["apiToken"]
    expect(UUID(user_id) != UUID(session.player_uuid), "account_uuid_is_not_game_uuid")
    _denied(
        lambda: client.request(
            "PATCH", target, {"isLocked": True}, session.access_token
        ),
        expect,
        "game_token_cannot_manage_account",
    )
    _denied(
        lambda: client.request(
            "PATCH",
            "/drasl/api/v3/users/" + accounts.admin["user"]["uuid"],
            {"password": secrets.token_urlsafe(24)},
            accounts.user["apiToken"],
        ),
        expect,
        "player_management_token_cannot_reset_another_account",
    )
    _denied(
        lambda: client.request(
            "PATCH",
            "/drasl/api/v3/users/" + str(UUID(session.player_uuid)),
            {"isLocked": True},
            token,
        ),
        expect,
        "game_uuid_not_accepted_as_account_uuid",
        {404},
    )
    return target


def _exercise(accounts, mods, console, expect, report):
    client, session = accounts.client, accounts.sessions[0]
    user_id = accounts.user["user"]["uuid"]
    token = accounts.admin["apiToken"]
    target = _permissions(accounts, expect)
    for index, saved in enumerate(accounts.sessions):
        client.request(
            "POST",
            "/auth/validate",
            {"accessToken": saved.access_token, "clientToken": saved.client_token},
        )
        expect(True, f"initial_session_{index}_valid_positive_control")
    with LabPlayer(client, session, 25576, mods) as player:
        expect(player.dimension == 0, "normal_non_op_actor_completes_forge_handshake")
        console("fill 0 240 0 15 240 15 minecraft:bedrock")
        console("fill 0 241 0 15 245 15 minecraft:air")
        console("tp " + FIRST + " 8.5 241 8.5")
        console("replaceitem entity " + FIRST + " slot.hotbar.8 minecraft:emerald 7")
        console("xp 12L " + FIRST)
        _response(player, "/team create omkrecovery", "ftblib.lang.team.created")
        player.command("/chunks claim")
        _response(player, "/chunks info", "commands.chunks.info.text")
        expect(
            _contains(player, "omkrecovery"), "initial_native_claim_has_fixture_owner"
        )
        _response(player, "/sethome recovery", "ftbutilities.lang.homes.set")
        password = secrets.token_urlsafe(24)
        updated = client.request(
            "PATCH",
            target,
            {"password": password, "resetApiToken": True, "resetMinecraftToken": True},
            token,
        )
        expect(updated["uuid"] == user_id, "reset_preserves_drasl_account_uuid")
        _denied(
            lambda: client.authenticate(FIRST, accounts.password, uuid4().hex),
            expect,
            "old_password_rejected_after_reset",
        )
        _denied(
            lambda: client.user(accounts.user["apiToken"]),
            expect,
            "old_player_management_token_revoked",
        )
        _invalid_sessions(accounts, accounts.sessions, expect, "reset")
        for index, (service, store) in enumerate(
            zip(accounts.services, accounts.stores, strict=True)
        ):
            expect(
                service.restore() is None and not store.path.exists(),
                f"launcher_{index}_forgets_revoked_portable_session",
            )
        _still_connected(
            player, console, expect, "password_reset_alone_does_not_kick_live_player"
        )
        _kick(player, console, expect, "explicit_console_kick_disconnects_live_player")
    stale = probe_login(client, session, "127.0.0.1", 25576)
    expect(not stale.authenticated and not stale.joined, "old_token_real_login_denied")
    recovered = accounts.services[0].login(FIRST, password).session
    expect(
        UUID(recovered.player_uuid) == UUID(session.player_uuid),
        "new_password_keeps_game_uuid",
    )
    with LabPlayer(client, recovered, 25576, mods) as player:
        expect(
            "Found"
            in console(
                "testfor "
                + FIRST
                + ' {Inventory:[{Slot:8b,id:"minecraft:emerald",Count:7b}],XpLevel:12}'
            ),
            "recovered_actor_keeps_inventory_and_xp",
        )
        console("tp " + FIRST + " 10.5 241 10.5")
        player.wait(
            lambda: player.position is not None and abs(player.position[0] - 10.5) < 0.2
        )
        player.command("/home recovery")
        player.wait(
            lambda: player.position is not None and abs(player.position[0] - 8.5) < 1
        )
        expect(True, "recovered_actor_keeps_working_home")
        _response(player, "/chunks info", "commands.chunks.info.text")
        expect(_contains(player, "omkrecovery"), "recovered_actor_keeps_native_claim")
        locked = client.request("PATCH", target, {"isLocked": True}, token)
        expect(locked["isLocked"] is True, "admin_lock_confirmed")
        _denied(
            lambda: client.authenticate(FIRST, password, uuid4().hex),
            expect,
            "locked_account_rejects_correct_password",
        )
        _invalid_sessions(accounts, [recovered], expect, "lock")
        _still_connected(
            player, console, expect, "auth_lock_alone_does_not_kick_live_player"
        )
        _kick(player, console, expect, "locked_actor_explicitly_disconnected")
    client.request("PATCH", target, {"isLocked": False}, token)
    _repeat_reset(accounts, target, password, recovered, mods, console, expect)
    console("save-all flush")
    report.update(
        auth_reset_automatically_kicks_live_connection=False,
        explicit_lab_console_kicks_verified=True,
        production_reset_cli_implemented=False,
    )


def _repeat_reset(accounts, target, password, recovered, mods, console, expect):
    client, session = accounts.client, accounts.sessions[0]
    token = accounts.admin["apiToken"]
    _invalid_sessions(accounts, [recovered], expect, "unlock_does_not_revive")
    again = accounts.services[0].login(FIRST, password).session
    expect(
        UUID(again.player_uuid) == UUID(session.player_uuid),
        "unlock_keeps_profile_identity",
    )
    repeat_password = secrets.token_urlsafe(24)
    client.request(
        "PATCH",
        target,
        {
            "password": repeat_password,
            "resetApiToken": True,
            "resetMinecraftToken": True,
        },
        token,
    )
    _invalid_sessions(accounts, [again], expect, "second_reset")
    _denied(
        lambda: client.authenticate(FIRST, password, uuid4().hex),
        expect,
        "previous_recovery_password_rejected_after_second_reset",
    )
    final = accounts.services[0].login(FIRST, repeat_password).session
    with LabPlayer(client, final, 25576, mods) as player:
        expect(player.dimension == 0, "second_recovery_real_forge_login_succeeds")
        expect(
            "Found"
            in console(
                "testfor "
                + FIRST
                + ' {Inventory:[{Slot:8b,id:"minecraft:emerald",Count:7b}],XpLevel:12}'
            ),
            "second_recovery_keeps_inventory_and_xp",
        )


def run_account_recovery_lab(args):
    validate_linux_runtime_inputs(args)
    run = uuid4().hex[:10]
    lab = PROJECT_ROOT / ".local" / ("account-recovery-" + run)
    lab.mkdir()
    project = "omk-recovery-auth-" + run
    compose = [
        "docker",
        "compose",
        "--project-name",
        project,
        "-f",
        str(PROJECT_ROOT / "deploy/auth-lab/compose.yaml"),
    ]
    server = LinuxServer(lab, run, project + "_default")
    report = {
        "ok": False,
        "checks": [],
        "lab": lab.relative_to(PROJECT_ROOT).as_posix(),
        "linux_java_image": JAVA_IMAGE,
        "graphical_client": False,
        "scope": "fresh disposable accounts/world only; not a production reset command",
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
        state("preparing_fresh_account_recovery_lab")
        dest, mods = _copy_server(args, lab)
        report["artifact_sha256"] = _artifact_hashes(args, dest)
        accounts = _accounts(compose, lab)
        report["java_runtime"] = server.prepare(dest, args, accounts.client)
        process = server.start()
        _wait_server(process, server.log, state)
        console = _console_sender(process, server.log)
        operators = json.loads(
            server.helper("cat /srv/ops.json", readonly_volume=True).stdout
        )
        expect(
            all(
                UUID(row["uuid"]) != UUID(accounts.sessions[0].player_uuid)
                for row in operators
            ),
            "recovery_actor_is_not_operator",
        )
        _exercise(accounts, mods, console, expect, report)
        report["ok"] = True
    except Exception as error:
        # Authentication and network exceptions may carry credentials in their
        # text. Even assertion messages are fixed labels, never HTTP bodies.
        report["error_type"] = type(error).__name__
        report["failed_after"] = report["checks"][-1] if report["checks"] else "setup"
        report["error"] = (
            "Account recovery lab failed; inspect private isolated evidence"
        )
    finally:
        _finish(server, compose, report)
        state("complete" if report["ok"] else "failed")
        (lab / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
