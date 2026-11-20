import copy
import json
from pathlib import Path

import pytest

from omk.localization.dj2_resource_models import compose_resource_models
from tests.fixtures.unit.localization.dj2_resource_models import inputs, pin

__all__ = ["inputs", "pin"]


def test_only_reviewed_paths_change_and_inputs_remain_unchanged(inputs):
    before = copy.deepcopy(inputs)
    result = compose_resource_models(**inputs)
    source = inputs["review"]["models"][0]["source"]["path"]
    target = inputs["review"]["models"][0]["target"]
    assert result.files == {target: inputs["resources"][source]}
    assert result.removed == (source,)
    assert result.items == ("contenttweaker:puzzle_tile_gbbgr",)
    assert inputs == before


@pytest.mark.parametrize("which", ["model", "texture", "script", "bag", "orphan"])
def test_changed_reviewed_payload_is_rejected(inputs, which):
    row = inputs["review"]
    path = {
        "model": row["models"][0]["source"]["path"],
        "texture": row["models"][0]["texture"]["path"],
        "script": row["scripts"][0]["path"],
        "bag": row["scripts"][1]["path"],
        "orphan": row["preserved_models"][0]["path"],
    }[which]
    inputs["resources"][path] += b"changed"
    with pytest.raises(ValueError):
        compose_resource_models(**inputs)


@pytest.mark.parametrize(
    "target",
    [
        "mods/new.jar",
        "../model.json",
        "resources/contenttweaker/models/item/puzzle_tile_grgrg.json",
        "resources/contenttweaker/models/item/puzzle_tile_Gbbgr.json",
    ],
)
def test_no_arbitrary_retarget_or_unchanged_case(inputs, target):
    inputs["review"]["models"][0]["target"] = target
    with pytest.raises(ValueError):
        compose_resource_models(**inputs)


@pytest.mark.parametrize(
    "extra",
    [
        "target",
        "other_source_case",
        "missing_source",
        "missing_texture",
        "missing_orphan",
        "unreviewed_resource",
        "duplicate_model",
        "orphan_registered",
    ],
)
def test_inventory_or_registration_disagreement_rejects_plan(inputs, extra):
    row = inputs["review"]["models"][0]
    if extra == "target":
        inputs["inventory"].append(row["target"])
    elif extra == "other_source_case":
        inputs["inventory"].append(row["source"]["path"].upper())
    elif extra.startswith("missing_"):
        path = {
            "missing_source": row["source"]["path"],
            "missing_texture": row["texture"]["path"],
            "missing_orphan": inputs["review"]["preserved_models"][0]["path"],
        }[extra]
        inputs["inventory"].remove(path)
    elif extra == "unreviewed_resource":
        inputs["resources"]["resources/other.json"] = b"other"
    elif extra == "duplicate_model":
        inputs["review"]["models"].append(copy.deepcopy(row))
    else:
        path = inputs["review"]["scripts"][0]["path"]
        inputs["resources"][path] += b'VanillaFactory.createItem("puzzle_tile_grgrg");'
        inputs["review"]["scripts"][0] = pin(path, inputs["resources"][path])
    with pytest.raises(ValueError):
        compose_resource_models(**inputs)


@pytest.mark.parametrize(
    "change", ["parent", "texture_reference", "extra_texture", "extra_field"]
)
def test_even_re_pinned_model_must_keep_exact_reviewed_shape(inputs, change):
    row = inputs["review"]["models"][0]
    source = row["source"]["path"]
    model = json.loads(inputs["resources"][source])
    if change == "parent":
        model["parent"] = "other/parent"
    elif change == "texture_reference":
        model["textures"]["layer0"] = "other:items/puzzle_tile_Gbbgr"
    elif change == "extra_texture":
        model["textures"]["layer1"] = model["textures"]["layer0"]
    else:
        model["overrides"] = []
    inputs["resources"][source] = json.dumps(model).encode()
    row["source"] = pin(source, inputs["resources"][source])
    with pytest.raises(ValueError):
        compose_resource_models(**inputs)


def test_profile_has_59_registered_models_and_keeps_one_orphan():
    review = json.loads(
        Path("profiles/pack-overlays/dj2-2.23.4/resource-models.json").read_bytes()
    )
    assert len(review["models"]) == 59
    assert len(review["preserved_models"]) == 1
    assert review["preserved_models"][0]["path"].endswith("puzzle_tile_Grgrg.json")
    assert len({r["target"].casefold() for r in review["models"]}) == 59
