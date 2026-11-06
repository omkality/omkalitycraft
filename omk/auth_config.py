"""Environment-driven Drasl config; no account credentials are accepted here."""

import json
import os
import re
from pathlib import Path
from urllib.parse import urlsplit

from omk.drasl import DraslClient


def render_config(environment=None):
    env = os.environ if environment is None else environment
    origin = env.get("OMK_AUTH_URL", "http://127.0.0.1:25586").rstrip("/")
    DraslClient(origin)  # HTTPS outside loopback, no credentials/query/path.
    admin = env.get("OMK_AUTH_ADMIN", "omk_owner")
    if not re.fullmatch(r"[A-Za-z0-9_]{3,16}", admin):
        raise ValueError("Invalid OMK_AUTH_ADMIN")
    limits = {}
    for name, default, minimum, maximum in (
        ("INTERNAL_PORT", 25585, 1024, 65535),
        ("TOKEN_EXPIRE_SECONDS", 2592000, 3600, 31536000),
        ("TOKEN_STALE_SECONDS", 86400, 1, 2592000),
        ("MIN_PASSWORD_LENGTH", 12, 12, 128),
    ):
        value = int(env.get("OMK_AUTH_" + name, str(default)))
        if not minimum <= value <= maximum:
            raise ValueError("Invalid OMK_AUTH_" + name)
        limits[name] = value
    if limits["TOKEN_STALE_SECONDS"] >= limits["TOKEN_EXPIRE_SECONDS"]:
        raise ValueError("Session stale interval must be below expiry")
    values = {
        "Domain": urlsplit(origin).hostname,
        "BaseURL": origin,
        "ListenAddress": f"0.0.0.0:{limits['INTERNAL_PORT']}",
        "DefaultAdmins": [admin],
        "StateDirectory": "/var/lib/drasl",
        "AllowChangingPlayerName": False,
        "DefaultMaxPlayerCount": 1,
        "SignPublicKeys": False,
        "TokenExpireSec": limits["TOKEN_EXPIRE_SECONDS"],
        "TokenStaleSec": limits["TOKEN_STALE_SECONDS"],
        "MinPasswordLength": limits["MIN_PASSWORD_LENGTH"],
        "AllowSkins": True,
        "AllowCapes": False,
    }
    return (
        "# Generated locally; contains no account password or API token.\n"
        + "\n".join(f"{key} = {json.dumps(value)}" for key, value in values.items())
        + "\n\n[RegistrationUsernamePassword.CreateNewPlayer]\n"
        "Allow = true\nRequireInvite = true\nAllowChoosingUUID = false\n"
    )


def configure(output: Path):
    data = render_config()
    # No overwrite: changing DefaultAdmins on an existing service needs a review.
    with output.open("x", encoding="utf-8") as file:
        file.write(data)
    return {"ok": True, "config": str(output.resolve()), "contains_credentials": False}


def add_auth_commands(sub):
    auth = sub.add_parser("auth", help="Configure the persistent Drasl runtime")
    action = auth.add_subparsers(dest="action", required=True).add_parser("configure")
    action.add_argument("--output", type=Path, required=True)
