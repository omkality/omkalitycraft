"""Owner-only, journalled account recovery. Secrets never enter the journal."""

import contextlib
import hashlib
import json
import os
import re
import secrets
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from uuid import UUID

from omk.admin import AdminError, _client, _credential, _read_json, _write_private
from omk.diagnostics import regular
from omk.recovery_console import RecoveryConsole


@contextlib.contextmanager
def _locked(config):
    path = config.private / "recovery.lock"
    try:
        with path.open("xb") as stream:
            stream.write(b"0")
        path.chmod(0o600)
    except FileExistsError:
        pass
    if not regular(path, config.private):
        raise AdminError("Invalid account recovery lock")
    with path.open("r+b") as stream:
        if os.name == "nt":
            import msvcrt  # noqa: PLC0415

            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl  # noqa: PLC0415

            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            if os.name == "nt":
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _snapshot(user):
    players = user.get("players")
    if not isinstance(players, list) or not 1 <= len(players) <= 32:
        raise AdminError("Invalid account player inventory")
    values = []
    for player in players:
        if (
            not isinstance(player, dict)
            or not re.fullmatch(r"[A-Za-z0-9_]{3,16}", player.get("name", ""))
            or UUID(player["userUuid"]) != UUID(user["uuid"])
        ):
            raise AdminError("Invalid account player identity")
        values.append({"uuid": str(UUID(player["uuid"])), "name": player["name"]})
    if len({p["uuid"] for p in values}) != len(values):
        raise AdminError("Duplicate account player identity")
    return {
        "account": str(UUID(user["uuid"])),
        "username": user["username"],
        "players": sorted(values, key=lambda p: p["uuid"]),
    }


def _operator(config):
    client, token = _client(config), _credential(config)
    caller = client.user(token)
    if caller.get("isAdmin") is not True:
        raise AdminError("Account recovery requires a Drasl administrator")
    return client, token, str(UUID(caller["uuid"]))


def _binding(config):
    if not config.servers or set(config.servers) != set(config.recovery_consoles):
        raise AdminError("Every configured server requires a recovery console")
    consoles = {k: asdict(v) for k, v in sorted(config.recovery_consoles.items())}
    if len({(v["host"], v["port"]) for v in consoles.values()}) != len(consoles):
        raise AdminError("Each server requires a distinct recovery console")
    value = {
        "origin": config.auth_origin,
        "consoles": consoles,
        "servers": {k: str(v) for k, v in sorted(config.servers.items())},
    }
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def _path(config, account):
    return config.private / "recovery" / (str(UUID(account)) + ".json")


