from launcher.pack.keybindings import saved_legacy_key_labels


def test_reads_forge_control_with_modifier_mouse_and_grave(tmp_path):
    (tmp_path / "options.txt").write_text(
        "lang:ru_ru\nkey_book:37\nkey_mouse:-96\n"
        "key_book:41:SHIFT\nkey_inv:18\nkey_unbound:0\n"
        "key_invalid:17:UNKNOWN\nkey_broken:keycode\n",
        encoding="utf-8",
    )
    assert saved_legacy_key_labels(
        tmp_path, "book", "mouse", "inv", "unbound", "invalid", "broken", "missing"
    ) == {"book": "Shift + Ё / `", "mouse": "Кнопка мыши 5", "inv": "E"}


def test_unavailable_options_does_not_invent_a_key(tmp_path):
    assert saved_legacy_key_labels(tmp_path, "book") == {}
    (tmp_path / "options.txt").write_bytes(b"key_book:37\xff")
    assert saved_legacy_key_labels(tmp_path, "book") == {}
