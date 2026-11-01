import pytest

from omk.dj2_spawn_policy import POLICY_FILE, spawn_plan, write_spawn_policy


def test_default_inclusive_spawn_square_uses_floor_for_negative_coordinates(tmp_path):
    plan = write_spawn_policy(tmp_path, {})
    assert plan == {
        "dimension": 0,
        "radius": 300,
        "chunk_min": -19,
        "chunk_max": 18,
        "chunks": 1444,
        "protected_min": -304,
        "protected_max": 303,
    }
    assert "zones=0:-300:300:-300:300\n" in (tmp_path / POLICY_FILE).read_text()
    with pytest.raises(FileExistsError):
        write_spawn_policy(tmp_path, {"OMK_DJ2_SPAWN_RADIUS": "500"})
    assert "zones=0:-300:300:-300:300\n" in (tmp_path / POLICY_FILE).read_text()


@pytest.mark.parametrize("radius", ["1", "16", "300", "768"])
def test_bounded_override_and_chunk_alignment(radius):
    plan = spawn_plan({"OMK_DJ2_SPAWN_RADIUS": radius})
    assert plan["protected_min"] <= -int(radius)
    assert plan["protected_max"] >= int(radius)
    assert plan["chunks"] <= 10000


@pytest.mark.parametrize(
    "value", ["0", "-1", "769", "300\n", " 300", "5.5", "", "secret-synthetic", None]
)
def test_invalid_config_does_not_write_or_echo_value(tmp_path, value):
    with pytest.raises(ValueError, match=r"^Invalid OMK_DJ2_SPAWN_RADIUS$"):
        write_spawn_policy(tmp_path, {"OMK_DJ2_SPAWN_RADIUS": value})
    assert not (tmp_path / POLICY_FILE).exists()


def test_existing_symlink_policy_is_never_followed(tmp_path):
    source, folder = tmp_path / "source", tmp_path / "config"
    source.write_text("preserve")
    folder.mkdir()
    try:
        (folder / POLICY_FILE).symlink_to(source)
    except OSError:
        pytest.skip("Symlink permission unavailable on this Windows host")
    with pytest.raises(FileExistsError):
        write_spawn_policy(folder, {})
    assert source.read_text() == "preserve"
