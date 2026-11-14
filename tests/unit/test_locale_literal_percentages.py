"""Literal chance prose is not a Java character/float format directive."""

import hashlib

import pytest

from omk.locale_overlay import parse_lang, render_lang


def render(source, russian, **overrides):
    return render_lang(
        b"# kept\ny=old\n",
        ("x=" + source + "\n").encode(),
        additions={"x": russian},
        expected_source_sha256={"x": hashlib.sha256(source.encode()).hexdigest()},
        literal_percentage_keys={"x"},
        **overrides,
    )


def test_reviewed_literal_chance_text_keeps_percent_and_unrelated_bytes():
    result = render("20% chance to burn the target.", "Шанс поджечь цель: 20%.")
    assert result.startswith(b"# kept\ny=old\n")
    assert parse_lang(result)["x"] == "Шанс поджечь цель: 20%."


def test_default_format_contract_still_rejects_literal_chance_conversion():
    with pytest.raises(ValueError, match="contract"):
        render_lang(b"", b"x=20% chance", additions={"x": "Вероятность: 20%."})


@pytest.mark.parametrize(
    ("english", "russian"),
    [
        ("20% chance, %s required", "Шанс 20%, требуется %d"),
        ("20% chance, %s required", "Шанс 20%, ничего не требуется"),
        ("20% chance", "Шанс 20%, предмет %s"),
        ("20% chance", "Шанс 20"),
        ("20% chance", "Шанс 20%%"),
        ("20% chance", "Шанс 20%.\nx=injected"),
    ],
)
def test_literal_mode_does_not_hide_arguments_percent_changes_or_line_injection(
    english, russian
):
    with pytest.raises(ValueError):
        render(english, russian)


def test_literal_mode_retains_a_separate_actual_argument():
    assert (
        parse_lang(render("20% chance, %s required", "Шанс 20%, требуется %s"))["x"]
        == "Шанс 20%, требуется %s"
    )


@pytest.mark.parametrize("keys", [{"missing"}, {"x", "missing"}, "x"])
def test_literal_rules_must_name_only_changed_keys(keys):
    with pytest.raises(ValueError):
        render_lang(
            b"",
            b"x=20% chance",
            additions={"x": "Шанс 20%."},
            expected_source_sha256={"x": hashlib.sha256(b"20% chance").hexdigest()},
            literal_percentage_keys=keys,
        )


def test_literal_rules_require_source_hash_guards():
    with pytest.raises(ValueError):
        render_lang(
            b"",
            b"x=20% chance",
            additions={"x": "Шанс 20%."},
            literal_percentage_keys={"x"},
        )


def test_literal_rules_reject_stale_english_with_unchanged_key():
    with pytest.raises(ValueError, match="source"):
        render_lang(
            b"",
            b"x=40% chance",
            additions={"x": "Шанс 20%."},
            expected_source_sha256={"x": hashlib.sha256(b"20% chance").hexdigest()},
            literal_percentage_keys={"x"},
        )
