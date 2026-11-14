import copy
import hashlib
import json
from pathlib import Path

import pytest

from launcher.releases import ReleaseError
from omk.dj2_locale_bundle import compose_locale_bundle, render_initial_book


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


def test_literal_book_and_complete_generation_match_review(inputs):
    data, expected = inputs
    before = copy.deepcopy(data)
    result = compose_locale_bundle(**data)
    assert result["scripts/ModSpecific/InitialInventory.zs"] == expected
    assert len(result) == 4
    assert data == before
    assert b"recipes.keep();" in expected and b'"Bag"' in expected


@pytest.mark.parametrize(
    "fault",
    [
        "source",
        "target",
        "author",
        "recipe",
        "missing_literal",
        "duplicate_literal",
        "title",
        "pages",
        "lore",
        "schema",
        "unknown",
    ],
)
def test_book_refuses_drift_before_returning_any_installation(inputs, fault):
    data, _ = inputs
    source, review = data["script"], data["book_review"]
    if fault == "source":
        source += b" "
    elif fault == "target":
        review["result_sha256"] = "0" * 64
    elif fault in {"author", "recipe", "missing_literal", "duplicate_literal"}:
        old, new = {
            "author": (b"Atricos", b"Other"),
            "recipe": (b"recipes.keep();", b"recipes.removeAll();"),
            "missing_literal": (b"val dj2introductionpaperdesc0", b"val other"),
            "duplicate_literal": (
                b'val dj2introductionpaperdesc0 = "A";',
                b'val dj2introductionpaperdesc0 = "A";val dj2introductionpaperdesc0 = "A";',
            ),
        }[fault]
        source = source.replace(old, new)
        # Even a new source pin cannot silently reuse an old accepted output.
        review["source_sha256"] = sha(source)
    elif fault == "title":
        review["book_title"] = "x" * 33
    elif fault == "pages":
        review["pages"] = []
    elif fault == "lore":
        review["paper_lore"] = ["one"]
    elif fault == "schema":
        review["schema"] = 2
    else:
        review["exec"] = "not supported"
    with pytest.raises(ValueError):
        render_initial_book(source, review)


@pytest.mark.parametrize(
    "fault",
    [
        "missing",
        "extra",
        "corrupt",
        "length",
        "duplicate",
        "case",
        "escape",
        "personal",
        "script_path",
        "client",
        "client_size",
        "shared_script",
        "flags",
        "schema",
    ],
)
def test_generation_rejects_mixed_or_unsafe_inputs(inputs, fault):
    data, _ = inputs
    lock = data["lock"]
    row = lock["resources"][0]
    if fault == "missing":
        data["resources"].pop(row["path"])
    elif fault == "extra":
        data["resources"]["resources/personal.txt"] = b"private"
    elif fault == "corrupt":
        data["resources"][row["path"]] += b"drift"
    elif fault == "length":
        row["size"] += 1
    elif fault == "duplicate":
        lock["resources"].append(dict(row))
    elif fault == "case":
        lock["resources"].append(dict(row, path=row["path"].upper()))
    elif fault in {"escape", "personal", "script_path"}:
        path = {
            "escape": "resources/../outside",
            "personal": "options.txt",
            "script_path": "scripts/Other.zs",
        }[fault]
        data["resources"][path] = data["resources"].pop(row["path"])
        row["path"] = path
    elif fault == "client":
        data["client"] += b"corrupt"
    elif fault == "client_size":
        lock["client"]["size"] += 1
    elif fault == "shared_script":
        lock["initial_inventory"]["result_sha256"] = "0" * 64
    elif fault == "flags":
        lock["jvm_args_required"] = []
    else:
        lock["schema"] = 2
    with pytest.raises((ValueError, ReleaseError)):
        compose_locale_bundle(**data)


def test_checked_in_generation_agrees_with_component_and_book_pins():
    root = Path(__file__).resolve().parents[2]
    profile = root / "profiles/locale-overlays/dj2-2.23.4"
    lock = json.loads((profile / "bundle-lock.json").read_bytes())
    book = json.loads((profile / "initial-book-review.json").read_bytes())
    client = json.loads((root / "mods/forge-1.12.2/versions.json").read_bytes())[
        "artifacts"
    ]["client"]
    assert lock["client"]["sha256"] == client["sha256"]
    assert lock["client"]["version"] == client["version"]
    assert lock["initial_inventory"]["result_sha256"] == book["result_sha256"]
    assert len(lock["resources"]) == 681 and len(book["pages"]) == 18
    assert len({x["path"].casefold() for x in lock["resources"]}) == 681


@pytest.mark.parametrize(
    "fault",
    [
        "book_bool",
        "lock_bool",
        "archive",
        "pack",
        "version",
        "mod_version",
        "resource_limit",
        "total_limit",
    ],
)
def test_generation_contract_and_memory_limits(inputs, fault, monkeypatch):
    data, _ = inputs
    if fault == "book_bool":
        data["book_review"]["schema"] = True
    elif fault == "lock_bool":
        data["lock"]["schema"] = True
    elif fault == "archive":
        data["lock"]["locale_archive_sha256"] = "wrong"
    elif fault == "pack":
        data["lock"]["pack"] = "gtnh"
    elif fault == "version":
        data["lock"]["version"] = False
    elif fault == "mod_version":
        data["lock"]["client"]["version"] = "../../unknown"
    else:
        monkeypatch.setattr(
            "omk.dj2_locale_bundle."
            + (
                "MAX_RESOURCE_BYTES"
                if fault == "resource_limit"
                else "MAX_BUNDLE_BYTES"
            ),
            1,
        )
    with pytest.raises(ValueError):
        compose_locale_bundle(**data)


@pytest.mark.parametrize(
    "page", ['Кавычки: "пример"; C:\\test\nё %s', '"; recipes.removeAll(); //']
)
def test_book_page_stays_a_string_not_script_code(inputs, page):
    data, expected = inputs
    review = data["book_review"]
    old = json.dumps(
        json.dumps(
            {"text": "Русский текст"}, ensure_ascii=False, separators=(",", ":")
        ),
        ensure_ascii=False,
    )
    new = json.dumps(
        json.dumps({"text": page}, ensure_ascii=False, separators=(",", ":")),
        ensure_ascii=False,
    )
    expected = expected.replace(old.encode(), new.encode())
    review["pages"] = [page]
    review["result_sha256"] = sha(expected)
    result = render_initial_book(data["script"], review)
    assert result == expected
    literal = result.decode().split("pages: [\n", 1)[1].lstrip()
    decoded, _ = json.JSONDecoder().raw_decode(literal)
    assert json.loads(decoded) == {"text": page}
    assert result.endswith(b"add(<minecraft:paper>);\nrecipes.keep();\n")
