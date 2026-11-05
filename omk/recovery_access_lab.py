"""Current vanilla access lists for a stopped, disposable Linux world return."""

import hashlib
import json
import re
import tarfile

from omk.dj2_commands_lab import FIRST, SECOND, _response
from omk.forge_player import LabPlayer
from omk.forge_probe import probe_login

LISTS = ("ops.json", "banned-players.json", "banned-ips.json", "whitelist.json")
FILES = (*LISTS, "server.properties")
MAX_FILE = 1024**2


def read_access(archive):
    """No extraction; bounded, exact allowlist, no secret data in errors/results."""
    if archive.is_symlink() or archive.stat().st_size > 6 * MAX_FILE:
        raise ValueError("Invalid current-access archive")
    data = {}
    with tarfile.open(archive, "r:") as tar:
        for member in tar:
            if (
                member.name not in FILES
                or member.name in data
                or not member.isfile()
                or member.issparse()
                or not 0 < member.size <= MAX_FILE
            ):
                raise ValueError("Invalid current-access archive entry")
            data[member.name] = tar.extractfile(member).read(MAX_FILE + 1)
    if set(data) != set(FILES):
        raise ValueError("Incomplete current-access archive")
    try:
        for name in LISTS:
            rows = json.loads(data[name])
            if (
                not isinstance(rows, list)
                or len(rows) > 10000
                or any(not isinstance(r, dict) for r in rows)
            ):
                raise ValueError("Invalid access list")
        text = data["server.properties"].decode("utf-8")
        flags = re.findall(r"^white-list=(true|false)\r?$", text, re.M)
        if len(flags) != 1:
            raise ValueError("Invalid whitelist flag")
    except ValueError, UnicodeError, RecursionError:
        raise ValueError("Invalid current-access data") from None
    manifest = {n: hashlib.sha256(b).hexdigest() for n, b in data.items()}
    return data, flags[0] == "true", manifest


def stage_access(archive, destination, *, lab):
    expected = lab / "recovery-lab-return/server"
    if (
        not lab.name.startswith("recovery-lab-")
        or lab.is_symlink()
        or destination != expected
        or not destination.is_dir()
        or destination.resolve() != destination.absolute()
        or not (lab / "full-return-staged.json").is_file()
        or archive.parent != lab / "current-access-before"
    ):
        raise ValueError("Expected the staged disposable replacement")
    data, enabled, manifest = read_access(archive)
    targets = [destination / n for n in LISTS]
    props = destination / "server.properties"
    if (
        any(p.exists() or p.is_symlink() for p in targets)
        or props.is_symlink()
        or not props.is_file()
    ):
        raise ValueError("Refusing existing or linked replacement access lists")
    current = props.read_text(encoding="utf-8")
    if len(current) > MAX_FILE:
        raise ValueError("Replacement properties too large")
    current = re.sub(r"^white-list=.*(?:\n|$)", "", current, flags=re.M)
    rendered = current.rstrip() + "\nwhite-list=" + str(enabled).lower() + "\n"
    result = {
        "lab_only": True,
        "source_file_sha256": manifest,
        "whitelist_enabled": enabled,
        "restored_lists": list(LISTS),
        "server_properties_copied": False,
    }
    with (lab / "current-access-plan.json").open("x", encoding="utf-8") as out:
        json.dump(result, out, indent=2)
    for name, path in zip(LISTS, targets, strict=True):
        with path.open("xb") as out:
            out.write(data[name])
        path.chmod(0o600)
        if hashlib.sha256(path.read_bytes()).hexdigest() != manifest[name]:
            raise ValueError("Current-access readback failed")
    props.write_text(rendered, encoding="utf-8")
    if props.read_text(encoding="utf-8") != rendered:
        raise ValueError("Current whitelist flag readback failed")
    with (lab / "current-access-staged.json").open("x", encoding="utf-8") as out:
        json.dump(result, out, indent=2)
    return result


def seed_access(console, expect):
    # Observe actual restored permissions below rather than matching localized
    # command-success strings. These accounts exist only in this fresh lab.
    for command in [
        "op " + FIRST,
        "ban " + SECOND + " omk_access_fixture",
        "whitelist add " + FIRST,
        "whitelist add " + SECOND,
        "whitelist on",
    ]:
        console(command)
    expect(True, "current_access_fixture_commands_issued")


def verify_access(client, sessions, mods, console, expect):
    first_session, second_session = sessions
    expect(
        not probe_login(client, second_session, "127.0.0.1", 25576).authenticated,
        "current_ban_survives_historical_world_return",
    )
    with LabPlayer(client, first_session, 25576, mods) as first:
        _response(first, "/whitelist list", "commands.whitelist.list")
        expect(True, "current_op_permission_survives_world_return")
        console("deop " + FIRST)
        _response(first, "/whitelist list", "commands.generic.permission")
        expect(True, "explicit_deop_removes_operator_permission")
    console("pardon " + SECOND)
    with LabPlayer(client, second_session, 25576, mods):
        expect(True, "same_session_rejoins_after_explicit_pardon")
    console("whitelist remove " + SECOND)
    expect(
        not probe_login(client, second_session, "127.0.0.1", 25576).authenticated,
        "current_whitelist_is_enforced_after_world_return",
    )
    console("whitelist add " + SECOND)
