"""Read-only saved dimension-link inventory, never a universal portal approval.

Known integer links and RFTools receiver IDs are reported, not silently cleared.
Opaque serializers still require adapters before an owner reset can be approved.
"""

import hashlib
import json
import re
from pathlib import Path

from omk.backups.ftb_restore_authority import nbt
from omk.shared.nbt import Tag
from omk.worlds import (
    enderutilities_reset as ender,
    forge112_regions as anvil,
)
from omk.worlds.reset import (
    resource_reset_inventory as audit,
    rftools_reset as rftools,
)
from omk.worlds.reset.dimension_reset import omitted
from omk.worlds.reset.resource_reset_landing import world_path


def _world_primer_counts(root):
    value = root.get("DimLoadCounts")
    if value is None:
        return False
    if value.kind != 9:
        raise ValueError("Unexpected World Primer dimension-count data")
    kind, entries = value.value
    if kind != 10 and (kind != 0 or entries):
        raise ValueError("Unexpected World Primer dimension-count rows")
    found = set()
    for row in entries:
        fields = row.value
        if (
            set(fields) != {"Dim", "Count"}
            or fields["Dim"].kind != 3
            or fields["Count"].kind != 3
            or fields["Count"].value < 0
            or fields["Dim"].value in found
        ):
            raise ValueError("Unexpected World Primer dimension-count row")
        found.add(fields["Dim"].value)
    return True


