import copy
import hashlib
import json

import pytest

from omk.locale_overlay import parse_lang
from omk.quest_locale import (
    audit_quest_references,
    render_initial_key_defaults,
    render_quest_locale,
)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


@pytest.fixture
def inputs():
    def props(prefix):
        return {
            "properties:10": {
                "betterquesting:10": {
                    "name:8": prefix + ".title",
                    "desc:8": prefix + ".desc",
                }
            }
        }

    quest = props("dj2.quest.db.1")
    quest.update(
        {
            "questID:3": 1,
            "preRequisites:11": [0],
            "tasks:9": {
                "0:10": {
                    "taskID:8": "bq_standard:location",
                    "name:8": "Enter the Nether",
                    "dimension:3": -1,
                    "range:3": -1,
                },
                "1:10": {
                    "taskID:8": "bq_standard:retrieval",
                    "requiredItems:9": {
                        "0:10": {
                            "id:8": "minecraft:chest",
                            "tag:10": {
                                "display:10": {"Name:8": "Original puzzle item"}
                            },
                        }
                    },
                },
            },
        }
    )
    chapter = props("dj2.quest.ql.0")
    chapter["lineID:3"] = 0
    data = {
        "format:8": "2.0.0",
        "questDatabase:9": {"0:10": quest},
        "questLines:9": {"0:10": chapter},
    }
    database = json.dumps(data).encode()
    en = b"dj2.quest.db.1.title=Hello\ndj2.quest.db.1.desc=Puzzle\ndj2.quest.ql.0.title=Chapter\ndj2.quest.ql.0.desc=\n"
    ru = (
        "# retained\ndj2.quest.db.1.title=Привет\ndj2.quest.db.1.desc=Puzzle\n"
        "dj2.quest.ql.0.title=Глава\ndj2.quest.ql.0.desc=\nother.key=Не менять\n"
    ).encode()
    profile = {
        "schema": 1,
        "pack": "DJ2 2.23.4",
        "source_database_sha256": sha(database),
        "source_english_sha256": sha(en),
        "previous_russian_sha256": sha(ru),
        "quests": 1,
        "chapters": 1,
        "updates": [
            {
                "key": "dj2.quest.db.1.desc",
                "english_sha256": sha(b"Puzzle"),
                "previous_sha256": sha(b"Puzzle"),
                "ru": "Загадка",
            }
        ],
        "literal_task_labels": [
            {
                "quest": 1,
                "task": "0:10",
                "source_sha256": sha(b"Enter the Nether"),
                "ru": "Войдите в Нижний мир",
            }
        ],
    }
    return database, en, ru, profile


def test_translates_prose_and_literal_key_without_rewriting_quest_data(inputs):
    database, en, _ru, _profile = inputs
    before = copy.deepcopy(inputs)
    result = render_quest_locale(*inputs)
    parsed = parse_lang(result)
    assert parsed["dj2.quest.db.1.desc"] == "Загадка"
    assert parsed["Enter the Nether"] == "Войдите в Нижний мир"
    assert parsed["other.key"] == "Не менять"
    assert result.startswith(b"# retained\n")
    assert inputs == before
    assert render_quest_locale(*inputs) == result
    assert audit_quest_references(database, en, result) == {
        "quests": 1,
        "chapters": 1,
        "references": 4,
        "empty_source_values": 1,
        "database_sha256": sha(database),
    }


@pytest.mark.parametrize("index", [0, 1, 2])
def test_refuses_changed_whole_source_before_rendering(inputs, index):
    changed = list(inputs)
    changed[index] += b" "
    with pytest.raises(ValueError, match="source changed"):
        render_quest_locale(*changed)


@pytest.mark.parametrize("field", ["english_sha256", "previous_sha256"])
def test_refuses_changed_value_pin(inputs, field):
    inputs[3]["updates"][0][field] = "0" * 64
    with pytest.raises(ValueError, match="puzzle contract"):
        render_quest_locale(*inputs)


@pytest.mark.parametrize("value", ["Bad\nnew.key=evil", "Bad\rtext", "Bad\0text", "%s"])
def test_refuses_line_injection_or_added_format_argument(inputs, value):
    inputs[3]["updates"][0]["ru"] = value
    with pytest.raises(ValueError):
        render_quest_locale(*inputs)


