"""Read-only saved dimension-link inventory, never a universal portal approval.

Known integer links and RFTools receiver IDs are reported, not silently cleared.
Opaque serializers still require adapters before an owner reset can be approved.
"""

import hashlib
import json
import re
from pathlib import Path

from launcher.nbt import Tag
from omk import (
    enderutilities_reset as ender,
    forge112_regions as anvil,
)
from omk.ftb_restore_authority import nbt
from omk.resource_reset_inventory import _read
from omk.resource_reset_landing import world_path


def inspect_links(  # noqa: PLR0912, PLR0915 - bounded read-only record traversal
    server: Path,
    world_name: str,
    dimension: int,
    files,
    *,
    max_chunks=100000,
    nonportal_patterns=(),
    enderutilities_targets=False,
):
    if type(max_chunks) is not int or not 1 <= max_chunks <= 1000000:
        raise ValueError("Invalid mod reference scan budget")
    world, prefix = world_path(server, world_name), world_name + "/"
    omitted = prefix + f"DIM{dimension}/"
    records = []
    receiver_ids = set()
    known_receiver_ids = set()
    findings, opaque = [], []
    chunks_read, nodes, nonportal = 0, 0, 0
    eligible, reviewed = set(), 0

    def add(file, path, kind):
        nonlocal reviewed
        if len(findings) >= 2000:
            raise ValueError("Too many dimension references for reviewed reset")
        finding = {"file": file, "nbt_path": path, "kind": kind}
        if kind == "enderutilities.target" and path in eligible:
            finding["staging_adapter"] = ender.ADAPTER
            reviewed += 1
        findings.append(finding)

    for name in sorted(files):
        if (
            not isinstance(name, str)
            or "\\" in name
            or any(part in {"", ".", ".."} for part in name.split("/"))
        ):
            raise ValueError("Noncanonical reference input path")
        if not name.startswith(prefix) or name.startswith(omitted):
            continue
        relative = name.removeprefix(prefix)
        if any(re.fullmatch(pattern, relative) for pattern in nonportal_patterns):
            nonportal += 1
            continue
        if name.endswith(".mca"):
            if "/region/" in name:
                records.append((name, "region"))
            continue
        if (
            name.startswith(prefix + "data/ftb_lib/")
            or relative == "data/justenoughdimensions/data_tracker.dat"
        ):
            continue  # Reviewed separately by the FTB/JED migration adapters.
        if name.endswith((".dat", ".dat_old", ".nbt")):
            records.append(
                (name, "player" if relative.startswith("playerdata/") else "data")
            )
        elif re.search(
            r"(?:portal|teleport|destination).*\.(?:json|db|bin)$", relative, re.I
        ):
            opaque.append(relative)

    # Receiver numbers are references too. A porter need not contain a dimension.
    registry_name = prefix + "data/TPDestinations.dat"
    if registry_name in files:
        raw = nbt(_read(server / registry_name, world))
        data = anvil.value(raw, "data", 10)
        last_id = anvil.value(data, "lastId", 3)
        if last_id < 0:
            raise ValueError("Invalid RFTools destination counter")
        seen = set()
        for row in anvil.compounds(data, "destinations"):
            target = anvil.value(row, "dim", 3)
            if "id" in row:
                number = anvil.value(row, "id", 3)
                if number < 0 or number > last_id or number in seen:
                    raise ValueError("Ambiguous RFTools destination IDs")
                seen.add(number)
                if target == dimension:
                    receiver_ids.add(number)
        known_receiver_ids.update(seen)

    def walk(  # noqa: PLR0912 - bounded serializer cases
        root, file, path="", context="", skip=frozenset(), depth=0
    ):
        nonlocal nodes
        nodes += 1
        if depth > 64 or nodes > 5000000:
            raise ValueError("Mod reference inventory exceeds traversal budget")
        if isinstance(root, dict):
            if "id" in root and root["id"].kind == 8:
                context = root["id"].value
            target = root.get("target")
            if (
                context.startswith("rftools:")
                and "porter" in context
                and "tpTimer" in root
                and (
                    not isinstance(target, Tag)
                    or target.kind != 3
                    or target.value == -1
                )
            ):
                # onUpdate resolves a target even after incomplete manual unbinding.
                add(file, path + "/tpTimer", "rftools.incomplete-porter-timer")
            for key, tag in root.items():
                if key in skip:
                    continue
                here = path + "/" + key
                normalized = key.replace("_", "").lower()
                dim_key = normalized in {
                    "dim",
                    "dimension",
                    "dimensionid",
                    "dimid",
                } or normalized.endswith(
                    ("targetdim", "targetdimension", "destdim", "destinationdimension")
                )
                if dim_key and tag.kind in (2, 3, 4) and tag.value == dimension:
                    kind = (
                        "enderutilities.target"
                        if context.startswith("enderutilities:") and "/Target/" in here
                        else "dimension-tag"
                    )
                    add(file, here, kind)
                if (
                    context.startswith("rftools:")
                    and tag.kind == 3
                    # Native receiver/porter -1 is unbound; transmitter destId is not.
                    and not (tag.value == -1 and key != "destId")
                    and (
                        key in {"destId", "destinationId"}
                        or (
                            "porter" in context
                            and re.fullmatch(r"target(?:[0-7])?", key)
                        )
                    )
                ):
                    if tag.value in receiver_ids:
                        add(file, here, "rftools.receiver-id")
                    elif tag.value not in known_receiver_ids:
                        add(file, here, "rftools.unresolved-receiver-id")
                if (
                    tag.kind in (11, 12)
                    and len(tag.value) == 4
                    and tag.value[-1] == dimension
                    and normalized
                    in {"target", "destination", "position", "coordinates"}
                ):
                    add(file, here, "dimension-tuple")
                walk(tag, file, here, context, depth=depth + 1)
        elif isinstance(root, Tag):
            if root.kind == 10:
                walk(root.value, file, path, context, depth=depth + 1)
            elif root.kind == 9:
                for index, child in enumerate(root.value[1]):
                    walk(child, file, path + "/" + str(index), context, depth=depth + 1)

    for name, kind in records:
        eligible = set()
        relative = name.removeprefix(prefix)
        if kind == "region":
            region = anvil.Region(server / name, world)
            for index in region.locations:
                chunks_read += 1
                if chunks_read > max_chunks:
                    raise ValueError("Mod link scan chunk budget exceeded")
                chunk = region.chunk(index)
                for key in ("TileEntities", "Entities"):
                    # Block/light arrays do not encode teleport bindings.
                    walk(chunk[key], relative, f"chunk/{index}/{key}")
        else:
            try:
                root = nbt(_read(server / name, world))
            except ValueError, UnicodeError, KeyError:
                opaque.append(relative)
                continue
            skip = (
                {"Dimension", "SpawnDimension", "Spawns"} if kind == "player" else set()
            )
            if enderutilities_targets and re.fullmatch(
                r"playerdata/[a-f0-9-]{36}\.(?:dat|dat_old)", relative
            ):
                _candidate, paths = ender.unbind_player_targets(root, dimension)
                eligible = set(paths)
            if Path(relative).name in {"level.dat", "level.dat_old"}:
                skip.add("FML")  # Registry IDs are not bound teleport destinations.
            walk(root, relative, skip=skip)
    return {
        "schema": 1,
        "dimension": dimension,
        "finding_count": len(findings),
        "handled_finding_count": reviewed,
        "unhandled_finding_count": len(findings) - reviewed,
        "findings_sha256": hashlib.sha256(
            json.dumps(findings, sort_keys=True).encode()
        ).hexdigest(),
        "examples": findings[:32],
        "rftools_resource_receiver_ids": len(receiver_ids),
        "chunks_read": chunks_read,
        "records_read": len(records),
        "opaque_record_count": len(opaque),
        "opaque_examples": opaque[:16],
        "nonportal_binary_records": nonportal,
        "world_changes": False,
        "coverage_complete": False,
        "portal_adapters_reviewed": False,
    }
