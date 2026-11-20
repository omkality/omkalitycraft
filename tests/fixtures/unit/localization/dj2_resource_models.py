"""Test dependencies for dj2 resource models."""

import hashlib

import pytest


def pin(path, raw):
    return {"path": path, "size": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


@pytest.fixture
def inputs():
    script = b'var p = VanillaFactory.createItem("puzzle_tile_gbbgr");\np.register();\n'
    bag = b'keep("contenttweaker:puzzle_tile_gbbgr");\n'
    model = b'{"parent":"item/generated","textures":{"layer0":"contenttweaker:items/puzzle_tile_Gbbgr"}}\n'
    orphan = b'{"parent":"item/generated","textures":{"layer0":"contenttweaker:items/puzzle_tile_Grgrg"}}\n'
    texture = b"reviewed texture fixture"
    rows = [
        pin("scripts/ContentTweaker/ContentTweakerItems.zs", script),
        pin("scripts/Unique/ContentTweakerBag.zs", bag),
    ]
    source = "resources/contenttweaker/models/item/puzzle_tile_Gbbgr.json"
    target = source.lower()
    texture_path = "resources/contenttweaker/textures/items/puzzle_tile_gbbgr.png"
    unused = pin("resources/contenttweaker/models/item/puzzle_tile_Grgrg.json", orphan)
    resources = {
        rows[0]["path"]: script,
        rows[1]["path"]: bag,
        source: model,
        texture_path: texture,
        unused["path"]: orphan,
    }
    review = {
        "schema": 1,
        "pack": "dj2",
        "version": "2.23.4",
        "upstream_commit": "2" * 40,
        "scripts": rows,
        "models": [
            {
                "item": "contenttweaker:puzzle_tile_gbbgr",
                "source": pin(source, model),
                "target": target,
                "texture": pin(texture_path, texture),
            }
        ],
        "preserved_models": [unused],
    }
    return {
        "resources": resources,
        "inventory": [*resources, "mods/untouched.jar"],
        "review": review,
    }
