import hashlib

import pytest

from omk import locale_overlay
from omk.locale_overlay import (
    MAX_LANG_BYTES,
    audit_lang,
    format_signature,
    parse_lang,
    render_lang,
)


def raw(text):
    return text.encode("utf-8")


def test_preserves_unrelated_comments_lines_and_equals_inside_value():
    base = raw("# note\r\nold=старое\r\nkeep=а=б\r\n\r\n")
    rendered = render_lang(base, b"old=new\nkeep=a=b\n", updates={"old": "новое"})
    assert rendered == raw("# note\r\nold=новое\r\nkeep=а=б\r\n\r\n")


def test_noop_preserves_bom_and_absent_final_newline():
    base = b"\xef\xbb\xbf# note\r\nx=unchanged"
    assert render_lang(base, b"x=unchanged") == base


def test_audit_distinguishes_coverage_format_and_stale_source():
    result = audit_lang(
        b"one=%s\ntwo=new\n", b"one=%d\nextra=old\n", b"one=%s\ntwo=old\n"
    )
    assert result["missing"] == ["two"]
    assert result["extra"] == ["extra"]
    assert result["format_mismatches"] == ["one"]
    assert result["changed_source_values"] == ["two"]
    assert result["game_tested"] is False


def test_numbered_arguments_can_reorder_but_types_and_unindexed_order_cannot():
    assert format_signature("%2$d %1$s") == format_signature("%1$s %2$d")
    assert format_signature("%s %d") != format_signature("%d %s")
    assert format_signature("%1$s") != format_signature("%1$d")
    assert format_signature("%s%n%%s") == format_signature("%s")


@pytest.mark.parametrize(
    "bad",
    [b"x=1\nx=2", b"broken", b"=empty", b"x=\0", b"x=" + b"a" * MAX_LANG_BYTES],
    ids=["duplicate", "broken", "empty", "nul", "oversized"],
)
def test_rejects_ambiguous_or_invalid_catalog(bad):
    with pytest.raises(ValueError):
        parse_lang(bad)


@pytest.mark.parametrize("value", ["%d", "%q", "%s\nnew=entry", "%s\0", "%s\r"])
def test_patch_cannot_change_argument_type_or_inject_entry(value):
    with pytest.raises(ValueError):
        render_lang(b"x=%s\n", b"x=%s\n", updates={"x": value})


def test_update_add_remove_are_explicit_and_disjoint():
    rendered = render_lang(
        b"old=x\nkept=y", b"kept=z\nnew=%s\n", additions={"new": "%s"}, removals={"old"}
    )
    assert rendered == b"kept=y\nnew=%s\n"
    for changes in [
        {"updates": {"missing": "x"}},
        {"additions": {"kept": "x"}},
        {"removals": {"missing"}},
        {"updates": {"kept": "z"}, "removals": {"kept"}},
    ]:
        with pytest.raises(ValueError):
            render_lang(b"kept=x", b"kept=z", **changes)


