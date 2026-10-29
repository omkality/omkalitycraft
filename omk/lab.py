"""Real, disposable Drasl integration checks. No existing accounts are used."""

import base64
import re
import secrets
import struct
import subprocess
import time
import zlib
from collections.abc import Callable
from typing import Any
from urllib.error import URLError
from urllib.parse import urlencode
from uuid import uuid4

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


def auth_smoke() -> dict[str, Any]:
    """Start a unique Compose project and always remove only that project's state."""
    project = f"omk-auth-smoke-{uuid4().hex[:10]}"
    compose = PROJECT_ROOT / "deploy" / "auth-lab" / "compose.yaml"
    command = ["docker", "compose", "--project-name", project, "--file", str(compose)]
    report: dict[str, Any] = {
        "project": project,
        "checks": [],
        "cleanup": False,
        "ok": False,
    }

    def docker(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [*command, *args], capture_output=True, text=True, timeout=60, check=False
        )

    def passed(name: str) -> None:
        report["checks"].append(name)

    try:
        started = docker("up", "--detach", "--pull", "never")
        if started.returncode:
            raise RuntimeError(
                "Cannot start the lab; check Docker, the pinned image and free port 25586"
            )
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
        _profile_checks(client, admin, user, passed)
        _session_checks(client, user, password, passed)
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
    return report
