"""Binary-save fault controls; these tests do not claim a native game boot."""

import gzip
import hashlib
import json
import struct
import zlib

import pytest

from launcher.nbt import Tag, write_nbt
from omk import (
    forge112_regions as anvil,
    resource_reset_landing as landing,
    resource_reset_links as links,
    resource_reset_preflight as preflight,
)
from omk.stopped_world_backup import inventory


def compound_list(rows):
    return Tag(9, (10, [Tag(10, row) for row in rows]))


def encoded(path, root):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(gzip.compress(write_nbt("", root), mtime=0))


def region_write(world, chunk, *, codec=2, coordinates=(0, 0)):
    cx, cz = coordinates
    path = world / "region" / f"r.{cx // 32}.{cz // 32}.mca"
    path.parent.mkdir(exist_ok=True)
    packed = zlib.compress(write_nbt("", {"Level": Tag(10, chunk)}))
    body = struct.pack(">IB", len(packed) + 1, codec) + packed
    sectors = (len(body) + 4095) // 4096
    header = bytearray(8192)
    index = cx % 32 + 32 * (cz % 32)
    header[index * 4 : index * 4 + 4] = bytes([0, 0, 2, sectors])
    path.write_bytes(header + body + b"\0" * (4096 * sectors - len(body)))
    return path


@pytest.fixture
def saved(tmp_path, monkeypatch):
    server, world = tmp_path / "server", tmp_path / "server/world"
    world.mkdir(parents=True)
    chunk = {
        "xPos": Tag(3, 0),
        "zPos": Tag(3, 0),
        "TerrainPopulated": Tag(1, 1),
        "LightPopulated": Tag(1, 1),
        "TileEntities": compound_list([]),
        "Entities": compound_list([]),
        "Sections": compound_list(
            [
                {
                    "Y": Tag(1, 4),
                    "Blocks": Tag(7, b"\0" * 4096),
                    "Data": Tag(7, b"\0" * 2048),
                }
            ]
        ),
    }
    # Saved floor at Y=69, feet at 70. Registry IDs intentionally differ from vanilla.
    section = chunk["Sections"].value[1][0].value
    blocks = bytearray(section["Blocks"].value)
    blocks[5 * 256 : 6 * 256] = bytes([42]) * 256
    section["Blocks"].value = bytes(blocks)
    root = {
        "Data": Tag(
            10,
            {
                "SpawnX": Tag(3, 8),
                "SpawnY": Tag(3, 70),
                "SpawnZ": Tag(3, 8),
                "BorderCenterX": Tag(6, 0.0),
                "BorderCenterZ": Tag(6, 0.0),
                "BorderSize": Tag(6, 1000.0),
                "BorderSizeLerpTime": Tag(4, 0),
            },
        ),
        "FML": Tag(
            10,
            {
                "Registries": Tag(
                    10,
                    {
                        "minecraft:blocks": Tag(
                            10,
                            {
                                "ids": compound_list(
                                    [
                                        {"K": Tag(8, "minecraft:air"), "V": Tag(3, 0)},
                                        {
                                            "K": Tag(8, "minecraft:stone"),
                                            "V": Tag(3, 42),
                                        },
                                        {
                                            "K": Tag(8, "minecraft:magma"),
                                            "V": Tag(3, 43),
                                        },
                                    ]
                                )
                            },
                        )
                    },
                )
            },
        ),
    }
    encoded(world / "level.dat", root)
    encoded(world / "data/ftb_lib/teams/omk_spawn.dat", {"Type": Tag(8, "server")})
    claims = {
        "ClaimedChunks": Tag(
            10, {"0": compound_list([{"x": Tag(3, 0), "z": Tag(3, 0)}])}
        )
    }
    encoded(world / "data/ftb_lib/teams/claimedchunks/omk_spawn.dat", claims)
    region_write(world, chunk)
    mods = server / "mods"
    mods.mkdir()
    payload = b"explicit synthetic artifact, not a runtime"
    (mods / "reviewed.jar").write_bytes(payload)
    profile = tmp_path / "preflight.json"
    profile.write_text(
        json.dumps(
            {
                "schema": 1,
                "adapter": "synthetic-test-only",
                "artifacts": {"reviewed.jar": hashlib.sha256(payload).hexdigest()},
                "nonportal_binary_patterns": [
                    r"(?:[^/]+/)?RedstoneEther/(?:fmap|node[12])\.dat"
                ],
            }
        )
    )
    monkeypatch.setattr(preflight, "PROFILE", profile)
    return server, world, root, chunk


