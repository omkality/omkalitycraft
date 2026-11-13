import hashlib

import pytest

from omk import locale_overlay


def pin(value):
    return hashlib.sha256(value.encode()).hexdigest()


def reuse(**overrides):
    arguments = {
        "english": b"x=Input: %s\nexisting=Keep\n",
        "russian": "# Local comment\r\nexisting=Прежний текст\r\n".encode(),
        "source_english": b"x=Input: %s\nmodern=Only upstream\n",
        "source_russian": "x=Вход: %s\nmodern=Новая возможность\n".encode(),
        "expected_source_sha256": {"x": pin("Input: %s")},
        "expected_translation_sha256": {"x": pin("Вход: %s")},
    }
    arguments.update(overrides)
    return locale_overlay.reuse_reviewed_lang_values(**arguments)


def test_reuse_only_the_explicitly_approved_missing_key_and_preserve_existing_bytes():
    before = "# Local comment\r\nexisting=Прежний текст\r\n".encode()
    result = reuse(russian=before)
    assert result.startswith(before)
    assert locale_overlay.parse_lang(result) == {
        "existing": "Прежний текст",
        "x": "Вход: %s",
    }


@pytest.mark.parametrize(
    "russian", [b"x=Input: %s\n", "x=Более свежий перевод: %s\n".encode()]
)
def test_reuse_never_overwrites_a_present_key_even_when_it_contains_english(russian):
    with pytest.raises(ValueError, match="existing"):
        reuse(russian=russian)


@pytest.mark.parametrize(
    "overrides",
    [
        {"english": b"x=Output: %s\n"},
        {"source_english": b"x=Output: %s\n"},
        {"source_russian": "x=Выход: %s\n".encode()},
        {"english": b"other=Input: %s\n"},
        {"source_english": b"other=Input: %s\n"},
        {"source_russian": "other=Вход: %s\n".encode()},
        {"expected_source_sha256": None},
        {"expected_translation_sha256": None},
        {"expected_source_sha256": {}},
        {"expected_translation_sha256": {}},
        {"expected_translation_sha256": {"other": pin("Вход: %s")}},
        {"expected_source_sha256": {"x": "invalid"}},
        {"expected_translation_sha256": {"x": "invalid"}},
    ],
    ids=[
        "target_english_changed",
        "source_english_changed",
        "translation_changed",
        "target_key_missing",
        "source_key_missing",
        "translation_key_missing",
        "no_english_guard",
        "no_russian_guard",
        "empty_english_guard",
        "empty_russian_guard",
        "unequal_guard_keys",
        "invalid_english_hash",
        "invalid_russian_hash",
    ],
)
def test_reuse_requires_both_exact_sources_and_the_exact_approved_key_set(overrides):
    with pytest.raises(ValueError):
        reuse(**overrides)


def test_reviewed_hashes_do_not_bypass_the_target_placeholder_contract():
    with pytest.raises(ValueError, match="contract"):
        reuse(
            source_russian="x=Вход: %d\n".encode(),
            expected_translation_sha256={"x": pin("Вход: %d")},
        )


def test_reuse_does_not_treat_an_english_copy_as_a_translation():
    with pytest.raises(ValueError):
        reuse(
            source_russian=b"x=Input: %s\n",
            expected_translation_sha256={"x": pin("Input: %s")},
        )


def test_reuse_rejects_a_source_with_ambiguous_duplicate_keys():
    with pytest.raises(ValueError, match="duplicate"):
        reuse(source_russian="x=Вход: %s\nx=Иное: %s\n".encode())
