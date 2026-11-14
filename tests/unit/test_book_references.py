import copy
import hashlib
import json
import re

import pytest

from omk.book_layout import repair_patchouli_references


def sample():
    return {
        "name": "Book",
        "advancement": "pack:gate",
        "pages": [
            {
                "type": "text",
                "text": "A $(l:old/path)label$() and $(cat:old)category$().",
            },
            {
                "type": "text",
                "title": "Renewability",
                "text": "Keep all of this.",
                "flag": "enabled",
            },
            {"type": "relations", "entries": ["old/path"]},
            {"type": "crafting", "recipe": "mod:unchanged"},
        ],
    }


def render(value, edits=(), anchors=None, **kwargs):
    source = (json.dumps(value, ensure_ascii=False) + "\n").encode()
    return repair_patchouli_references(
        source,
        expected_source_sha256=hashlib.sha256(source).hexdigest(),
        edits=edits,
        anchors={} if anchors is None else anchors,
        **kwargs,
    )


def inline(**updates):
    return {
        "kind": "inline",
        "pointer": "/pages/0/text",
        "macro": "l",
        "old": "old/path",
        "new": "new/path",
        **updates,
    }


def test_allowlisted_links_relations_and_anchor_preserve_other_book_data():
    value = sample()
    before = copy.deepcopy(value)
    edits = [
        inline(),
        inline(macro="cat", old="old", new="new_category"),
        {
            "kind": "relation",
            "pointer": "/pages/2/entries/0",
            "old": "old/path",
            "new": "new/path",
        },
    ]
    raw = render(value, edits, {1: "renew"})
    assert raw == render(value, edits, {1: "renew"})
    out = json.loads(raw)
    assert re.sub(r"\$\([^)]*\)", "", out["pages"][0]["text"]) == re.sub(
        r"\$\([^)]*\)", "", before["pages"][0]["text"]
    )
    assert out["pages"][1]["anchor"] == "renew"
    assert out["pages"][1]["flag"] == "enabled"
    assert out["pages"][2]["entries"] == ["new/path"]
    assert out["pages"][3] == before["pages"][3]
    assert out["advancement"] == before["advancement"]
    assert value == before


def test_nonexistent_article_can_be_unlinked_without_losing_label_or_other_link():
    out = json.loads(render(sample(), [inline(kind="unlink", new=None)]))
    assert out["pages"][0]["text"] == "A label$() and $(cat:old)category$()."


@pytest.mark.parametrize(
    "change",
    [
        {"old": "missing"},
        {"old": "old/path)label$()"},
        {"count": 2},
        {"count": True},
        {"macro": "cmd"},
        {"new": "https://example.com"},
        {"new": "../target"},
        {"new": "Upper Case"},
        {"pointer": "/advancement"},
        {"pointer": "/pages/3/recipe"},
        {"pointer": "/pages/99/text"},
    ],
)
def test_unreviewed_replacements_are_rejected(change):
    with pytest.raises(ValueError):
        render(sample(), [inline(**change)])


def test_relation_requires_the_actual_relations_page_and_exact_old_value():
    with pytest.raises(ValueError):
        render(
            sample(),
            [
                {
                    "kind": "relation",
                    "pointer": "/pages/2/entries/0",
                    "old": "wrong",
                    "new": "new/path",
                }
            ],
        )
    value = sample()
    value["pages"][2]["type"] = "recipe_template"
    with pytest.raises(ValueError):
        render(
            value,
            [
                {
                    "kind": "relation",
                    "pointer": "/pages/2/entries/0",
                    "old": "old/path",
                    "new": "new/path",
                }
            ],
        )


@pytest.mark.parametrize("anchors", [{3: "renew"}, {True: "renew"}, {1: "Bad anchor"}])
def test_anchor_cannot_touch_recipe_page_or_use_unreviewed_identity(anchors):
    with pytest.raises(ValueError):
        render(sample(), anchors=anchors)


def test_existing_or_duplicate_anchor_cannot_be_replaced():
    value = sample()
    value["pages"][0]["anchor"] = "renew"
    with pytest.raises(ValueError):
        render(value, anchors={1: "renew"})
    with pytest.raises(ValueError):
        render(value, anchors={0: "other"})


def test_stale_resource_and_duplicate_keys_fail_before_an_edit():
    source = b'{"pages":[],"pages":[]}'
    for digest in ["0" * 64, hashlib.sha256(source).hexdigest()]:
        with pytest.raises(ValueError):
            repair_patchouli_references(
                source, expected_source_sha256=digest, edits=[], anchors={}
            )