def test_saved_registry_geometry_and_read_only_proof(saved):
    server, world, _, _ = saved
    before = inventory(world, world_name="world")
    result = preflight.preflight(
        server, "world", -18000, options=preflight.settings({})
    )
    assert (
        result["world_inventory_sha256"]
        == hashlib.sha256(json.dumps(before, sort_keys=True).encode()).hexdigest()
    )  # Same identity contract as the existing owner inspection.
    assert result["landing"]["position"] == [8, 70, 8]
    assert result["can_stage_data"] and not result["ready_for_start"]
    assert (
        not result["portal_adapters_reviewed"]
        and not result["links"]["coverage_complete"]
    )
    assert inventory(world, world_name="world") == before


def test_blocked_spawn_selects_nearby_and_never_digs(saved):
    server, world, _, chunk = saved
    section = chunk["Sections"].value[1][0].value
    blocks = bytearray(section["Blocks"].value)
    blocks[6 * 256 + 8 * 16 + 8] = 42
    section["Blocks"].value = bytes(blocks)
    region_write(world, chunk)
    before = inventory(world, world_name="world")
    point = landing.select_landing(server, "world", vertical=0)["position"]
    assert point != [8, 70, 8] and point[1] == 70
    assert inventory(world, world_name="world") == before


@pytest.mark.parametrize(
    "fault",
    [
        "magma",
        "water_or_unknown",
        "no_floor",
        "tile",
        "entity",
        "unpopulated",
        "unlit",
        "claim",
        "border",
        "missing",
    ],
)
def test_unsafe_saved_spawn_is_not_approved(saved, fault):
    server, world, root, chunk = saved
    if fault in {"magma", "water_or_unknown", "no_floor"}:
        section = chunk["Sections"].value[1][0].value
        blocks = bytearray(section["Blocks"].value)
        blocks[5 * 256 + 8 * 16 + 8] = {
            "magma": 43,
            "water_or_unknown": 44,
            "no_floor": 0,
        }[fault]
        section["Blocks"].value = bytes(blocks)
    elif fault == "tile":
        chunk["TileEntities"] = compound_list(
            [{"x": Tag(3, 10), "y": Tag(3, 70), "z": Tag(3, 8)}]
        )
    elif fault == "entity":
        chunk["Entities"] = compound_list(
            [{"Pos": Tag(9, (6, [Tag(6, n) for n in (8.5, 70.0, 8.5)]))}]
        )
    elif fault in {"unpopulated", "unlit"}:
        chunk["TerrainPopulated" if fault == "unpopulated" else "LightPopulated"] = Tag(
            1, 0
        )
    elif fault == "claim":
        encoded(
            world / "data/ftb_lib/teams/claimedchunks/omk_spawn.dat",
            {"ClaimedChunks": Tag(10, {"0": compound_list([])})},
        )
    elif fault == "border":
        root["Data"].value["BorderSize"].value = 4.0
        encoded(world / "level.dat", root)
    region = region_write(world, chunk)
    if fault == "missing":
        region.unlink()  # Only this pytest-owned synthetic file.
    expected = ValueError if fault == "water_or_unknown" else landing.NoReviewedLanding
    with pytest.raises(expected):
        landing.select_landing(server, "world", radius=0, vertical=0)


@pytest.mark.parametrize(
    "corrupt", ["overlap", "codec", "coordinates", "compressed", "section"]
)
def test_malformed_anvil_never_becomes_safe_air(saved, corrupt):
    server, world, _, chunk = saved
    if corrupt == "coordinates":
        chunk["xPos"].value = 1
    if corrupt == "section":
        chunk["Sections"].value[1][0].value["Blocks"].value = b"short"
    region = region_write(world, chunk, codec=1 if corrupt == "codec" else 2)
    if corrupt in {"overlap", "compressed"}:
        raw = bytearray(region.read_bytes())
        if corrupt == "overlap":
            raw[4:8] = raw[:4]
        else:
            raw[8197:8202] = b"bogus"
        region.write_bytes(raw)
    with pytest.raises((ValueError, zlib.error)):
        landing.select_landing(server, "world", radius=0, vertical=0)


