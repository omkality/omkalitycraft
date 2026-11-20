"""Test dependencies for quest locale."""

import hashlib
import json

import pytest


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
