"""Real, disposable Drasl integration checks. No existing accounts are used."""

import base64
import os
import re
import secrets
import struct
import subprocess
import tempfile
import time
import zlib
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.parse import urlencode
from uuid import uuid4

from launcher.accounts import AccountService, Registration
from launcher.storage import FileSessionStore
from omk.drasl import DraslClient, DraslError
from omk.profiles import PROJECT_ROOT


def skin_fixture() -> bytes:
    """Create an original opaque 64x64 PNG fixture using the standard library."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data))
        )

    rows = b"".join(b"\0" + bytes((40, 120, 200, 255)) * 64 for _ in range(64))
    header = struct.pack(">IIBBBBB", 64, 64, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(rows))
        + chunk(b"IEND", b"")
    )


def _expect_denied(operation: Callable[[], Any], statuses: set[int]) -> None:
    try:
        operation()
    except DraslError as exc:
        if exc.status in statuses:
            return
        raise RuntimeError(f"Unexpected refusal status: {exc.status}") from None
    raise RuntimeError("An operation which must be denied was accepted")


def _registration_checks(
    client: DraslClient,
    invitation: str,
    passed: Callable[[str], None],
) -> tuple[dict[str, Any], dict[str, Any], str]:
    admin = client.register("omk_lab_admin", secrets.token_urlsafe(24), invitation)
    if not admin["user"]["isAdmin"]:
        raise RuntimeError("Bootstrap account did not become the lab administrator")
    passed("bootstrap_registration")
    name, password = "omk_test_player", secrets.token_urlsafe(24)
    _expect_denied(lambda: client.register(name, password, ""), {400, 403})
    passed("registration_requires_invitation")
    invite = client.request("POST", "/drasl/api/v3/invites", {}, admin["apiToken"])[
        "code"
    ]
    user = client.register(name, password, invite)
    if user["user"]["isAdmin"]:
        raise RuntimeError("A player account received admin privileges")
    passed("player_registration")
    _expect_denied(
        lambda: client.register("omk_other", secrets.token_urlsafe(24), invite),
        {400, 403},
    )
    passed("invitation_cannot_be_reused")
    return admin, user, password


def _profile_checks(
    client: DraslClient,
    admin: dict[str, Any],
    user: dict[str, Any],
    passed: Callable[[str], None],
) -> None:
    skin = {
        "skinBase64": base64.b64encode(skin_fixture()).decode("ascii"),
        "skinModel": "classic",
    }
    player_uuid = user["user"]["players"][0]["uuid"]
    path = f"/drasl/api/v3/players/{player_uuid}"
    _expect_denied(lambda: client.request("PATCH", path, skin), {401, 403})
    passed("anonymous_skin_change_rejected")
    updated = client.request("PATCH", path, skin, user["apiToken"])
    if not updated.get("skinUrl"):
        raise RuntimeError("Skin upload returned no texture URL")
    passed("skin_uploaded_through_api")
    admin_uuid = admin["user"]["players"][0]["uuid"]
    # The same valid PNG is refused for an existing profile owned by another user.
    _expect_denied(
        lambda: client.request(
            "PATCH", f"/drasl/api/v3/players/{admin_uuid}", skin, user["apiToken"]
        ),
        {400, 403},
    )
    passed("another_players_skin_change_rejected")


def _session_checks(
    client: DraslClient,
    user: dict[str, Any],
    password: str,
    passed: Callable[[str], None],
) -> None:
    name = user["user"]["username"]
    player_uuid = user["user"]["players"][0]["uuid"].replace("-", "")
    _expect_denied(
        lambda: client.authenticate(name, "wrong-test-password", "test"), {400, 403}
    )
    passed("wrong_password_rejected")
    client_token = uuid4().hex
    game = client.authenticate(name, password, client_token)
    if game["selectedProfile"]["id"].replace("-", "") != player_uuid:
        raise RuntimeError("Game identity differs from the registered player")
    passed("game_authentication_stable_uuid")
    game_token = game["accessToken"]
    server_id = secrets.token_hex(20)
    client.request(
        "POST",
        "/session/minecraft/join",
        {
            "accessToken": game_token,
            "selectedProfile": game["selectedProfile"]["id"],
            "serverId": server_id,
        },
    )
    joined = client.request(
        "GET",
        "/session/minecraft/hasJoined?"
        + urlencode({"username": name, "serverId": server_id}),
    )
    if joined["id"].replace("-", "") != player_uuid:
        raise RuntimeError("Join verification returned another identity")
    passed("join_hasJoined_protocol")
    renewed = client.request(
        "POST",
        "/auth/refresh",
        {"accessToken": game_token, "clientToken": client_token},
    )
    new_token = renewed["accessToken"]
    client.request(
        "POST",
        "/auth/validate",
        {"accessToken": new_token, "clientToken": client_token},
    )
    passed("session_refreshed_without_password")
    client.request(
        "POST",
        "/auth/invalidate",
        {"accessToken": new_token, "clientToken": client_token},
    )
    _expect_denied(
        lambda: client.request(
            "POST",
            "/auth/validate",
            {"accessToken": new_token, "clientToken": client_token},
        ),
        {400, 403},
    )
    passed("revoked_session_rejected")


def _launcher_revocation_checks(
    client: DraslClient,
    service: AccountService,
    registration: Registration,
    passed: Callable[[str], None],
) -> None:
    old = service.current
    if old is None:
        raise RuntimeError("No launcher session")
    management = client.login(registration.username, registration.password)["apiToken"]
    other = client.authenticate(
        registration.username, registration.password, uuid4().hex
    )
    new_password = secrets.token_urlsafe(24)
    changed = service.change_password(registration.password, new_password)
    _expect_denied(lambda: client.user(management), {401, 403})
    for game in [
        other,
        {"accessToken": old.access_token, "clientToken": old.client_token},
    ]:
        _expect_denied(
            lambda game=game: client.request("POST", "/auth/validate", game), {400, 403}
        )
    _expect_denied(
        lambda: client.login(registration.username, registration.password),
        {400, 401, 403},
    )
    passed("launcher_password_change_revokes_old_sessions_and_management_token")
    service.revoke_all(new_password)
    _expect_denied(
        lambda: client.refresh(
            changed.session.access_token, changed.session.client_token
        ),
        {400, 403},
    )
    if service.store.load() is not None:
        raise RuntimeError("Revoked launcher session remains on disk")
    passed("launcher_all_sessions_revoked")


def _launcher_checks(
    client: DraslClient, admin: dict[str, Any], passed: Callable[[str], None]
) -> None:
    local = PROJECT_ROOT / ".local"
    local.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="launcher-auth-", dir=local) as folder:
        store = FileSessionStore(Path(folder) / "session.json")
        service = AccountService(client, store)
        invite = client.request("POST", "/drasl/api/v3/invites", {}, admin["apiToken"])[
            "code"
        ]
        registration = service.prepare_registration("omk_launcher", invite)
        result = service.register(registration)
        if not result.remembered or registration.password in store.path.read_text():
            raise RuntimeError("Portable registration storage check failed")
        passed("launcher_registration_with_portable_game_session")
        # The persisted game token must not authorize account-management requests.
        _expect_denied(
            lambda: client.update_user(
                result.session.access_token, {"password": secrets.token_urlsafe(24)}
            ),
            {401, 403},
        )
        passed("portable_game_token_cannot_change_account_password")
        restored = AccountService(client, store).restore()
        if (
            restored is None
            or restored.session.player_uuid != result.session.player_uuid
        ):
            raise RuntimeError("Portable automatic login check failed")
        passed("launcher_auto_login_without_password")
        service.current = restored.session
        service.upload_skin(skin_fixture(), "classic")
        service.upload_skin(skin_fixture(), "slim")
        player = client.request(
            "GET",
            f"/drasl/api/v3/players/{restored.session.player_uuid}",
            token=admin["apiToken"],
        )
        if not player.get("skinUrl") or player.get("skinModel") != "slim":
            raise RuntimeError("Game-token skin upload did not update the profile")
        passed("launcher_skin_upload_with_game_token_classic_and_slim")
        _launcher_revocation_checks(client, service, registration, passed)


def _launcher_expiry_checks(
    client: DraslClient, admin: dict[str, Any], passed: Callable[[str], None]
) -> None:
    local = PROJECT_ROOT / ".local"
    local.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="session-expiry-", dir=local) as folder:
        store = FileSessionStore(Path(folder) / "session.json")
        service = AccountService(client, store)
        invite = client.request("POST", "/drasl/api/v3/invites", {}, admin["apiToken"])[
            "code"
        ]
        result = service.register(service.prepare_registration("omk_expiry", invite))
        client.request(
            "POST",
            "/auth/validate",
            {
                "accessToken": result.session.access_token,
                "clientToken": result.session.client_token,
            },
        )
        passed("game_session_valid_before_expiry")
        time.sleep(2.2)
        if (
            AccountService(client, store).restore() is not None
            or store.load() is not None
        ):
            raise RuntimeError("Expired game session was restored")
        passed("expired_game_session_requires_reauthentication")


def _exercise_lab(
    docker: Callable[..., subprocess.CompletedProcess[str]],
    report: dict[str, Any],
    passed: Callable[[str], None],
    *,
    with_gui: bool,
    expiry_only: bool,
) -> None:
    client = DraslClient("http://127.0.0.1:25586")
    metadata = None
    for _ in range(40):
        try:
            metadata = client.request("GET", "/authlib-injector")
            break
        except URLError, TimeoutError, ConnectionError:
            time.sleep(0.25)
    if metadata is None:
        raise RuntimeError("Drasl did not become ready")
    report["drasl_version"] = metadata["meta"]["implementationVersion"]
    logs = docker("logs", "--no-color", "drasl").stdout
    if "unknown config option" in logs:
        raise RuntimeError("Drasl rejected a configuration option")
    match = re.search(r"invite=([A-Za-z0-9_-]+)", logs)
    if match is None:
        raise RuntimeError("No bootstrap invitation in the disposable lab")
    admin, user, password = _registration_checks(client, match[1], passed)
    if expiry_only:
        _launcher_expiry_checks(client, admin, passed)
    else:
        _profile_checks(client, admin, user, passed)
        _session_checks(client, user, password, passed)
        _launcher_checks(client, admin, passed)
    if with_gui and not expiry_only:
        from omk.gui_lab import launcher_checks  # noqa: PLC0415 - Qt is optional

        launcher_checks(client, admin, passed)


def auth_smoke(*, with_gui: bool = False, expiry_only: bool = False) -> dict[str, Any]:
    """Start a unique Compose project and always remove only that project's state."""
    project = f"omk-auth-smoke-{uuid4().hex[:10]}"
    compose = PROJECT_ROOT / "deploy" / "auth-lab" / "compose.yaml"
    command = ["docker", "compose", "--project-name", project, "--file", str(compose)]
    config = compose.parent / "config.toml"
    environment = {**os.environ, "OMK_AUTH_LAB_CONFIG": str(config)}
    temporary_config: tempfile.TemporaryDirectory[str] | None = None
    report: dict[str, Any] = {
        "project": project,
        "checks": [],
        "cleanup": False,
        "ok": False,
    }

    def docker(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [*command, *args],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
            env=environment,
        )

    def passed(name: str) -> None:
        report["checks"].append(name)

    try:
        if expiry_only:
            local = PROJECT_ROOT / ".local"
            local.mkdir(exist_ok=True)
            temporary_config = tempfile.TemporaryDirectory(
                prefix="drasl-expiry-", dir=local
            )
            short_config = Path(temporary_config.name) / "config.toml"
            short_config.write_text(
                config.read_text().replace(
                    "TokenExpireSec = 3600", "TokenExpireSec = 2"
                )
            )
            environment["OMK_AUTH_LAB_CONFIG"] = str(short_config)
        started = docker("up", "--detach", "--pull", "never")
        if started.returncode:
            raise RuntimeError(
                "Cannot start the lab; check Docker, the pinned image and free port 25586"
            )
        _exercise_lab(
            docker, report, passed, with_gui=with_gui, expiry_only=expiry_only
        )
        report["ok"] = True
    except (
        RuntimeError,
        KeyError,
        IndexError,
        ValueError,
        OSError,
        subprocess.SubprocessError,
    ) as exc:
        # Do not include request payloads, Docker logs, API tokens or passwords.
        report["error"] = (
            str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__
        )
    finally:
        try:
            report["cleanup"] = docker("down", "--timeout", "5").returncode == 0
        except OSError, subprocess.SubprocessError:
            report["cleanup"] = False
        report["ok"] = report["ok"] and report["cleanup"]
        if temporary_config is not None and report["cleanup"]:
            temporary_config.cleanup()
    return report
