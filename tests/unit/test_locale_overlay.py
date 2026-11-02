import pytest

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
