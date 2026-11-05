"""Current FTB rank definitions in a disposable, stopped Linux world return."""

import hashlib
import json
import os
import tarfile

from omk.dj2_commands_lab import _response
from omk.forge_player import LabPlayer

RANKS = "local/ftbutilities/ranks.txt"
MAX_FILE = 1024**2


def read_ranks(archive):
    """Read only the allowlisted file; FTB remains the authority for its grammar."""
    if archive.is_symlink() or archive.stat().st_size > 2 * MAX_FILE:
        raise ValueError("Invalid current-ranks archive")
    data = None
    with tarfile.open(archive, "r:") as tar:
        for member in tar:
            if (
                data is not None
                or member.name != RANKS
                or not member.isfile()
                or member.issparse()
                or not 0 < member.size <= MAX_FILE
            ):
                raise ValueError("Invalid current-ranks archive entry")
            data = tar.extractfile(member).read(MAX_FILE + 1)
    try:
        if data is None or not data.decode("utf-8").strip() or b"\0" in data:
            raise ValueError("Invalid rank definitions")
    except ValueError, UnicodeError:
        raise ValueError("Invalid current-ranks data") from None
    return data, hashlib.sha256(data).hexdigest()


def stage_ranks(archive, destination, *, lab):
    target = destination / RANKS
    pending = target.with_name("ranks.txt.current-policy")
    if (
        not lab.name.startswith("recovery-lab-")
        or lab.is_symlink()
        or destination != lab / "recovery-lab-return/server"
        or not (lab / "full-return-staged.json").is_file()
        or not (lab / "current-access-staged.json").is_file()
        or archive != lab / "current-ranks-before/ranks.tar"
        or target.resolve() != target.absolute()
        or not target.is_file()
        or target.stat().st_size > MAX_FILE
        or pending.exists()
        or pending.is_symlink()
    ):
        raise ValueError("Expected untouched disposable rank definitions")
    data, digest = read_ranks(archive)
    result = {
        "lab_only": True,
        "file": RANKS,
        "source_sha256": digest,
        "replacement_default_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        "historical_memberships_reconciled": False,
    }
    with (lab / "current-ranks-plan.json").open("x", encoding="utf-8") as out:
        json.dump(result, out, indent=2)
    # Replace only the freshly staged runtime's default, never the source file.
    with pending.open("xb") as out:
        out.write(data)
    pending.chmod(0o600)
    if pending.read_bytes() != data:
        raise ValueError("Current-ranks temporary readback failed")
    os.replace(pending, target)
    if target.read_bytes() != data:
        raise ValueError("Current-ranks final readback failed")
    with (lab / "current-ranks-staged.json").open("x", encoding="utf-8") as out:
        json.dump(result, out, indent=2)
    return result


def seed_ranks(console, expect):
    console("ranks setp player ftbutilities.homes.max 1")
    expect(True, "current_rank_fixture_command_issued")


def verify_ranks(client, session, mods, console, expect):
    # Historical backuporigin consumes one home. The fresh runtime default is 3;
    # the current policy is 1. The player was explicitly deopped by verify_access.
    with LabPlayer(client, session, 25576, mods) as first:
        _response(first, "/sethome policycheck", "ftbutilities.lang.homes.limit")
        expect(True, "current_home_quota_survives_historical_world_return")
        console("ranks setp player ftbutilities.homes.max 2")
        _response(first, "/sethome policycheck", "ftbutilities.lang.homes.set")
        expect(True, "explicit_rank_increase_allows_second_home")
        _response(first, "/delhome policycheck", "ftbutilities.lang.homes.del")
        console("ranks setp player ftbutilities.homes.max 1")
        _response(first, "/sethome policycheck", "ftbutilities.lang.homes.limit")
        expect(True, "explicit_rank_decrease_is_enforced_again")
