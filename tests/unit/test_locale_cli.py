import hashlib
import json

import pytest

from omk.cli import main
from omk.locale_overlay import MAX_LANG_BYTES


def test_cli_reports_changes_and_hashes_without_writing_inputs(tmp_path, capsys):
    source, locale, previous = [tmp_path / name for name in ("en", "ru", "old")]
    source.write_bytes(b"key=new %s\n")
    locale.write_bytes("key=новое %s\nextra=старое\n".encode())
    previous.write_bytes(b"key=old %s\n")
    before = [p.read_bytes() for p in (source, locale, previous)]
    assert (
        main(
            [
                "locale",
                "audit",
                "--source",
                str(source),
                "--locale",
                str(locale),
                "--previous-source",
                str(previous),
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert result["changed_source_values"] == ["key"]
    assert result["extra"] == ["extra"]
    assert result["read_only"] and result["semantic_review_required"]
    assert not result["game_tested"]
    assert result["sha256"]["source"] == hashlib.sha256(before[0]).hexdigest()
    assert [p.read_bytes() for p in (source, locale, previous)] == before


@pytest.mark.parametrize("translated", [b"other=text\n", b"key=%d\n"])
def test_missing_keys_and_incompatible_arguments_fail(tmp_path, capsys, translated):
    source, locale = tmp_path / "en", tmp_path / "ru"
    source.write_bytes(b"key=%s\n")
    locale.write_bytes(translated)
    assert (
        main(["locale", "audit", "--source", str(source), "--locale", str(locale)]) == 1
    )
    assert json.loads(capsys.readouterr().out)["ok"] is False


@pytest.mark.parametrize("kind", ["missing", "bad_utf8", "oversized", "duplicate"])
def test_bad_input_is_bounded_and_errors_do_not_echo_content(tmp_path, capsys, kind):
    source, locale = tmp_path / "private-path", tmp_path / "ru"
    payload = {
        "bad_utf8": b"secret=\xff",
        "oversized": b"s" * (MAX_LANG_BYTES + 1),
        "duplicate": b"secret=1\nsecret=2",
    }
    if kind != "missing":
        source.write_bytes(payload[kind])
    locale.write_bytes(b"x=1")
    assert (
        main(["locale", "audit", "--source", str(source), "--locale", str(locale)]) == 1
    )
    output = capsys.readouterr().out
    assert json.loads(output) == {
        "ok": False,
        "error": "Unreadable or invalid language input",
    }
    assert "secret" not in output and "private-path" not in output
