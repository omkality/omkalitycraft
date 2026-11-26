"""Test dependencies for resource reset preflight."""

import gzip
import hashlib
import json
import struct
import zlib

import pytest

from launcher.nbt import Tag, write_nbt
from omk.worlds.reset import resource_reset_preflight as preflight


def compound_list(rows):
    return Tag(9, (10, [Tag(10, row) for row in rows]))


def encoded(path, root):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(gzip.compress(write_nbt("", root), mtime=0))


def region_write(world, chunk, *, codec=2, coordinates=(0, 0), data_version=None):
    cx, cz = coordinates
    path = world / "region" / f"r.{cx // 32}.{cz // 32}.mca"
    path.parent.mkdir(exist_ok=True)
    root = {"Level": Tag(10, chunk)}
    if data_version is not None:
        root["DataVersion"] = Tag(3, data_version)
    packed = zlib.compress(write_nbt("", root))
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
