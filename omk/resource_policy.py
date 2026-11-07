"""Offline resource-world bundle. No runtime writes, downloads, or world deletion."""

import hashlib
import json
import os
import re
from pathlib import Path

from omk.dj2_rtp_policy import rtp_plan, write_rtp_policy
from omk.dj2_spawn_policy import spawn_plan
from omk.profiles import PROJECT_ROOT
from omk.resource_generation import additional_generator_patches
from omk.territory_policy import territory_plan, write_territory_policy

PROFILE = PROJECT_ROOT / "profiles/server-defaults/dj2/resource-world.json"


def _integer(values, key, default, low, high):
    raw = values.get(key, str(default))
    if not isinstance(raw, str) or not re.fullmatch(r"-?[0-9]{1,19}", raw):
        raise ValueError("Invalid resource setting: " + key)
    value = int(raw)
    if not low <= value <= high:
        raise ValueError("Resource setting out of range: " + key)
    return value


def resource_plan(environ=None):
    values = os.environ if environ is None else environ
    profile = json.loads(PROFILE.read_text(encoding="utf-8"))
    dimension = _integer(
        values, "OMK_DJ2_RESOURCE_DIMENSION", profile["dimension"], -32000, -2
    )
    if dimension in profile["reserved_dimensions"]:
        raise ValueError("Resource dimension overlaps a DJ2 dimension")
    radius = _integer(values, "OMK_DJ2_RESOURCE_SPAWN_RADIUS", 100, 16, 512)
    rtp = rtp_plan(values)
    rows = rtp["worlds"]
    if any(row["id"] == dimension for row in rows) or len(rows) >= 8:
        raise ValueError("Resource dimension conflicts with RTP profile")
    main_spawn = spawn_plan(values)
    resource_spawn = spawn_plan({"OMK_DJ2_SPAWN_RADIUS": str(radius)})
    territory_plan(values)
    diameter = _integer(values, "OMK_DJ2_RESOURCE_DIAMETER", 16384, 512, 100000)
    if diameter <= 2 * (radius + 16) or rtp["minimum"] >= min(
        rtp["maximum"], diameter * rtp["border_percent"] / 200 - 2
    ):
        raise ValueError("Resource border leaves no safe spawn/RTP range")
    if main_spawn["chunks"] + resource_spawn["chunks"] > 10000:
        raise ValueError("Combined spawn plan exceeds the Core bound")
    return {
        "schema": 1,
        "identity": profile["identity"],
        "dimension": dimension,
        "seed": _integer(values, "OMK_DJ2_RESOURCE_SEED", 0, -(2**63), 2**63 - 1),
        "diameter": diameter,
        "spawn_radius": radius,
        "main_spawn_radius": main_spawn["radius"],
        "generator": "default",
        "provider": "fi.dy.masa.justenoughdimensions.world.WorldProviderSurfaceJED",
        "command": "resource",
        "return_command": "spawn",
        "ftb_timer": "SPAWN",
        "search_radius": min(64, radius - 2),
        "chunk_loads": _integer(
            values, "OMK_DJ2_RESOURCE_SEARCH_CHUNK_LOADS", 64, 16, 64
        ),
        "rtp_worlds": [
            *rows,
            {"id": dimension, "mode": "surface", "min_y": 1, "max_y": 250},
        ],
        "artifact": profile["artifact"],
        "ready_for_players": False,
        "required_capabilities": [
            "ftb.resource",
            "ftb.spawn",
            "ftb.rtp",
            "ftb.territories",
        ],
    }


def jed_dimension(plan):
    return {
        "dimensions": [
            {
                "dim": plan["dimension"],
                "override": False,
                "unregister": False,
                "temporary_dimension": False,
                "load_on_start": False,
                "normal_biomes": True,
                "dimensiontype": {
                    "id": plan["dimension"],
                    "name": "omk_resource",
                    "suffix": "_omk_resource",
                    "keeploaded": False,
                    "worldprovider": "WorldProviderSurfaceJED",
                },
                "worldinfo_onetime": {
                    "RandomSeed": plan["seed"],
                    "generatorName": "default",
                    "generatorVersion": 1,
                    "generatorOptions": "",
                    "MapFeatures": True,
                    "GameType": 0,
                    "BorderCenterX": 0.0,
                    "BorderCenterZ": 0.0,
                    "BorderSize": float(plan["diameter"]),
                },
                "jed": {"CanRespawnHere": False, "RespawnDimension": 0},
            }
        ],
    }


