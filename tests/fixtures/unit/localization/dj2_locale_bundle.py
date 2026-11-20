"""Test dependencies for dj2 locale bundle."""

import hashlib

import pytest


def sha(value):
    return hashlib.sha256(value).hexdigest()


@pytest.fixture
def inputs():
    note = (
        "// As such, english is used as the default, and the first page has instructions "
        "to send a command (which can be localized)."
    )
    after_note = "// OmkalityCraft: literal Russian pages, serialized before installation; no server-side client I18n."
    prefix = 'val dj2bag_of_truth_lockedname = "Bag";\n'
    suffix = (
        '], author: "Atricos", title: dj2introductionbookname, resolved: 1 as byte}));\n'
        "add(<minecraft:paper>);\nrecipes.keep();\n"
    )
    original = (
        prefix
        + (
            'val dj2introductionbookname = "Welcome";\nval dj2introductionpapername = "Keys";\n'
            'val dj2introductionpaperdesc0 = "A";\nval dj2introductionpaperdesc1 = "B";\n'
            'val dj2introductionpaperdesc2 = "C";\nval dj2introductionbookdesc0 = "Old page";\n'
        )
        + note
        + '\nadd(<minecraft:written_book>.withTag({pages: ["old"]'
        + suffix[1:]
    ).encode()
    expected = (
        prefix
        + (
            'val dj2introductionbookname = "Введение";\nval dj2introductionpapername = "Клавиши";\n'
            'val dj2introductionpaperdesc0 = "А";\nval dj2introductionpaperdesc1 = "Б";\n'
            'val dj2introductionpaperdesc2 = "В";\n'
        )
        + after_note
        + '\nadd(<minecraft:written_book>.withTag({pages: [\n    "{\\"text\\":\\"Русский текст\\"}",\n'
        + suffix
    ).encode()
    review = {
        "schema": 1,
        "source_sha256": sha(original),
        "result_sha256": sha(expected),
        "book_title": "Введение",
        "paper_title": "Клавиши",
        "paper_lore": ["А", "Б", "В"],
        "pages": ["Русский текст"],
    }
    resources = {
        "resources/demo/lang/ru_ru.lang": b"k=value\n",
        "licenses/demo.txt": b"author",
    }
    client = b"already verified owned component bytes"
    lock = {
        "schema": 1,
        "pack": "dj2",
        "version": "2.23.4",
        "locale_archive_sha256": "a" * 64,
        "client": {
            "version": "0.1.3",
            "path": "mods/OmkalityClient-0.1.3.jar",
            "sha256": sha(client),
            "size": len(client),
        },
        "initial_inventory": {
            "path": "scripts/ModSpecific/InitialInventory.zs",
            "source_sha256": sha(original),
            "result_sha256": sha(expected),
        },
        "resources": [
            {"path": k, "sha256": sha(v), "size": len(v)} for k, v in resources.items()
        ],
        "jvm_args_required": [
            "-Domkality.books.locale.forge112=true",
            "-Domkality.appearance.forge112=true",
        ],
    }
    return (
        {
            "resources": resources,
            "script": original,
            "client": client,
            "lock": lock,
            "book_review": review,
        },
        expected,
    )
