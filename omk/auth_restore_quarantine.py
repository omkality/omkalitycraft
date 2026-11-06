"""Offline-to-network staging policy for a trusted Drasl 4.0 backup.

Run only in an isolated container network with NO published port. Secrets arrive
over stdin, never command arguments/environment/logs. The caller supplies a NEW
owner password, retains it privately and replaces their operator credential.
All other restored accounts stay locked pending individual owner recovery.
"""

import json
import secrets
import sys
import time
from urllib.error import URLError

from omk.drasl import DraslClient


def quarantine(client, token, owner_password):
    for _ in range(80):
        try:
            client.request("GET", "/authlib-injector")
            break
        except URLError, TimeoutError, ConnectionError:
            time.sleep(0.25)
    else:
        raise RuntimeError("Quarantined service did not become ready")
    owner = client.user(token)
    if not owner.get("isAdmin") or owner.get("isLocked"):
        raise ValueError("An unlocked snapshot administrator is required")
    users = client.request("GET", "/drasl/api/v3/users", token=token)
    if not 1 <= len(users) <= 1000:
        raise ValueError("Account count exceeds reviewed restore budget")
    for user in users:
        if user["uuid"] != owner["uuid"]:
            result = client.request(
                "PATCH",
                "/drasl/api/v3/users/" + user["uuid"],
                {
                    "isLocked": True,
                    "password": secrets.token_urlsafe(32),
                    "resetApiToken": True,
                    "resetMinecraftToken": True,
                },
                token,
            )
            if result.get("isLocked") is not True:
                raise ValueError("Restored account lock not confirmed")
    invites = client.request("GET", "/drasl/api/v3/invites", token=token)
    if len(invites) > 10000:
        raise ValueError("Invitation count exceeds reviewed restore budget")
    for invite in invites:
        client.request("DELETE", "/drasl/api/v3/invites/" + invite["code"], token=token)
    client.update_user(
        token,
        {
            "password": owner_password,
            "resetApiToken": True,
            "resetMinecraftToken": True,
        },
    )
    # Assert the new owner credential works; don't return it in a report.
    new_token = client.login(owner["username"], owner_password)["apiToken"]
    if client.user(new_token)["uuid"] != owner["uuid"]:
        raise ValueError("Owner identity changed")
    return {
        "credentials_rotated": len(users),
        "invitations_revoked": len(invites),
        "non_owner_accounts_locked": True,
    }


if __name__ == "__main__":
    try:
        request = json.loads(sys.stdin.buffer.read(65537))
        result = quarantine(
            DraslClient(request["origin"]), request["token"], request["password"]
        )
        print(json.dumps(result))
    except Exception:
        # No traceback/local variables: stdin contains private recovery credentials.
        print('{"ok": false, "error": "quarantine_failed_keep_offline"}')
        raise SystemExit(1) from None