def source_pin(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def test_reviewed_translation_is_bound_to_english_meaning_not_only_key_and_format():
    patch = {"recipe": "Используйте железо: %s"}
    pins = {"recipe": source_pin("Use iron: %s")}
    assert render_lang(
        b"# keep\nother=unchanged\n",
        b"other=unchanged\nrecipe=Use iron: %s\n",
        additions=patch,
        expected_source_sha256=pins,
    ) == raw("# keep\nother=unchanged\nrecipe=Используйте железо: %s\n")
    # Same ID and same placeholder, but changed ingredient: do not silently reuse old RU.
    with pytest.raises(ValueError, match="source"):
        render_lang(
            b"other=unchanged\n",
            b"other=unchanged\nrecipe=Use gold: %s\n",
            additions=patch,
            expected_source_sha256=pins,
        )


@pytest.mark.parametrize(
    "pins",
    [
        {},
        {"x": "bad"},
        {"x": "a" * 64},
        {"x": None},
        {"x": source_pin("new"), "unreviewed": source_pin("other")},
        {"y": source_pin("new")},
    ],
    ids=["missing", "malformed", "wrong_digest", "wrong_type", "extra", "wrong_key"],
)
def test_source_guards_cover_exactly_all_changed_or_added_entries(pins):
    with pytest.raises(ValueError, match="source"):
        render_lang(
            b"x=old\n", b"x=new\n", updates={"x": "новое"}, expected_source_sha256=pins
        )


def test_source_guard_is_per_value_and_preserves_existing_russian_bytes():
    base = raw("\ufeff# keep\r\nother=остальное\r\nx=прежнее")
    assert render_lang(
        base,
        b"# different unrelated comments\nother=Changed unrelated source\nx=new\n",
        updates={"x": "новое"},
        expected_source_sha256={"x": source_pin("new")},
    ) == raw("\ufeff# keep\r\nother=остальное\r\nx=новое")


def test_valid_source_pin_does_not_disable_placeholder_validation():
    with pytest.raises(ValueError, match="contract"):
        render_lang(
            b"x=old\n",
            b"x=%d\n",
            updates={"x": "%s"},
            expected_source_sha256={"x": source_pin("%d")},
        )


def test_reviewed_edit_preserves_the_existing_translation_around_a_small_change():
    previous = "Знакомый текст. Энергия алтаря.%n%nХвост §cкрасный§r."
    edits = [{"kind": "replace", "old": "Энергия алтаря", "new": "Магическая сила"}]
    original_edits = [dict(e) for e in edits]
    result = locale_overlay.edit_reviewed_value(
        previous, expected_previous_sha256=source_pin(previous), edits=edits
    )
    assert result == "Знакомый текст. Магическая сила.%n%nХвост §cкрасный§r."
    assert edits == original_edits


def test_reviewed_edit_requires_the_exact_previous_russian_value():
    with pytest.raises(ValueError, match="previous"):
        locale_overlay.edit_reviewed_value(
            "Более новый перевод",
            expected_previous_sha256=source_pin("Старый перевод"),
            edits=[{"kind": "replace", "old": "перевод", "new": "текст"}],
        )


def test_reviewed_suffix_removal_is_exact_and_keeps_other_paragraphs():
    previous = "Основной текст.%n%nПримечание.%n%n§cСтарое предупреждение."
    result = locale_overlay.edit_reviewed_value(
        previous,
        expected_previous_sha256=source_pin(previous),
        edits=[{"kind": "truncate_before", "marker": "%n%n§c"}],
    )
    assert result == "Основной текст.%n%nПримечание."


@pytest.mark.parametrize(
    "edits",
    [
        [],
        [{"kind": "regex", "old": "x", "new": "y"}],
        [{"kind": "replace", "old": "x", "new": "y", "extra": 1}],
        [{"kind": "replace", "old": "", "new": "y"}],
        [{"kind": "replace", "old": "missing", "new": "y"}],
        [{"kind": "replace", "old": "x", "new": "y\ninjected=entry"}],
        [{"kind": "replace", "old": "x", "new": "y\0"}],
        [{"kind": "truncate_before", "marker": "missing"}],
        [{"kind": "truncate_before", "marker": ""}],
        [{"kind": "truncate_before", "marker": "x"}],
        [{"kind": "replace", "old": "x", "new": "x"}] * 9,
        [None],
    ],
    ids=[
        "empty",
        "unknown_operation",
        "unknown_field",
        "empty_old",
        "missing_old",
        "line_injection",
        "nul",
        "missing_marker",
        "empty_marker",
        "empty_result",
        "too_many_edits",
        "non_object",
    ],
)
def test_reviewed_edit_rejects_ambiguous_or_unbounded_operations(edits):
    with pytest.raises(ValueError):
        locale_overlay.edit_reviewed_value(
            "x", expected_previous_sha256=source_pin("x"), edits=edits
        )


@pytest.mark.parametrize("kind", ["replace", "truncate_before"])
def test_reviewed_edit_does_not_guess_between_duplicate_fragments(kind):
    edit = {
        "kind": kind,
        **({"old": "x", "new": "y"} if kind == "replace" else {"marker": "x"}),
    }
    with pytest.raises(ValueError):
        locale_overlay.edit_reviewed_value(
            "x and x", expected_previous_sha256=source_pin("x and x"), edits=[edit]
        )


def test_reviewed_edits_keep_literal_escape_sequences_and_still_need_source_validation():
    previous = "Начало\\nКлавиша: %s"
    updated = locale_overlay.edit_reviewed_value(
        previous,
        expected_previous_sha256=source_pin(previous),
        edits=[{"kind": "replace", "old": "Начало", "new": "Вступление"}],
    )
    assert updated == "Вступление\\nКлавиша: %s"
    with pytest.raises(ValueError, match="contract"):
        render_lang(b"", b"x=Key: %d", additions={"x": updated})


def test_reviewed_edit_checks_utf8_byte_budget_after_expansion():
    with pytest.raises(ValueError):
        locale_overlay.edit_reviewed_value(
            "x",
            expected_previous_sha256=source_pin("x"),
            edits=[{"kind": "replace", "old": "x", "new": "я" * MAX_LANG_BYTES}],
        )
