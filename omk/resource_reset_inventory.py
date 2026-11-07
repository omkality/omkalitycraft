"""Read-only DJ2 reference audit. Never a reset plan, migration or apply gate."""

import hashlib
import json
import re
from pathlib import Path
from uuid import UUID

from launcher.nbt import Tag
from omk import ftb_restore_authority as ftb
from omk.fs import regular
from omk.profiles import PROJECT_ROOT
from omk.stopped_world_backup import inventory

PROFILE = PROJECT_ROOT / "profiles/server-defaults/dj2/resource-world.json"


def validate_dimension(dimension):
    profile = json.loads(PROFILE.read_bytes())
    if (
        type(dimension) is not int
        or not -32000 <= dimension <= -2
        or dimension in profile["reserved_dimensions"]
    ):
        raise ValueError("Dimension is not an allowlisted resource candidate")
    return profile


def _read(path, root, maximum=2 * 1024**2):
    if not regular(path, root) or path.stat().st_size > maximum:
        raise ValueError("Missing, linked or oversized inspection input")
    with path.open("rb") as source:
        data = source.read(maximum + 1)
    if len(data) > maximum:
        raise ValueError("Inspection input exceeded limit")
    return data


def _properties(path, root):
    values = {}
    for raw in _read(path, root, 4096).decode("ascii").splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", "!")):
            continue
        if line.count("=") != 1:
            raise ValueError("Unreviewed resource property format")
        key, value = line.split("=", 1)
        if key in values or not key or "\\" in line:
            raise ValueError("Duplicate or escaped resource property")
        values[key] = value
    return values


def _tag(root, key, kind):
    value = root.get(key)
    if not isinstance(value, Tag) or value.kind != kind:
        raise ValueError("Unreviewed dimension-reference field")
    return value.value


def _list(root, key, child):
    kind, entries = _tag(root, key, 9)
    if kind != child and not (kind == 0 and not entries):
        raise ValueError("Unreviewed dimension-reference list")
    return [v.value for v in entries]


def _position_dimension(tag):
    if not isinstance(tag, Tag) or tag.kind != 11 or len(tag.value) not in (0, 3, 4):
        raise ValueError("Unreviewed FTB position")
    return None if not tag.value else (tag.value[3] if len(tag.value) == 4 else 0)


def _utilities_refs(data, dimension):
    homes = _tag(data, "Homes", 10)
    result = {
        "homes": sum(_position_dimension(v) == dimension for v in homes.values()),
        "legacy_back_death": 0,
    }
    if "LastDeath" in data:
        result["legacy_back_death"] += (
            _position_dimension(data["LastDeath"]) == dimension
        )
    if "teleportTracker" in data:
        for entry in _tag(data, "teleportTracker", 10).values():
            if entry.kind != 10:
                raise ValueError("Unreviewed FTB teleport tracker")
            result["legacy_back_death"] += (
                _tag(entry.value, "dimension", 3) == dimension
            )
    return result


def _policy(server, dimension, profile):
    policy = _properties(server / "config/omkalitycore-resource.properties", server)
    expected = {
        "schema",
        "dimension",
        "seed",
        "command",
        "identity",
        "jed_config_sha256",
        "spawn_x",
        "spawn_z",
        "search_radius",
        "search_step",
        "chunk_loads",
    }
    if (
        set(policy) != expected
        or policy["schema"] != "1"
        or policy["identity"] != profile["identity"]
        or policy["dimension"] != str(dimension)
        or not re.fullmatch(r"-?[0-9]{1,19}", policy["seed"])
        or not -(2**63) <= int(policy["seed"]) < 2**63
    ):
        raise ValueError("Resource identity or policy differs from requested dimension")
    raw = _read(server / "config/justenoughdimensions/dimensions.json", server, 65536)
    if hashlib.sha256(raw).hexdigest() != policy["jed_config_sha256"]:
        raise ValueError("Resource dimension configuration hash differs")
    rows = [v for v in json.loads(raw)["dimensions"] if v.get("dim") == dimension]
    if (
        len(rows) != 1
        or rows[0]["dimensiontype"].get("worldprovider") != "WorldProviderSurfaceJED"
        or rows[0]["dimensiontype"].get("require_exact_match") is not True
    ):
        raise ValueError("Unreviewed resource dimension provider")
    artifact = profile["artifact"]
    if (
        hashlib.sha256(
            _read(server / "mods" / artifact["filename"], server, 16 * 1024**2)
        ).hexdigest()
        != artifact["sha256"]
    ):
        raise ValueError("Unreviewed JED runtime")
    ftb.check_runtime(server)
    return policy


