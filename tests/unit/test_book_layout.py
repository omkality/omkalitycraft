import copy
import hashlib
import json

import pytest

from omk.book_layout import paginate_patchouli_entry


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()


def sample():
    return {
        "name": "Книга",
        "category": "concepts",
        "pages": [
            {
                "type": "text",
                "title": "Длинный заголовок",
                "text": "Первый $(l:herbs/wildroot)корень$().$(br2)Второй абзац.",
                "anchor": "start",
                "advancement": "roots:begin",
                "flag": "enabled",
            },
            {"type": "crafting", "recipe": "roots:knife", "anchor": "recipe"},
        ],
    }


def render(value, **kwargs):
    source = encoded(value)
    return paginate_patchouli_entry(
        source, expected_source_sha256=hashlib.sha256(source).hexdigest(), **kwargs
    )


def test_split_preserves_body_order_recipes_gates_and_unique_anchors():
    value = sample()
    unchanged = copy.deepcopy(value)
    cut = value["pages"][0]["text"].index("$(br2)")
    first = render(value, splits={0: (cut,)}, titles={0: "Кратко"})
    assert first == render(value, splits={0: (cut,)}, titles={0: "Кратко"})
    out = json.loads(first)
    assert value == unchanged
    assert len(out["pages"]) == 3
    assert "".join(p["text"] for p in out["pages"][:2]) == value["pages"][0]["text"]
    assert out["pages"][2] == value["pages"][1]
    assert out["pages"][0]["anchor"] == "start"
    assert "anchor" not in out["pages"][1]
    for page in out["pages"][:2]:
        assert page["title"] == "Кратко"
        assert page["advancement"] == "roots:begin"
        assert page["flag"] == "enabled"
    assert {k: v for k, v in out.items() if k != "pages"} == {
        k: v for k, v in value.items() if k != "pages"
    }


def test_stale_resource_is_rejected_before_processing():
    with pytest.raises(ValueError, match="source"):
        paginate_patchouli_entry(
            encoded(sample()), expected_source_sha256="0" * 64, splits={}
        )


@pytest.mark.parametrize("cuts", [(0,), (-1,), (999,), (True,), (3, 2), (2, 2), (3,)])
def test_invalid_or_unreviewed_split_boundary_is_rejected(cuts):
    with pytest.raises(ValueError):
        render(sample(), splits={0: cuts})


@pytest.mark.parametrize(
    "text", ["$(l:herbs/root)текст$(br2)ссылка$()", "$(bold)жирный$(li)текст$()"]
)
def test_style_or_link_cannot_span_two_pages(text):
    value = sample()
    value["pages"][0]["text"] = text
    cut = text.index("$(br2)") if "$(br2)" in text else text.index("$(li)")
    with pytest.raises(ValueError, match="format"):
        render(value, splits={0: (cut,)})


def test_non_text_or_unknown_template_payload_cannot_be_split():
    value = sample()
    value["pages"][0]["type"] = "spell_template"
    with pytest.raises(ValueError, match="text"):
        render(value, splits={0: (value["pages"][0]["text"].index("$(br2)"),)})
    value = sample()
    value["pages"][0]["custom_layout"] = {"height": 30}
    with pytest.raises(ValueError, match="field"):
        render(value, splits={0: (value["pages"][0]["text"].index("$(br2)"),)})


def test_title_change_cannot_touch_unplanned_or_untitled_page():
    value = sample()
    cut = value["pages"][0]["text"].index("$(br2)")
    with pytest.raises(ValueError, match="title"):
        render(value, splits={0: (cut,)}, titles={1: "Рецепт"})
    del value["pages"][0]["title"]
    with pytest.raises(ValueError, match="title"):
        render(value, splits={0: (cut,)}, titles={0: "Заголовок"})


def test_duplicate_json_keys_are_not_silently_discarded():
    source = b'{"pages":[],"pages":[]}'
    with pytest.raises(ValueError, match="Duplicate"):
        paginate_patchouli_entry(
            source, expected_source_sha256=hashlib.sha256(source).hexdigest(), splits={}
        )


@pytest.mark.parametrize("prefix", ["\u00a7lЖирный", "$(l:незакрытая"])
def test_legacy_or_malformed_formatting_is_not_split(prefix):
    value = sample()
    value["pages"][0]["text"] = prefix + "$(br2)Далее"
    with pytest.raises(ValueError, match="format"):
        render(value, splits={0: (len(prefix),)})


def test_roots_category_link_must_close_before_split():
    value = sample()
    text = "$(cat:herbs)Herbs$(/cat).$(br2)Next page."
    value["pages"][0]["text"] = text
    out = json.loads(render(value, splits={0: (text.index("$(br2)"),)}))
    assert "".join(p["text"] for p in out["pages"][:2]) == text
    value["pages"][0]["text"] = text.replace("$(/cat)", "")
    with pytest.raises(ValueError, match="format"):
        render(value, splits={0: (value["pages"][0]["text"].index("$(br2)"),)})


def test_plain_word_boundaries_require_explicit_review_and_preserve_text():
    value = sample()
    text = "First sentence. Second sentence."
    value["pages"][0]["text"] = text
    cut = text.index(" Second")
    with pytest.raises(ValueError):
        render(value, splits={0: (cut,)})
    out = json.loads(render(value, splits={0: (cut,)}, allow_word_boundaries=True))
    assert "".join(p["text"] for p in out["pages"][:2]) == text
    with pytest.raises(ValueError):
        render(value, splits={0: (3,)}, allow_word_boundaries=True)


def test_full_native_reset_ends_previous_formatting_before_a_word_cut():
    value = sample()
    text = "$(italic)First$() sentence. Second sentence."
    value["pages"][0]["text"] = text
    out = json.loads(
        render(value, splits={0: (text.index(" Second"),)}, allow_word_boundaries=True)
    )
    assert "".join(p["text"] for p in out["pages"][:2]) == text