def test_extended_neid_ids_and_negative_region_coordinates(saved):
    _, world, _, chunk = saved
    chunk["xPos"].value, chunk["zPos"].value = -1, -33
    section = chunk["Sections"].value[1][0].value
    section["Blocks"].value = bytes([0xAB]) * 4096
    section["Add"] = Tag(7, bytes([0xCC]) * 2048)
    section["Add2"] = Tag(7, bytes([0xDD]) * 2048)
    path = region_write(world, chunk, coordinates=(-1, -33))
    loaded = anvil.Region(path, world).chunk(1023)
    assert anvil.block_id(anvil.sections(loaded), -1, 69, -513) == 0xDCAB


def link_save(world):
    encoded(
        world / "data/TPDestinations.dat",
        {
            "data": Tag(
                10,
                {
                    "lastId": Tag(3, 8),
                    "destinations": compound_list(
                        [
                            {"dim": Tag(3, -18000), "id": Tag(3, 7)},
                            {"dim": Tag(3, 0), "id": Tag(3, 8)},
                        ]
                    ),
                },
            )
        },
    )
    items = [
        {
            "id": Tag(8, "enderutilities:linkcrystal"),
            "tag": Tag(10, {"Target": Tag(10, {"Dim": Tag(3, -18000)})}),
        },
        {
            "id": Tag(8, "rftools:charged_porter"),
            "tag": Tag(10, {"target": Tag(3, 7), "Energy": Tag(3, 54321)}),
        },
        {"id": Tag(8, "rftools:charged_porter"), "tag": Tag(10, {"target": Tag(3, 8)})},
    ]
    encoded(
        world / "playerdata/native.dat",
        {"Dimension": Tag(3, -18000), "Inventory": compound_list(items)},
    )
    return items


def test_nested_dimension_and_receiver_links_block_auto_but_keep_items(saved):
    server, world, _, chunk = saved
    items = link_save(world)
    chunk["TileEntities"] = compound_list(
        [{"id": Tag(8, "rftools:transmitter"), "destId": Tag(3, 7)}]
    )
    region_write(world, chunk)
    # A modded world's retained region must also be searched.
    other = world / "DIM5"
    other.mkdir()
    region_write(other, chunk)
    before = inventory(world, world_name="world")
    result = links.inspect_links(server, "world", -18000, before)
    assert result["finding_count"] == 5  # Registry + two items + two tile entities.
    assert result["rftools_resource_receiver_ids"] == 1
    assert any(e["kind"] == "enderutilities.target" for e in result["examples"])
    assert any(e["file"].startswith("DIM5/") for e in result["examples"])
    assert inventory(world, world_name="world") == before
    assert items[1]["tag"].value["Energy"].value == 54321


def test_opaque_records_and_version_drift_refuse_auto_gate(saved):
    server, world, _, _ = saved
    (world / "data/unknownportal.dat").write_bytes(b"unknown serializer")
    ether = world / "RedstoneEther"
    ether.mkdir()
    (ether / "node1.dat").write_bytes(b"pinned nonportal format")
    result = preflight.preflight(
        server, "world", -18000, options=preflight.settings({})
    )
    assert result["links"]["opaque_record_count"] == 1
    assert result["links"]["nonportal_binary_records"] == 1
    assert not result["can_stage_data"]
    (server / "mods/reviewed.jar").write_bytes(b"unreviewed version")
    with pytest.raises(ValueError, match="artifact"):
        preflight.preflight(server, "world", -18000)


def test_removed_receiver_does_not_hide_still_bound_porter(saved):
    server, world, _, _ = saved
    link_save(world)
    encoded(
        world / "data/TPDestinations.dat",
        {
            "data": Tag(
                10,
                {
                    "lastId": Tag(3, 8),
                    "destinations": compound_list(
                        [{"dim": Tag(3, 0), "id": Tag(3, 8)}]
                    ),
                },
            )
        },
    )
    result = links.inspect_links(
        server, "world", -18000, inventory(world, world_name="world")
    )
    assert any(
        row["kind"] == "rftools.unresolved-receiver-id" for row in result["examples"]
    )