def _save(config, record, stage):
    record.update(stage=stage, updated_at=datetime.now(UTC).isoformat())
    _write_private(_path(config, record["account"]), config.private, record)
    if os.name != "nt":
        fd = os.open(config.private / "recovery", os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def prepare(config, username):
    if not re.fullmatch(r"[A-Za-z0-9_]{3,16}", username):
        raise AdminError("Use the existing community account name")
    with _locked(config):
        binding = _binding(config)
        client, token, operator = _operator(config)
        users = client.request("GET", "/drasl/api/v3/users", token=token)
        if not isinstance(users, list) or len(users) > 10000:
            raise AdminError("Invalid account inventory")
        matches = [
            u for u in users if u.get("username", "").casefold() == username.casefold()
        ]
        if len(matches) != 1:
            raise AdminError("Expected exactly one existing account")
        user = matches[0]
        if user.get("isAdmin") is not False or UUID(user["uuid"]) == UUID(operator):
            raise AdminError("Administrative accounts require separate recovery")
        if user.get("isLocked") is not False:
            raise AdminError(
                "Do not recover an already locked account as an unlocked player"
            )
        record = {
            "schema": 1,
            **_snapshot(user),
            "binding": binding,
            "servers": sorted(config.servers),
            "attempt": 0,
        }
        path = _path(config, record["account"])
        if (
            path.exists()
            and _read_json(path, config.private).get("stage") != "complete"
        ):
            raise AdminError(
                "An unfinished recovery exists; inspect and explicitly resume it"
            )
        folder = config.private / "recovery"
        if (
            folder.exists()
            and len(list(folder.iterdir())) >= 1000
            and not path.exists()
        ):
            raise AdminError("Account recovery journal capacity reached")
        _save(config, record, "planned")
        return {
            "ok": True,
            "account": record["account"],
            "username": record["username"],
            "players": record["players"],
            "servers": record["servers"],
            "journal_file": str(path),
            "account_changed": False,
        }


def status(config, account):
    record = _read_json(_path(config, account), config.private)
    return {"ok": True, "recovery": record}


def _read_record(config, account):
    record = _read_json(_path(config, account), config.private)
    if (
        record.get("schema") != 1
        or record.get("account") != str(UUID(account))
        or record.get("binding") != _binding(config)
        or record.get("servers") != sorted(config.servers)
    ):
        raise AdminError("Account recovery plan differs from current configuration")
    return record


def _consoles(config):
    result = {}
    for name, settings in config.recovery_consoles.items():
        value = _read_json(config.private / settings.credential_file, config.private)
        if set(value) != {"password"}:
            raise AdminError("Invalid private recovery console credential")
        result[name] = RecoveryConsole(settings, value["password"])
    return result


def _checked_user(client, token, record):
    user = client.request(
        "GET", "/drasl/api/v3/users/" + record["account"], token=token
    )
    if _snapshot(user) != {k: record[k] for k in ("account", "username", "players")}:
        raise AdminError("Account identity changed; recovery requires investigation")
    if user.get("isAdmin") is not False:
        raise AdminError("Recovery target became an administrator")
    return user


def _patch(client, token, record, changes):
    client.request("PATCH", "/drasl/api/v3/users/" + record["account"], changes, token)
    return _checked_user(client, token, record)


def _recover(config, record, client, token, consoles, emit):
    password = secrets.token_urlsafe(24)
    record["attempt"] += 1
    _save(config, record, "locking")
    try:
        if (
            _patch(client, token, record, {"isLocked": True}).get("isLocked")
            is not True
        ):
            raise AdminError("Account lock was not confirmed")
        _save(config, record, "resetting")
        changed = _patch(
            client,
            token,
            record,
            {
                "password": password,
                "resetApiToken": True,
                "resetMinecraftToken": True,
            },
        )
        if changed.get("isLocked") is not True:
            raise AdminError("Account unexpectedly unlocked during recovery")
        _save(config, record, "disconnecting")
        players = [p["uuid"] for p in record["players"]]
        for console in consoles.values():
            console.disconnect(players)
        # Recheck every server and identity before the unlock request.
        for console in consoles.values():
            if set(console.online()) & set(players):
                raise AdminError("A game profile reappeared during recovery")
        if _checked_user(client, token, record).get("isLocked") is not True:
            raise AdminError("Account lock changed before completion")
        _save(config, record, "unlocking")
        if (
            _patch(client, token, record, {"isLocked": False}).get("isLocked")
            is not False
        ):
            raise AdminError("Account unlock was not confirmed")
        _save(config, record, "password_delivery")
        emit(password)
        _save(config, record, "complete")
    except Exception as error:
        # A lost reply is not proof of success. Best-effort close; journal uncertainty.
        record["failed_stage"] = record["stage"]
        record["failure_type"] = type(error).__name__
        record["lock_confirmed_after_failure"] = False
        with contextlib.suppress(Exception):
            locked = _patch(client, token, record, {"isLocked": True})
            record["lock_confirmed_after_failure"] = locked.get("isLocked") is True
        _save(config, record, "incomplete")
        raise AdminError(
            "Recovery incomplete; inspect its journal and explicitly resume; no password was saved"
        ) from None
    return {
        "ok": True,
        "account": record["account"],
        "stage": "complete",
        "servers_checked": record["servers"],
        "password_saved": False,
    }


def execute(config, account, *, resume=False, emit):
    with _locked(config):
        record = _read_record(config, account)
        if record.get("stage") == "complete" or (
            record.get("stage") != "planned" and not resume
        ):
            raise AdminError("Recovery requires a new plan or explicit resume")
        client, token, operator = _operator(config)
        if operator == record["account"]:
            raise AdminError("Do not recover the current operator account")
        user = _checked_user(client, token, record)
        if record["stage"] == "planned" and user.get("isLocked") is not False:
            raise AdminError("Planned account was locked by another operation")
        consoles = _consoles(config)
        for console in consoles.values():
            console.online()  # Preflight all servers before any account mutation.
        return _recover(config, record, client, token, consoles, emit)


def terminal_password(password):
    sys.stderr.write("\nNew account password (shown once): " + password + "\n")
    sys.stderr.flush()


def run_recovery(config, args):
    if args.recovery_action == "plan":
        return prepare(config, args.username)
    if args.recovery_action == "status":
        return status(config, args.account)
    if not sys.stdin.isatty() or not sys.stderr.isatty():
        raise AdminError("Password delivery requires an interactive private terminal")
    return execute(
        config,
        args.account,
        resume=args.recovery_action == "resume",
        emit=terminal_password,
    )


def add_recovery_parser(actions):
    recovery = actions.add_parser(
        "recover-account", help="Owner-only journalled account recovery"
    )
    sub = recovery.add_subparsers(dest="recovery_action", required=True)
    sub.add_parser("plan").add_argument("--username", required=True)
    for name in ("run", "resume", "status"):
        sub.add_parser(name).add_argument(
            "--account", required=True, help="Drasl account UUID, not player UUID"
        )