@pytest.mark.parametrize("kind", ["runes", "hint"])
def test_cannot_erase_story_cipher_or_change_hidden_hint(inputs, kind):
    database, en, ru, profile = inputs
    source = "Puzzle ᚢᛤ" if kind == "runes" else "Puzzle §4U§rp"
    en = en.replace(b"=Puzzle\n", b"=" + source.encode() + b"\n")
    profile["source_english_sha256"] = sha(en)
    profile["updates"][0]["english_sha256"] = sha(source.encode())
    with pytest.raises(ValueError, match="puzzle contract"):
        render_quest_locale(database, en, ru, profile)
    profile["updates"][0]["ru"] = "Загадка " + ("ᚢᛤ" if kind == "runes" else "§4U§rp")
    assert parse_lang(render_quest_locale(database, en, ru, profile))[
        "dj2.quest.db.1.desc"
    ].startswith("Загадка")


@pytest.mark.parametrize("group", ["updates", "literal_task_labels"])
def test_refuses_repeated_review_records(inputs, group):
    inputs[3][group].append(copy.deepcopy(inputs[3][group][0]))
    with pytest.raises(ValueError):
        render_quest_locale(*inputs)


def test_cannot_use_task_label_rule_to_change_item_nbt(inputs):
    inputs[3]["literal_task_labels"][0]["task"] = "1:10"
    with pytest.raises(ValueError):
        render_quest_locale(*inputs)


def test_checks_location_type_even_after_source_is_explicitly_repinned(inputs):
    database, en, ru, profile = inputs
    data = json.loads(database)
    data["questDatabase:9"]["0:10"]["tasks:9"]["0:10"][
        "taskID:8"
    ] = "bq_standard:retrieval"
    database = json.dumps(data).encode()
    profile["source_database_sha256"] = sha(database)
    with pytest.raises(ValueError, match="literal task label"):
        render_quest_locale(database, en, ru, profile)


@pytest.mark.parametrize(
    "change", ["missing", "empty", "literal_reference", "duplicate_id"]
)
def test_catalog_checks_actual_records_instead_of_only_key_counts(inputs, change):
    database, en, ru, _profile = inputs
    data = json.loads(database)
    if change == "missing":
        ru = ru.replace(b"dj2.quest.db.1.desc=Puzzle\n", b"")
    elif change == "empty":
        ru = ru.replace(b"dj2.quest.db.1.desc=Puzzle\n", b"dj2.quest.db.1.desc=\n")
    elif change == "literal_reference":
        data["questDatabase:9"]["0:10"]["properties:10"]["betterquesting:10"][
            "name:8"
        ] = "Hello"
    else:
        data["questDatabase:9"]["1:10"] = copy.deepcopy(data["questDatabase:9"]["0:10"])
    with pytest.raises(ValueError):
        audit_quest_references(json.dumps(data).encode(), en, ru)


def test_refuses_duplicate_json_fields(inputs):
    database, en, ru, _profile = inputs
    database = database.replace(
        b'"format:8": "2.0.0"', b'"format:8":"2.0.0","format:8":"2.0.0"'
    )
    with pytest.raises(ValueError, match="Duplicate"):
        audit_quest_references(database, en, ru)


def test_boolean_is_not_a_profile_schema(inputs):
    inputs[3]["schema"] = True
    with pytest.raises(ValueError, match="Unknown quest review"):
        render_quest_locale(*inputs)


def test_initial_alias_only_appends_to_pinned_defaultoptions_template():
    raw = b"key_quests:37:NONE\r\nkey_Toggle Sensor Goggles Mode:0:NONE\r\n"
    addition = "key_Переключить режим Очков с сенсорами:0:NONE"
    review = {
        "source_sha256": sha(raw),
        "result_sha256": sha(raw + addition.encode() + b"\n"),
        "required_lines": [
            "key_quests:37:NONE",
            "key_Toggle Sensor Goggles Mode:0:NONE",
        ],
        "addition": addition,
    }
    result = render_initial_key_defaults(raw, review)
    assert result.startswith(raw)
    assert result[len(raw) :].decode() == review["addition"] + "\n"
    with pytest.raises(ValueError, match="source changed"):
        render_initial_key_defaults(raw + b"key_personal:4:NONE\n", review)
    review["result_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="result changed"):
        render_initial_key_defaults(raw, review)


@pytest.mark.parametrize(
    "addition",
    ["key_bad:37:NONE", "key_bad:0:NONE\nkey_quests:0:NONE", "key_quests:0:NONE"],
)
def test_initial_alias_cannot_replace_other_bindings_or_inject_lines(addition):
    raw = b"key_quests:37:NONE\n"
    review = {
        "source_sha256": sha(raw),
        "required_lines": ["key_quests:37:NONE"],
        "addition": addition,
    }
    with pytest.raises(ValueError):
        render_initial_key_defaults(raw, review)
