"""Binary-save fault controls; these tests do not claim a native game boot."""

import hashlib
import json
import shutil
import zlib

import pytest

from launcher.nbt import Tag
from omk.backups.stopped_world_backup import inventory
from omk.worlds import forge112_regions as anvil
from omk.worlds.reset import (
    dimension_reset,
    resource_reset_inventory as audit,
    resource_reset_landing as landing,
    resource_reset_links as links,
    resource_reset_preflight as preflight,
    rftools_reset as rftools,
)
from tests.fixtures.unit.worlds.resource_reset_inventory import (
    rftools_destinations,
    rftools_registry,
)
from tests.fixtures.unit.worlds.resource_reset_preflight import (
    compound_list,
    encoded,
    region_write,
    saved,
)

__all__ = ["compound_list", "encoded", "region_write", "rftools_registry", "saved"]


@pytest.mark.parametrize(
    ("linked", "expected_pending"),
    [
        (None, []),
        ("porter", ["rftools.receiver-id"]),
        ("favorite", ["dimension-tag"]),
        ("other-receiver", ["dimension-tag"]),
    ],
)
def test_generated_rftools_spawn_receiver_only_is_reviewed(
    rftools_registry, linked, expected_pending
):
    server, _, save = rftools_registry
    world = server / "world"
    registry = save([(6200, "Лаборатория"), (6201, "Другая")])
    destinations = world / audit.RFTOOLS_DESTINATIONS
    receivers = [(7, 6200, "Лаборатория", 7), (8, 6201, "Другая", 7)]
    if linked == "other-receiver":
        receivers.append((9, 6200, "Лаборатория", 24))
    rftools_destinations(destinations, *receivers)
    files = [registry, destinations]
    player = world / "playerdata/fixture.dat"
    if linked == "porter":
        encoded(
            player,
            {
                "Inventory": compound_list(
                    [
                        {
                            "id": Tag(8, "rftools:charged_porter"),
                            "tag": Tag(10, {"target": Tag(3, 7)}),
                        }
                    ]
                )
            },
        )
        files.append(player)
    elif linked == "favorite":
        encoded(player, {"Favorites": compound_list([{"dim": Tag(3, 6200)}])})
        files.append(player)
    _label, _root, rows = audit._rftools_registry(server, "world")
    reset = dimension_reset.layout(
        6200, rftools_identity=audit.rftools_identity(rows[6200])
    )
    report = links.inspect_links(
        server,
        "world",
        6200,
        [p.relative_to(server).as_posix() for p in files],
        reset=reset,
    )
    assert report["handled_finding_count"] == 1
    assert report["unhandled_finding_count"] == len(expected_pending)
    assert [
        row["kind"] for row in report["examples"] if "staging_adapter" not in row
    ] == expected_pending