def test_advanced_porter_slots_and_nested_item_containers_are_scanned(saved):
    server, world, _, _ = saved
    link_save(world)
    advanced = {
        "id": Tag(8, "rftools:advanced_charged_porter"),
        "tag": Tag(
            10, {"target0": Tag(3, 7), "target7": Tag(3, 8), "Energy": Tag(3, 7)}
        ),
    }
    encoded(world / "data/nested.nbt", {"nested": compound_list([advanced])})
    result = links.inspect_links(
        server, "world", -18000, inventory(world, world_name="world")
    )
    matches = [r for r in result["examples"] if r["file"] == "data/nested.nbt"]
    assert len(matches) == 1 and matches[0]["nbt_path"].endswith("/target0")


@pytest.mark.parametrize("registry_present", [True, False])
def test_native_receiver_block_drop_keeps_a_receiver_id_and_must_be_reported(
    saved, registry_present
):
    server, world, _, _ = saved
    link_save(world)
    if not registry_present:
        (world / "data/TPDestinations.dat").unlink()
    encoded(
        world / "playerdata/block-drop.dat",
        {
            "Inventory": compound_list(
                [
                    {
                        "id": Tag(8, "rftools:matter_receiver"),
                        "tag": Tag(
                            10,
                            {
                                "destinationId": Tag(3, 7),
                                "Energy": Tag(4, 500000),
                                "tpName": Tag(8, "keep name"),
                            },
                        ),
                    }
                ]
            )
        },
    )
    result = links.inspect_links(
        server, "world", -18000, inventory(world, world_name="world")
    )
    rows = [r for r in result["examples"] if r["file"] == "playerdata/block-drop.dat"]
    assert len(rows) == 1 and rows[0]["nbt_path"].endswith("/destinationId")
    assert rows[0]["kind"] == (
        "rftools.receiver-id" if registry_present else "rftools.unresolved-receiver-id"
    )


@pytest.mark.parametrize(
    "item,key,expected",
    [
        ("matter_receiver", "destinationId", 0),
        ("charged_porter", "target", 0),
        ("advanced_charged_porter", "target7", 0),
        ("matter_transmitter", "destId", 1),
    ],
)
def test_native_unbound_minus_one_is_not_confused_with_a_stale_dial(
    saved, item, key, expected
):
    server, world, _, _ = saved
    encoded(
        world / "data/sentinel.nbt",
        {"id": Tag(8, "rftools:" + item), "tag": Tag(10, {key: Tag(3, -1)})},
    )
    result = links.inspect_links(
        server, "world", -18000, inventory(world, world_name="world")
    )
    assert result["finding_count"] == expected


def test_preflight_detects_concurrent_world_change(saved, monkeypatch):
    server, world, _, _ = saved
    original = preflight.inspect_links

    def changed(*args, **kwargs):
        result = original(*args, **kwargs)
        (world / "data/concurrent.dat").write_bytes(b"changed")
        return result

    monkeypatch.setattr(preflight, "inspect_links", changed)
    with pytest.raises(ValueError, match="changed"):
        preflight.preflight(server, "world", -18000)


@pytest.mark.parametrize("raw", ["-1", "33", "1.5", "true", " 4", "四", ""])
def test_invalid_search_environment_is_rejected(raw):
    with pytest.raises(ValueError):
        preflight.settings({"OMK_RESET_LANDING_RADIUS": raw})


def test_invalid_names_and_scan_budgets_are_rejected(saved):
    server, world, _, _ = saved
    for name in ("../world", "/world", "", "a/b", "a\\b"):
        with pytest.raises(ValueError):
            landing.select_landing(server, name)
    with pytest.raises(ValueError):
        links.inspect_links(server, "world", -18000, ["world/../outside.dat"])
    for options in ({}, {**preflight.settings({}), "landing_chunks": True}):
        with pytest.raises(ValueError):
            preflight.preflight(server, "world", -18000, options=options)
    assert world.exists()
