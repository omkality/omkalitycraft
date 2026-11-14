import hashlib
import json

import pytest

from omk.book_layout import expand_patchouli_template_pages


def fixture():
    value = {
        "name": "Магия",
        "advancement": "roots:progress/one",
        "pages": [
            {"type": "text", "text": "Введение"},
            {
                "type": "spell_modifier_template",
                "spell": "roots:example",
                "modifier": "roots:secondary",
                "anchor": "modifier",
                "flag": "roots:enabled",
                "advancement": "roots:progress/two",
                "processor_input": {"amount": 2},
            },
            {"type": "crafting", "recipe": "roots:example"},
        ],
    }
    source = (json.dumps(value, ensure_ascii=False) + "\n").encode()
    return source, hashlib.sha256(source).hexdigest(), value


def apply(source, sha, **overrides):
    options = {
        "expected_source_sha256": sha,
        "pages": [1],
        "expected_type": "spell_modifier_template",
        "guards": ["omk_layout_stats", "omk_layout_details"],
        **overrides,
    }
    return expand_patchouli_template_pages(source, **options)


def test_template_expansion_preserves_live_variables_gates_and_recipes():
    source, sha, value = fixture()
    result = json.loads(apply(source, sha))
    first, second = result["pages"][1:3]
    assert first == {
        **value["pages"][1],
        "omk_layout_stats": "true",
        "omk_layout_details": "false",
    }
    assert second == {
        k: v
        for k, v in {
            **value["pages"][1],
            "omk_layout_stats": "false",
            "omk_layout_details": "true",
        }.items()
        if k != "anchor"
    }
    assert result["pages"][0] == value["pages"][0]
    assert result["pages"][-1] == value["pages"][-1]
    assert result["advancement"] == value["advancement"]
    assert hashlib.sha256(source).hexdigest() == sha
    assert apply(source, sha) == apply(source, sha)


@pytest.mark.parametrize(
    "overrides",
    [
        {"expected_source_sha256": "0" * 64},
        {"pages": [0]},
        {"pages": [1, 1]},
        {"pages": [True]},
        {"pages": [3]},
        {"expected_type": "other_template"},
        {"guards": ["flag", "advancement"]},
        {"guards": ["omk_layout_same", "omk_layout_same"]},
        {"guards": ["omk_layout_../outside", "omk_layout_details"]},
        {"guards": ["omk_layout_one"]},
    ],
)
def test_unreviewed_template_expansion_is_rejected(overrides):
    source, sha, _ = fixture()
    with pytest.raises(ValueError):
        apply(source, sha, **overrides)


def test_builtin_recipe_cannot_be_disguised_as_custom_template():
    source, sha, _ = fixture()
    with pytest.raises(ValueError):
        apply(source, sha, pages=[2], expected_type="crafting")


def test_duplicate_json_fields_are_rejected_before_expansion():
    source = b'{"pages":[],"pages":[]}'
    with pytest.raises(ValueError, match="Duplicate"):
        apply(source, hashlib.sha256(source).hexdigest())


def test_existing_processor_variable_cannot_be_overwritten():
    _, _, value = fixture()
    value["pages"][1]["omk_layout_stats"] = "original processor input"
    source = json.dumps(value).encode()
    with pytest.raises(ValueError, match="already exists"):
        apply(source, hashlib.sha256(source).hexdigest())