@pytest.mark.parametrize(
    "variant",
    [
        None,
        "dialer",
        "nested",
        "other_version",
        "transmitter",
        "wrong_block",
        "mixed_destination",
    ],
)
def test_rftools_preflight_reviews_player_targets_favorites_and_extra_receivers(
    saved, rftools_registry, monkeypatch, tmp_path, variant
):
    server, world, level, chunk = saved
    _, _, save = rftools_registry
    save([(6200, "Лаборатория"), (6201, "Соседний мир")])
    selected_region = world / "RFTOOLS6200/region"
    selected_region.mkdir(parents=True)
    (selected_region / "r.0.0.mca").write_bytes(b"omitted old terrain")
    destinations = world / audit.RFTOOLS_DESTINATIONS
    rftools_destinations(
        destinations,
        (7, 6200, "Лаборатория", 7),
        (8, 6201, "Соседний мир", 7),
        (9, 6200, "Площадка", 24),
    )
    player = world / "playerdata/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa.dat"
    encoded(
        player,
        {
            "Inventory": compound_list(
                [
                    {
                        "Slot": Tag(1, 0),
                        "Count": Tag(1, 1),
                        "Damage": Tag(2, 0),
                        "id": Tag(8, "rftools:advanced_charged_porter"),
                        "tag": Tag(
                            10,
                            {
                                "target": Tag(3, 9),
                                "target0": Tag(3, 9),
                                "target1": Tag(3, 8),
                                "tpTimer": Tag(3, 40),
                            },
                        ),
                    }
                ]
            ),
            "ForgeCaps": Tag(
                10,
                {
                    "rftools:properties": Tag(
                        10,
                        {
                            "destinations": compound_list(
                                [
                                    {
                                        "dim": Tag(3, dim),
                                        "x": Tag(3, 7),
                                        "y": Tag(3, 101),
                                        "z": Tag(3, -12),
                                    }
                                    for dim in (6200, 6201)
                                ]
                            )
                        },
                    )
                },
            ),
        },
    )
    _label, _root, rows = audit._rftools_registry(server, "world")
    reset = dimension_reset.layout(
        6200, rftools_identity=audit.rftools_identity(rows[6200])
    )
    if variant in {"transmitter", "wrong_block", "mixed_destination"}:
        registry = level["FML"].value["Registries"].value["minecraft:blocks"].value
        registry["ids"].value[1].append(
            Tag(10, {"K": Tag(8, "rftools:matter_transmitter"), "V": Tag(3, 44)})
        )
        encoded(world / "level.dat", level)
        section = anvil.sections(chunk)[4]
        blocks = bytearray(section["Blocks"].value)
        blocks[6 * 256 + 14 * 16 + 14] = 43 if variant == "wrong_block" else 44
        section["Blocks"] = Tag(7, bytes(blocks))
        chunk["TileEntities"] = compound_list(
            [
                {
                    "id": Tag(8, "rftools:matter_transmitter"),
                    "x": Tag(3, 14),
                    "y": Tag(3, 70),
                    "z": Tag(3, 14),
                    "destId": Tag(3, 9),
                    "tpPlayer": Tag(8, "SyntheticPlayer"),
                    "tpTimer": Tag(3, 32),
                    "Energy": Tag(4, 20000),
                    "private": Tag(1, 1),
                }
            ]
        )
        if variant == "mixed_destination":
            tile = chunk["TileEntities"].value[1][0].value
            tile.update(dim=Tag(3, 0), dest=Tag(11, [3, 70, 5]))
        region_file = region_write(world, chunk, data_version=anvil.DATA_VERSION)
    elif variant == "dialer":
        chunk["TileEntities"] = compound_list(
            [
                {
                    "id": Tag(8, "rftools:simple_dialer"),
                    "x": Tag(3, 14),
                    "y": Tag(3, 70),
                    "z": Tag(3, 14),
                    "receiver": Tag(3, 9),
                    "transDim": Tag(3, 6200),
                }
            ]
        )
        region_write(world, chunk)
    elif variant == "nested":
        encoded(
            world / "data/chest.nbt",
            {
                "Items": compound_list(
                    [
                        {
                            "id": Tag(8, "rftools:matter_receiver"),
                            "tag": Tag(10, {"destinationId": Tag(3, 9)}),
                        }
                    ]
                ),
            },
        )
    if variant != "other_version":
        monkeypatch.setattr(
            preflight, "artifacts", lambda *_: {rftools.ARTIFACT: rftools.SHA256}
        )
    before = inventory(world, world_name="world")
    edits = {}
    report = preflight.preflight(server, "world", 6200, reset=reset, region_edits=edits)
    assert report["can_stage_data"] is (variant in (None, "transmitter"))
    expected = {
        None: 0,
        "dialer": 2,
        "nested": 1,
        "other_version": 4,
        "transmitter": 0,
        "wrong_block": 1,
        "mixed_destination": 1,
    }
    assert report["links"]["unhandled_finding_count"] == expected[variant]
    assert report["links"]["handled_finding_count"] == (
        1 if variant == "other_version" else 5 + (variant == "transmitter")
    )
    if variant == "transmitter":
        edit = edits[region_file.relative_to(server).as_posix()]
        copy_path = tmp_path / region_file.name
        shutil.copyfile(region_file, copy_path)
        edit.apply(copy_path)
        updated = anvil.compounds(
            anvil.Region(copy_path, tmp_path).chunk(0), "TileEntities"
        )
        assert updated == [
            {
                key: Tag(3, 0) if key == "tpTimer" else tag
                for key, tag in anvil.compounds(chunk, "TileEntities")[0].items()
                if key not in {"destId", "tpPlayer"}
            }
        ]
    else:
        assert not edits
    assert inventory(world, world_name="world") == before