def inspect_links(  # noqa: PLR0912, PLR0915 - bounded read-only record traversal
    server: Path,
    world_name: str,
    dimension: int,
    files,
    *,
    max_chunks=100000,
    nonportal_patterns=(),
    enderutilities_targets=False,
    rftools_transport=False,
    region_edits=None,
    reset=None,
):
    if type(max_chunks) is not int or not 1 <= max_chunks <= 1000000:
        raise ValueError("Invalid mod reference scan budget")
    world, prefix = world_path(server, world_name), world_name + "/"
    records = []
    receiver_ids = set()
    known_receiver_ids = set()
    findings, opaque = [], []
    chunks_read, nodes, nonportal = 0, 0, 0
    eligible, reviewed = set(), 0
    rftools_eligible, rftools_reviewed = set(), 0
    spawn_receiver = None

    def add(file, path, kind):
        nonlocal reviewed, rftools_reviewed
        if len(findings) >= 2000:
            raise ValueError("Too many dimension references for reviewed reset")
        finding = {"file": file, "nbt_path": path, "kind": kind}
        if kind == "enderutilities.target" and path in eligible:
            finding["staging_adapter"] = ender.ADAPTER
            reviewed += 1
        elif kind == "rftools.spawn-receiver":
            finding["staging_adapter"] = audit.RFTOOLS_SPAWN_ADAPTER
            reviewed += 1
        elif path in rftools_eligible and kind in {
            "dimension-tag",
            "rftools.receiver-id",
        }:
            finding["staging_adapter"] = rftools.ADAPTER
            rftools_reviewed += 1
            reviewed += 1
        findings.append(finding)

    for name in sorted(files):
        if (
            not isinstance(name, str)
            or "\\" in name
            or any(part in {"", ".", ".."} for part in name.split("/"))
        ):
            raise ValueError("Noncanonical reference input path")
        if not name.startswith(prefix) or omitted(name, world_name, dimension, reset):
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

    definition = None
    if reset and "rftools_identity" in reset:
        _label, _root, definitions = audit._rftools_registry(server, world_name)
        definition = definitions.get(dimension)
        if (
            definition is None
            or audit.rftools_identity(definition) != reset["rftools_identity"]
        ):
            raise ValueError("The selected RFTools dimension changed")

    # Receiver numbers are references too. A porter need not contain a dimension.
    registry_name = prefix + audit.RFTOOLS_DESTINATIONS
    registry_paths = set()
    if registry_name in files:
        raw = nbt(audit._read(server / registry_name, world))
        data = anvil.value(raw, "data", 10)
        receiver_ids, known_receiver_ids = rftools.destination_ids(data, dimension)
        if definition is not None:
            if rftools_transport:
                registry_paths = {
                    f"/data/destinations/{index}/dim"
                    for index in rftools.selected_positions(
                        data, dimension, registry=True
                    )
                }
            else:
                spawn_receiver = audit.rftools_spawn_destination(
                    definition, anvil.compounds(data, "destinations")
                )
    block_registry = (
        anvil.block_registry(nbt(audit._read(world / "level.dat", world)))
        if rftools_transport and receiver_ids
        else None
    )

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
            dialer = context in {
                "rftools:simple_dialer",
                "minecraft:rftools_simple_dialer",
            }
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
                # Keep diagnostic paths unambiguous before adapter admission.
                here = path + "/" + key.replace("~", "~0").replace("/", "~1")
                normalized = key.replace("_", "").lower()
                dim_key = (
                    normalized
                    in {
                        "dim",
                        "dimension",
                        "dimensionid",
                        "dimid",
                    }
                    or normalized.endswith(
                        (
                            "targetdim",
                            "targetdimension",
                            "destdim",
                            "destinationdimension",
                        )
                    )
                    or (dialer and key == "transDim")
                )
                if dim_key and tag.kind in (2, 3, 4) and tag.value == dimension:
                    kind = (
                        "enderutilities.target"
                        if context.startswith("enderutilities:") and "/Target/" in here
                        else "dimension-tag"
                    )
                    if (
                        spawn_receiver is not None
                        and file == audit.RFTOOLS_DESTINATIONS
                        and here == f"/data/destinations/{spawn_receiver}/dim"
                    ):
                        kind = "rftools.spawn-receiver"
                    add(file, here, kind)
                if (
                    (context.startswith("rftools:") or dialer)
                    and tag.kind == 3
                    # The native -1 sentinel applies to receivers and porters only.
                    and not (tag.value == -1 and key not in {"destId", "receiver"})
                    and (
                        key in {"destId", "destinationId"}
                        or (dialer and key == "receiver")
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

    patch_bytes = 0
    for name, kind in records:
        eligible = set()
        rftools_eligible = set()
        relative = name.removeprefix(prefix)
        if kind == "region":
            region = anvil.Region(server / name, world)
            replacements = []
            for index in region.locations:
                chunks_read += 1
                if chunks_read > max_chunks:
                    raise ValueError("Mod link scan chunk budget exceeded")
                label, root, raw = region.record(index)
                chunk = anvil.value(root, "Level", 10)
                edits = (
                    rftools.transmitter_updates(chunk, receiver_ids, block_registry)
                    if block_registry is not None
                    else {}
                )
                rftools_eligible = {
                    f"chunk/{index}/TileEntities/{slot}/destId" for slot in edits
                }
                if edits:
                    anvil.check_editable(label, root, raw)
                    tile_kind, tiles = chunk["TileEntities"].value
                    updated_tiles = [
                        Tag(10, edits[slot]) if slot in edits else row
                        for slot, row in enumerate(tiles)
                    ]
                    updated_chunk = {
                        **chunk,
                        "TileEntities": Tag(9, (tile_kind, updated_tiles)),
                    }
                    replacement = region.replacement(
                        index, label, {**root, "Level": Tag(10, updated_chunk)}
                    )
                    patch_bytes += len(replacement[1])
                    if patch_bytes > audit.ftb.MAX_TOTAL:
                        raise ValueError("Region edits exceed reviewed memory budget")
                    replacements.append(replacement)
                for key in ("TileEntities", "Entities"):
                    # Block/light arrays do not encode teleport bindings.
                    walk(chunk[key], relative, f"chunk/{index}/{key}")
            if replacements and region_edits is not None:
                region_edits[name] = anvil.RegionEdit(tuple(sorted(replacements)))
        else:
            try:
                root = nbt(audit._read(server / name, world))
            except ValueError, UnicodeError, KeyError:
                opaque.append(relative)
                continue
            skip = (
                {"Dimension", "SpawnDimension", "Spawns"} if kind == "player" else set()
            )
            if re.fullmatch(r"playerdata/[a-f0-9-]{36}\.(?:dat|dat_old)", relative):
                if enderutilities_targets:
                    _candidate, paths = ender.unbind_player_targets(root, dimension)
                    eligible = set(paths)
                if rftools_transport:
                    _candidate, paths = rftools.unbind_player_targets(
                        root, dimension, receiver_ids
                    )
                    rftools_eligible = set(paths)
            elif name == registry_name:
                rftools_eligible = registry_paths
            if Path(relative).name in {"level.dat", "level.dat_old"}:
                skip.add("FML")  # Registry IDs are not bound teleport destinations.
            if relative == "worldprimer/data_tracker.nbt" and _world_primer_counts(
                root
            ):
                skip.add(
                    "DimLoadCounts"
                )  # Audited counters, not transport destinations.
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
        **({"rftools_spawn_receiver": True} if spawn_receiver is not None else {}),
        **(
            {"rftools_transport_references": rftools_reviewed}
            if rftools_reviewed
            else {}
        ),
        "chunks_read": chunks_read,
        "records_read": len(records),
        "opaque_record_count": len(opaque),
        "opaque_examples": opaque[:16],
        "nonportal_binary_records": nonportal,
        "world_changes": False,
        "coverage_complete": False,
        "portal_adapters_reviewed": False,
    }
