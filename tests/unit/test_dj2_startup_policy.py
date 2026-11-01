import pytest

from omk.dj2_startup_policy import ENV, configure_remapper


def test_only_target_changes_in_owned_copy_and_policy_is_idempotent(
    tmp_path, monkeypatch
):
    monkeypatch.delenv(ENV, raising=False)
    path = tmp_path / "normalasm.cfg"
    data = b"# retain comments\r\n  B:optimizeFMLRemapper=true\r\nB:other=true\r\n"
    path.write_bytes(data)
    assert configure_remapper(path) == {"optimize_fml_remapper": False, "changed": True}
    expected = data.replace(b"Remapper=true", b"Remapper=false")
    assert path.read_bytes() == expected
    assert not configure_remapper(path)["changed"]
    assert path.read_bytes() == expected


@pytest.mark.parametrize("value", ["TRUE", "1", "", "false\n", "maybe"])
def test_bad_operator_env_fails_before_any_write(tmp_path, monkeypatch, value):
    monkeypatch.setenv(ENV, value)
    path = tmp_path / "normalasm.cfg"
    path.write_bytes(b"B:optimizeFMLRemapper=true\n")
    before = path.read_bytes()
    with pytest.raises(ValueError, match="must be true or false"):
        configure_remapper(path)
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    "data",
    [
        b"# missing",
        b"B:optimizeFMLRemapper=maybe\n",
        b"B:optimizeFMLRemapper=true\n" * 2,
        b"B:optimizeFMLRemapper=true\nB:optimizeFMLRemapper=bad\n",
        b"x" * (1024 * 1024 + 1),
    ],
    ids=["missing", "unsupported", "duplicate", "mixed-duplicate", "oversize"],
)
def test_unexpected_or_oversize_config_is_not_silently_rewritten(tmp_path, data):
    path = tmp_path / "normalasm.cfg"
    path.write_bytes(data)
    with pytest.raises(ValueError, match="exactly one"):
        configure_remapper(path, optimize=False)
    assert path.read_bytes() == data


def test_explicit_control_overrides_environment(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV, "false")
    path = tmp_path / "normalasm.cfg"
    path.write_bytes(b"B:optimizeFMLRemapper=false\n")
    assert configure_remapper(path, optimize=True)["optimize_fml_remapper"]
    assert path.read_bytes() == b"B:optimizeFMLRemapper=true\n"


def test_operator_env_allows_enabled_control(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV, "true")
    path = tmp_path / "normalasm.cfg"
    path.write_bytes(b"B:optimizeFMLRemapper=false\n")
    assert configure_remapper(path)["optimize_fml_remapper"]


def test_missing_config_and_non_boolean_explicit_policy_are_rejected(tmp_path):
    with pytest.raises(ValueError, match="regular staged"):
        configure_remapper(tmp_path / "absent.cfg", optimize=False)
    with pytest.raises(ValueError, match="must be boolean"):
        configure_remapper(tmp_path / "absent.cfg", optimize="false")