@pytest.mark.parametrize("selected_receiver", [True, False])
def test_rftools_dialer_drops_obsolete_links_in_saved_blocks(
    saved, rftools_registry, monkeypatch, tmp_path, selected_receiver
):
    server, world, level, chunk = saved
    _, _, save = rftools_registry
    save([(6200, "Лаборатория")])
    receivers = [(8, 0, "Основной", 7)]
    if selected_receiver:
        receivers.append((9, 6200, "Площадка", 24))
    rftools_destinations(world / audit.RFTOOLS_DESTINATIONS, *receivers)
    _label, _root, rows = audit._rftools_registry(server, "world")
    reset = dimension_reset.layout(
        6200, rftools_identity=audit.rftools_identity(rows[6200])
    )

    block = "rftools:simple_dialer"
    registry = level["FML"].value["Registries"].value["minecraft:blocks"].value
    registry["ids"].value[1].append(Tag(10, {"K": Tag(8, block), "V": Tag(3, 44)}))
    encoded(world / "level.dat", level)
    section = anvil.sections(chunk)[4]
    blocks = bytearray(section["Blocks"].value)
    tiles = []
    for x, source, receiver in (
        (12, 0, 9 if selected_receiver else 8),
        (13, 6200, 8),
        (14, 0, 8),
        (15, 0, None),  # An intentional redstone interrupter.
    ):
        blocks[6 * 256 + 14 * 16 + x] = 44
        tile = {
            "id": Tag(8, block),
            "x": Tag(3, x),
            "y": Tag(3, 70),
            "z": Tag(3, 14),
            "transX": Tag(3, 32),
            "transY": Tag(3, 71),
            "transZ": Tag(3, -2),
            "transDim": Tag(3, source),
            "once": Tag(1, 1),
            "owner": Tag(8, "SyntheticPlayer"),
        }
        if receiver is not None:
            tile["receiver"] = Tag(3, receiver)
        tiles.append(tile)
    section["Blocks"] = Tag(7, bytes(blocks))
    chunk["TileEntities"] = compound_list(tiles)
    region_file = region_write(world, chunk, data_version=anvil.DATA_VERSION)
    monkeypatch.setattr(
        preflight, "artifacts", lambda *_: {rftools.ARTIFACT: rftools.SHA256}
    )
    source_files = inventory(world, world_name="world")

    edits = {}
    report = preflight.preflight(server, "world", 6200, reset=reset, region_edits=edits)
    assert report["can_stage_data"]
    assert report["links"]["unhandled_finding_count"] == 0
    assert report["links"]["rftools_transport_references"] == (
        3 if selected_receiver else 1
    )
    copy_path = tmp_path / region_file.name
    shutil.copyfile(region_file, copy_path)
    edits[region_file.relative_to(server).as_posix()].apply(copy_path)
    updated = anvil.compounds(
        anvil.Region(copy_path, tmp_path).chunk(0), "TileEntities"
    )
    source_fields = {"transX", "transY", "transZ", "transDim"}
    assert updated == [
        {
            key: tag
            for key, tag in tiles[0].items()
            if not selected_receiver or key not in source_fields | {"receiver"}
        },
        {key: tag for key, tag in tiles[1].items() if key not in source_fields},
        *tiles[2:],
    ]
    assert inventory(world, world_name="world") == source_files


