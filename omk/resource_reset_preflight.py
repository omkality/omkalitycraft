"""Read-only, profile-pinned geometry and known mod-link preflight.

This is deliberately not a universal portal audit or permission to start/wipe.
"""

import hashlib
import json
import os
from pathlib import Path

from omk.cold_backup_worker import digest
from omk.fs import regular
from omk.profiles import PROJECT_ROOT
from omk.resource_reset_inventory import validate_dimension
from omk.resource_reset_landing import NoReviewedLanding, select_landing, world_path
from omk.resource_reset_links import inspect_links
from omk.stopped_world_backup import inventory

PROFILE = PROJECT_ROOT / "profiles/server-defaults/dj2/reset-preflight.json"
LIMITS = {
    "landing_radius": ("OMK_RESET_LANDING_RADIUS", 16, 0, 32),
    "landing_vertical": ("OMK_RESET_LANDING_VERTICAL", 8, 0, 32),
    "landing_chunks": ("OMK_RESET_LANDING_CHUNK_BUDGET", 32, 1, 256),
    "reference_chunks": ("OMK_RESET_REFERENCE_CHUNK_BUDGET", 100000, 1, 1000000),
}


def settings(environment=None):
    env = os.environ if environment is None else environment
    result = {}
    for key, (name, default, low, high) in LIMITS.items():
        raw = env.get(name, str(default))
        if not isinstance(raw, str) or not raw.isascii() or not raw.isdecimal():
            raise ValueError("Invalid preflight option: " + name)
        number = int(raw)
        if not low <= number <= high:
            raise ValueError("Preflight option outside bounds: " + name)
        result[key] = number
    return result


def options_checked(options):
    if not isinstance(options, dict) or set(options) != set(LIMITS):
        raise ValueError("Invalid preflight option keys")
    for key, value in options.items():
        _, _, low, high = LIMITS[key]
        if type(value) is not int or not low <= value <= high:
            raise ValueError("Invalid preflight option: " + key)
    return dict(options)


def artifacts(server, profile):
    actual = {}
    for name, expected in profile["artifacts"].items():
        path = server / "mods" / name
        if not regular(path, server) or path.stat().st_size > 128 * 1024**2:
            raise ValueError("Missing/linked preflight artifact: " + name)
        with path.open("rb") as stream:
            actual[name] = hashlib.file_digest(stream, "sha256").hexdigest()
        if actual[name] != expected:
            raise ValueError("Unreviewed preflight artifact: " + name)
    return actual


def preflight(
    server: Path,
    world_name: str,
    dimension: int,
    *,
    options=None,
    world_max_bytes=1024**4,
):
    if type(world_max_bytes) is not int or not 1 <= world_max_bytes <= 1024**4:
        raise ValueError("Invalid preflight world byte budget")
    validate_dimension(dimension)
    world = world_path(server, world_name)
    policy = options_checked(settings() if options is None else options)
    raw = PROFILE.read_bytes()
    profile = json.loads(raw)
    pins = artifacts(server, profile)

    def snapshot():
        return inventory(
            world,
            world_name=world_name,
            max_expanded_bytes=world_max_bytes,
            path_policy="linux-server",
        )

    before = snapshot()
    try:
        landing = {
            "found": True,
            **select_landing(
                server,
                world_name,
                radius=policy["landing_radius"],
                vertical=policy["landing_vertical"],
                max_chunks=policy["landing_chunks"],
            ),
        }
    except NoReviewedLanding:
        landing = {"found": False, "world_changes": False, "generation": False}
    links = inspect_links(
        server,
        world_name,
        dimension,
        before,
        max_chunks=policy["reference_chunks"],
        nonportal_patterns=profile["nonportal_binary_patterns"],
    )
    if (
        snapshot() != before
        or artifacts(server, profile) != pins
        or PROFILE.read_bytes() != raw
    ):
        raise ValueError("Preflight world/runtime changed during inspection")
    return {
        "schema": 1,
        "adapter": profile["adapter"],
        "dimension": dimension,
        "profile_sha256": hashlib.sha256(raw).hexdigest(),
        "artifacts_sha256": digest(pins),
        "world_inventory_sha256": hashlib.sha256(
            json.dumps(before, sort_keys=True).encode()
        ).hexdigest(),
        "policy": policy,
        "landing": landing,
        "links": links,
        "can_stage_data": bool(
            landing["found"]
            and not links["finding_count"]
            and not links["opaque_record_count"]
        ),
        "world_changes": False,
        "ready_for_start": False,
        "portal_adapters_reviewed": False,
    }