def inspect_resource(  # noqa: PLR0912, PLR0915 -- one bounded read-only audit
    server, world_name, dimension, *, world_max_bytes
):
    profile = validate_dimension(dimension)
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", world_name):
        raise ValueError("Invalid configured world root")
    server = Path(server).absolute()
    if server.resolve() != server or not server.is_dir():
        raise ValueError("Expected a regular source server root")
    policy = _policy(server, dimension, profile)
    world = server / world_name
    before = inventory(
        world,
        world_name=world_name,
        max_expanded_bytes=world_max_bytes,
        path_policy="linux-server",
    )
    expected = {
        "schema": "1",
        "identity": policy["identity"],
        "dimension": str(dimension),
        "seed": str(int(policy["seed"])),
    }
    if (
        _properties(world / "omk-resource-world.properties", world) != expected
        or _properties(world / f"DIM{dimension}/.omk-resource.properties", world)
        != expected
    ):
        raise ValueError("Resource ownership records differ")
    result = {
        "primary_player_records": 0,
        "primary_positions_in_resource": 0,
        "backup_positions_in_resource": 0,
        "player_spawn_references": 0,
        "opaque_player_files": 0,
        "mounted_player_records": 0,
        "ftb_homes": 0,
        "ftb_warps": 0,
        "ftb_legacy_back_death": 0,
        "resource_claimed_chunks": 0,
        "other_claimed_chunks": 0,
        "jed_player_dimensions": 0,
    }
    prefix = world_name + "/playerdata/"
    for name in before:
        if not name.startswith(prefix):
            continue
        leaf = name.removeprefix(prefix)
        match = re.fullmatch(r"([a-f0-9-]{36})\.(dat|dat_old)", leaf)
        if match is None:
            if leaf.endswith((".dat", ".dat_old")):
                raise ValueError("Unreviewed player record filename")
            result["opaque_player_files"] += 1
            continue
        uid = UUID(match[1])
        if str(uid) != match[1]:
            raise ValueError("Ambiguous player record identity")
        root = ftb.nbt(_read(server / name, world))
        saved = ((_tag(root, "UUIDMost", 4) & ((1 << 64) - 1)) << 64) | (
            _tag(root, "UUIDLeast", 4) & ((1 << 64) - 1)
        )
        if uid.int != saved:
            raise ValueError("Player record UUID differs from its filename")
        primary = match[2] == "dat"
        result["primary_player_records"] += primary
        key = (
            "primary_positions_in_resource"
            if primary
            else "backup_positions_in_resource"
        )
        result[key] += _tag(root, "Dimension", 3) == dimension
        if "SpawnDimension" in root:
            result["player_spawn_references"] += (
                _tag(root, "SpawnDimension", 3) == dimension
            )
        if "Spawns" in root:
            result["player_spawn_references"] += sum(
                _tag(x, "Dim", 3) == dimension for x in _list(root, "Spawns", 10)
            )
        result["mounted_player_records"] += "RootVehicle" in root
    records = ftb.read_staged(server, world_name=world_name)
    ftb.projection(records)  # Validate authority without changing the parsed records.
    for name, root in records.items():
        if name.startswith("players/"):
            data = _tag(_tag(root, "Data", 10), "ftbutilities", 10)
            refs = _utilities_refs(data, dimension)
            result["ftb_homes"] += refs["homes"]
            result["ftb_legacy_back_death"] += refs["legacy_back_death"]
    universe = records["universe.dat"]
    fake = _tag(_tag(_tag(universe, "FakePlayer", 10), "Data", 10), "ftbutilities", 10)
    refs = _utilities_refs(fake, dimension)
    result["ftb_homes"] += refs["homes"]
    result["ftb_legacy_back_death"] += refs["legacy_back_death"]
    warps = _tag(_tag(_tag(universe, "Data", 10), "ftbutilities", 10), "Warps", 10)
    result["ftb_warps"] = sum(
        _position_dimension(v) == dimension for v in warps.values()
    )
    claims_prefix = world_name + "/data/ftb_lib/teams/claimedchunks/"
    seen_claims = set()
    for name in before:
        if not name.startswith(claims_prefix):
            continue
        root = ftb.nbt(_read(server / name, world))
        for dim, entries in _tag(root, "ClaimedChunks", 10).items():
            if (
                not re.fullmatch(r"-?[0-9]{1,10}", dim)
                or str(int(dim)) != dim
                or entries.kind != 9
            ):
                raise ValueError("Unreviewed claim dimension or list")
            items = _list({"chunks": entries}, "chunks", 10)
            points = {(_tag(x, "x", 3), _tag(x, "z", 3)) for x in items}
            if len(points) != len(items):
                raise ValueError("Duplicate claimed chunk")
            identities = {(int(dim), x, z) for x, z in points}
            if seen_claims & identities:
                raise ValueError("Overlapping claim ownership records")
            seen_claims.update(identities)
            key = (
                "resource_claimed_chunks"
                if int(dim) == dimension
                else "other_claimed_chunks"
            )
            result[key] += len(items)
    tracker = world / "data/justenoughdimensions/data_tracker.dat"
    if tracker.exists() or tracker.is_symlink():
        root = ftb.nbt(_read(tracker, world))
        key = "PlayerData" if "PlayerData" in root else "PlayerDimensions"
        result["jed_player_dimensions"] = sum(
            _tag(v, "Dimension", 3) == dimension for v in _list(root, key, 10)
        )
    after = inventory(
        world,
        world_name=world_name,
        max_expanded_bytes=world_max_bytes,
        path_policy="linux-server",
    )
    if before != after:
        raise ValueError("Source world changed during read-only inspection")
    if _policy(server, dimension, profile) != policy:
        raise ValueError("Resource configuration changed during read-only inspection")
    return {
        "schema": 1,
        "adapter": "dj2-ftb5.4-jed1.6-inspection-v1",
        "world": world_name,
        "resource_identity": expected,
        "references": result,
        "world_files": len(before),
        "world_inventory_sha256": hashlib.sha256(
            json.dumps(before, sort_keys=True).encode()
        ).hexdigest(),
        "world_changes": False,
        "backup_verified": False,
        "reset_plan": False,
        "can_apply": False,
        "unreviewed": [
            "mod portals and other opaque dimension references",
            "evacuation/migration and rollback execution",
            "quest progress after reset",
        ],
    }
