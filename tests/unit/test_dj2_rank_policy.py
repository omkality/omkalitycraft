import pytest

from omk.dj2_rank_policy import apply_player_limits


def fixture(path):
    raw = (
        b"// fixture\r\n[player]\r\nftbutilities.homes.max: 3\r\n"
        b"ftbutilities.claims.max_chunks: 50\r\nother: true\r\n"
        b"[optional extends player]\r\nftbutilities.homes.max: 8\r\n"
    )
    path.write_bytes(raw)
    return raw


def test_defaults_are_idempotent_and_other_roles_are_preserved(tmp_path):
    path = tmp_path / "ranks.txt"
    before = fixture(path)
    assert apply_player_limits(path, {}) == {
        "ftbutilities.claims.max_chunks": 50,
        "ftbutilities.homes.max": 3,
    }
    assert path.read_bytes() == before
    apply_player_limits(
        path, {"OMK_DJ2_CLAIMS_PER_PLAYER": "75", "OMK_DJ2_HOMES_PER_PLAYER": "4"}
    )
    assert path.read_bytes() == before.replace(
        b"max_chunks: 50", b"max_chunks: 75"
    ).replace(b"homes.max: 3", b"homes.max: 4")


@pytest.mark.parametrize(
    "value", ["0", "-1", "1.5", "3\n", " 3", "30001", "secret-synthetic", ""]
)
def test_bad_limit_does_not_write_or_echo_its_value(tmp_path, value):
    path = tmp_path / "ranks.txt"
    before = fixture(path)
    with pytest.raises(ValueError, match="OMK_DJ2_CLAIMS_PER_PLAYER") as raised:
        apply_player_limits(path, {"OMK_DJ2_CLAIMS_PER_PLAYER": value})
    assert "secret-synthetic" not in str(raised.value)
    assert path.read_bytes() == before


@pytest.mark.parametrize("change", ["missing", "duplicate", "section", "large"])
def test_unknown_or_ambiguous_rank_file_is_not_rewritten(tmp_path, change):
    path = tmp_path / "ranks.txt"
    raw = fixture(path)
    raw = {
        "missing": raw.replace(b"ftbutilities.homes.max: 3", b"unknown: 3"),
        "duplicate": raw.replace(b"other: true", b"ftbutilities.homes.max: 3"),
        "section": raw + b"[player]\nfoo: 1\n",
        "large": raw + b"x" * 65536,
    }[change]
    path.write_bytes(raw)
    with pytest.raises(ValueError):
        apply_player_limits(path, {})
    assert path.read_bytes() == raw