def resource_generator_patch(source_config: Path, dimension: int):
    """Read the selected pack config; return a patched copy without editing it."""
    source = Path(source_config) / "undergroundbiomes.cfg"
    if (
        not source.is_file()
        or source.stat().st_size > 256 * 1024
        or any(p.is_symlink() or p.is_junction() for p in (source, *source.parents))
    ):
        raise ValueError("A regular Underground Biomes source config is required")
    raw = source.read_bytes()
    text = raw.decode("utf-8")
    pattern = r"(?m)^([ \t]*S:IncludedDimensions=)([^\r\n]*)(?=\r?$)"
    matches = list(re.finditer(pattern, text))
    if len(matches) != 1:
        raise ValueError("Unknown Underground Biomes dimension configuration")
    match = matches[0]
    parts = [part.strip() for part in match[2].split(",")]
    if not 1 <= len(parts) <= 64 or any(
        not re.fullmatch(r"-?[0-9]{1,10}", part) for part in parts
    ):
        raise ValueError("Unknown Underground Biomes dimension configuration")
    ids = [int(part) for part in parts]
    if len(ids) != len(set(ids)) or any(not -(2**31) <= value < 2**31 for value in ids):
        raise ValueError("Unknown Underground Biomes dimension configuration")
    patched = text
    if dimension not in ids:
        patched = (
            text[: match.start(2)]
            + ",".join(map(str, [*ids, dimension]))
            + text[match.end(2) :]
        )
    return patched, {
        "file": "config/undergroundbiomes.cfg",
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "output_sha256": hashlib.sha256(patched.encode("utf-8")).hexdigest(),
        "dimension_added": dimension,
    }


def resource_generator_bundle(source_config, plan):
    """Validate all selected pack inputs before creating any output directory."""
    text, ub = resource_generator_patch(source_config, plan["dimension"])
    patches, metadata = additional_generator_patches(source_config, plan["dimension"])
    plan["generator_patch"] = ub
    plan["generation_patches"] = [ub, *metadata]
    return {"undergroundbiomes.cfg": text.encode("utf-8"), **patches}


def prepare_resource_bundle(
    output: Path, environ=None, *, source_config: Path | None = None
):
    values = os.environ if environ is None else environ
    plan = resource_plan(values)
    patches = {}
    if source_config is not None:
        patches = resource_generator_bundle(source_config, plan)
    else:
        plan["generator_patch"] = {"pending": True}
    output = Path(output)
    if not output.parent.is_dir() or any(
        p.is_symlink() or p.is_junction() for p in (output, *output.parents)
    ):
        raise ValueError("A real offline output parent is required")
    # Exclusive directory claim. An incomplete bundle never gets bundle.json.
    output.mkdir()
    config = output / "config"
    jed = config / "justenoughdimensions"
    jed.mkdir(parents=True)
    for relative, content in patches.items():
        target = config / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    (jed / "dimensions.json").write_text(
        json.dumps(jed_dimension(plan), indent=2) + "\n", encoding="utf-8"
    )
    (jed / "justenoughdimensions.cfg").write_text(
        "ConfigHandling {\n B:copyDimensionConfigToWorld=false\n B:copyMainConfigToWorld=false\n"
        " B:usePerWorldDimensionConfig=false\n B:usePerWorldMainConfig=false\n}\n"
        "Generic {\n B:enableCommandRedirecting=false\n B:enableLoggingInfo=true\n"
        " B:enableSeparateWorldInfo=true\n B:enableSeparateWorldBorders=true\n"
        " B:enableReplacingRegisteredDimensions=false\n B:enableUnregisteringDimensions=false\n}\n",
        encoding="ascii",
    )
    (config / "omkalitycore-resource.properties").write_text(
        "schema=1\n"
        + "\n".join(
            f"{key}={plan[key]}" for key in ("dimension", "seed", "command", "identity")
        )
        + "\njed_config_sha256="
        + hashlib.sha256((jed / "dimensions.json").read_bytes()).hexdigest()
        + f'\nspawn_x=0\nspawn_z=0\nsearch_radius={plan["search_radius"]}\n'
        + f'search_step=8\nchunk_loads={plan["chunk_loads"]}\n',
        encoding="ascii",
    )
    a, b = plan["main_spawn_radius"], plan["spawn_radius"]
    (config / "omkalitycore-spawn.properties").write_text(
        f'version=1\nzones=0:{-a}:{a}:{-a}:{a};{plan["dimension"]}:{-b}:{b}:{-b}:{b}\n',
        encoding="ascii",
    )
    profiles = output / "profiles"
    profiles.mkdir()
    rtp = profiles / "rtp-worlds.json"
    rtp.write_text(
        json.dumps({"version": 1, "worlds": plan["rtp_worlds"]}, indent=2) + "\n",
        encoding="utf-8",
    )
    write_rtp_policy(config, {**values, "OMK_DJ2_RTP_PROFILE": str(rtp)})
    write_territory_policy(config, values)
    files = {
        p.relative_to(output).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(output.rglob("*"))
        if p.is_file()
    }
    manifest = {
        "schema": 1,
        "complete": True,
        "plan": plan,
        "files": files,
        "world_changes": False,
    }
    with (output / "bundle.json").open("x", encoding="utf-8") as file:
        json.dump(manifest, file, ensure_ascii=False, indent=2)
        file.write("\n")
    return manifest