def test_rftools_dialer_updates_only_direct_player_items(saved, rftools_registry):
    server, world, _, _ = saved
    _, _, save = rftools_registry
    registry = save([(6200, "Лаборатория")])
    destinations = world / audit.RFTOOLS_DESTINATIONS
    rftools_destinations(destinations, (8, 0, "Основной", 7), (9, 6200, "Площадка", 24))
    source_fields = {
        "transX": Tag(3, 32),
        "transY": Tag(3, 71),
        "transZ": Tag(3, -2),
        "transDim": Tag(3, 0),
    }
    metadata = {"once": Tag(1, 1), "display": Tag(10, {"Name": Tag(8, "Свой")})}
    carried = {
        "Slot": Tag(1, 4),
        "Count": Tag(3, 2),
        "Damage": Tag(2, 0),
        "id": Tag(8, "rftools:simple_dialer"),
        "tag": Tag(10, {**metadata, **source_fields, "receiver": Tag(3, 9)}),
    }
    ender = {
        **carried,
        "Count": Tag(1, 1),
        "tag": Tag(
            10, {**source_fields, "transDim": Tag(3, 6200), "receiver": Tag(3, 8)}
        ),
    }
    container = {
        "Slot": Tag(1, 5),
        "Count": Tag(1, 1),
        "Damage": Tag(2, 0),
        "id": Tag(8, "minecraft:shulker_box"),
        "tag": Tag(
            10, {"BlockEntityTag": Tag(10, {"Items": compound_list([carried])})}
        ),
    }
    original = {
        "Inventory": compound_list([carried, container]),
        "EnderItems": compound_list([ender]),
    }
    player = world / "playerdata/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa.dat_old"
    encoded(player, original)
    _label, _root, rows = audit._rftools_registry(server, "world")
    reset = dimension_reset.layout(
        6200, rftools_identity=audit.rftools_identity(rows[6200])
    )
    report = links.inspect_links(
        server,
        "world",
        6200,
        [p.relative_to(server).as_posix() for p in (player, registry, destinations)],
        reset=reset,
        rftools_transport=True,
    )
    unresolved = [
        row["nbt_path"] for row in report["examples"] if "staging_adapter" not in row
    ]
    assert unresolved == ["/Inventory/1/tag/BlockEntityTag/Items/0/tag/receiver"]

    saved_player = audit.ftb.nbt(player.read_bytes())
    updated, _removed = rftools.unbind_player_targets(saved_player, 6200, {9})
    assert anvil.compounds(updated, "Inventory") == [
        {**carried, "tag": Tag(10, metadata)},
        container,
    ]
    assert anvil.compounds(updated, "EnderItems") == [
        {**ender, "tag": Tag(10, {"receiver": Tag(3, 8)})}
    ]


def test_region_edit_hashes_and_overwrites_two_allocations_without_touching_neighbors(
    tmp_path,
):
    sector = anvil.SECTOR
    file = tmp_path / "r.0.0.mca"
    before = b"".join(bytes([index]) * sector for index in range(7))
    file.write_bytes(before)
    edit = anvil.RegionEdit(((2 * sector, b"A" * sector), (5 * sector, b"B" * sector)))
    expected = before[: 2 * sector] + b"A" * sector + before[3 * sector : 5 * sector]
    expected += b"B" * sector + before[6 * sector :]
    assert edit.record(file, len(before)) == {
        "bytes": len(before),
        "sha256": hashlib.sha256(expected).hexdigest(),
    }
    assert file.read_bytes() == before
    edit.apply(file)
    assert file.read_bytes() == expected


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


@pytest.mark.parametrize("target", [None, -1])
def test_unbinding_a_porter_without_cancelling_its_timer_is_not_clean(saved, target):
    server, world, _, _ = saved
    fields = {"tpTimer": Tag(3, 0), "Energy": Tag(3, 12345)}
    if target is not None:
        fields["target"] = Tag(3, target)
    encoded(
        world / "data/inflight.nbt",
        {"id": Tag(8, "rftools:charged_porter"), "tag": Tag(10, fields)},
    )
    result = links.inspect_links(
        server, "world", -18000, inventory(world, world_name="world")
    )
    assert any(
        row["kind"] == "rftools.incomplete-porter-timer" for row in result["examples"]
    )


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
