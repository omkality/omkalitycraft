import json

import pytest

from omk.dj2_rtp_policy import POLICY_FILE, write_rtp_policy


def test_default_profile_and_exclusive_offline_creation(tmp_path):
    plan = write_rtp_policy(tmp_path, {})
    assert (plan["minimum"], plan["maximum"], plan["border_percent"]) == (
        1000,
        5461,
        66,
    )
    assert {row["id"] for row in plan["worlds"]} == {0, -1, 7}
    nether = next(row for row in plan["worlds"] if row["id"] == -1)
    assert nether["mode"] == "cave" and nether["max_y"] == 120
    before = (tmp_path / POLICY_FILE).read_bytes()
    with pytest.raises(FileExistsError):
        write_rtp_policy(tmp_path, {"OMK_DJ2_RTP_MAX_DISTANCE": "6000"})
    assert (tmp_path / POLICY_FILE).read_bytes() == before


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("MIN_DISTANCE", "-1"),
        ("MAX_DISTANCE", "0"),
        ("MAX_DISTANCE", "100001"),
        ("MAX_DISTANCE", "secret-synthetic"),
        ("BORDER_PERCENT", "91"),
        ("BORDER_PERCENT", "65.5"),
        ("ATTEMPTS", "257"),
        ("CHUNK_LOADS", "17"),
        ("RETRY_SECONDS", "1"),
    ],
)
def test_bad_environment_does_not_write_or_expose_value(tmp_path, key, value):
    variable = "OMK_DJ2_RTP_" + key
    with pytest.raises(ValueError) as error:
        write_rtp_policy(tmp_path, {variable: value})
    assert str(error.value) == "Invalid " + variable
    assert not (tmp_path / POLICY_FILE).exists()


def test_inverted_radius_is_rejected_before_file_creation(tmp_path):
    with pytest.raises(ValueError, match="distance range"):
        write_rtp_policy(tmp_path, {"OMK_DJ2_RTP_MIN_DISTANCE": "6000"})
    assert not (tmp_path / POLICY_FILE).exists()


@pytest.mark.parametrize(
    "bad", ["mode", "duplicate", "y", "boolean", "unknown", "oversize"]
)
def test_invalid_operator_world_profile_is_not_applied(tmp_path, bad):
    row = {"id": 0, "mode": "surface", "min_y": 8, "max_y": 253}
    profile = {"version": 1, "worlds": [row]}
    if bad == "mode":
        row["mode"] = "secret-synthetic"
    elif bad == "duplicate":
        profile["worlds"].append(dict(row))
    elif bad == "y":
        row["max_y"] = 256
    elif bad == "boolean":
        row["id"] = True
    elif bad == "unknown":
        row["secret-synthetic"] = "value"
    file = tmp_path / "operator.json"
    file.write_text(" " * 4097 if bad == "oversize" else json.dumps(profile))
    with pytest.raises(ValueError, match=r"^Invalid OMK_DJ2_RTP_PROFILE$"):
        write_rtp_policy(tmp_path, {"OMK_DJ2_RTP_PROFILE": str(file)})
    assert not (tmp_path / POLICY_FILE).exists()


def test_custom_operator_profile_can_use_a_future_resource_dimension(tmp_path):
    profile = tmp_path / "operator.json"
    profile.write_text(
        json.dumps(
            {
                "version": 1,
                "worlds": [{"id": 1234, "mode": "surface", "min_y": 8, "max_y": 253}],
            }
        )
    )
    result = write_rtp_policy(tmp_path, {"OMK_DJ2_RTP_PROFILE": str(profile)})
    assert result["worlds"][0]["id"] == 1234
    assert "worlds=1234:surface:8:253\n" in (tmp_path / POLICY_FILE).read_text()
