import hashlib
import json

import pytest

from omk.book_layout import relocate_patchouli_text


def source():
    return {
        "name": "Device",
        "category": "crafting",
        "pages": [
            {
                "type": "crafting",
                "recipe": "pack:device",
                "recipe2": "pack:other",
                "text": "First.$(br2)Second.",
                "anchor": "device",
                "advancement": "pack:gate",
                "flag": "enabled",
            },
            {"type": "relations", "entries": ["crafting/other"]},
        ],
    }


def render(value, moves, **kwargs):
    raw = json.dumps(value).encode()
    return relocate_patchouli_text(
        raw,
        expected_source_sha256=hashlib.sha256(raw).hexdigest(),
        moves=moves,
        **kwargs,
    )


def test_recipe_payload_anchor_and_gates_survive_prose_relocation():
    value = source()
    move = {"page": 0, "expected_type": "crafting", "offsets": [6]}
    out = json.loads(render(value, [move]))
    assert len(out["pages"]) == 4
    recipe = out["pages"][0]
    assert recipe == {**value["pages"][0], "text": ""}
    assert out["pages"][3] == value["pages"][1]
    assert "".join(p["text"] for p in out["pages"][1:3]) == value["pages"][0]["text"]
    for page in out["pages"][1:3]:
        assert page == {
            "type": "text",
            "text": page["text"],
            "advancement": "pack:gate",
            "flag": "enabled",
        }


def test_template_prose_requires_an_exact_consumer_type_and_literal_text():
    value = source()
    value["pages"][0]["type"] = "spell_modifier_template"
    assert (
        json.loads(
            render(
                value,
                [
                    {
                        "page": 0,
                        "expected_type": "spell_modifier_template",
                        "offsets": [],
                    }
                ],
            )
        )["pages"][0]["text"]
        == ""
    )
    with pytest.raises(ValueError):
        render(value, [{"page": 0, "expected_type": "crafting", "offsets": []}])
    value["pages"][0]["text"] = "#template_variable"
    with pytest.raises(ValueError):
        render(
            value,
            [{"page": 0, "expected_type": "spell_modifier_template", "offsets": []}],
        )


@pytest.mark.parametrize("page", [True, -1, 99])
def test_invalid_source_page_is_rejected(page):
    with pytest.raises(ValueError):
        render(source(), [{"page": page, "expected_type": "crafting", "offsets": []}])


def test_no_implicit_text_page_relocation_or_duplicate_moves():
    value = source()
    move = {"page": 0, "expected_type": "crafting", "offsets": []}
    with pytest.raises(ValueError):
        render(value, [move, move])
    value["pages"][0]["type"] = "text"
    with pytest.raises(ValueError):
        render(value, [{**move, "expected_type": "text"}])


def test_stale_source_is_rejected():
    with pytest.raises(ValueError):
        relocate_patchouli_text(
            b'{"pages":[]}', expected_source_sha256="0" * 64, moves=[]
        )
