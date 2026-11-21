import json
import tomllib
from copy import deepcopy
from dataclasses import replace

import pytest

from omk.shared.profiles import PROJECT_ROOT, _requirements, load_profiles


def test_profile_requirements_are_optional_for_existing_profiles(tmp_path):
    profile = load_profiles()[0]
    document = replace(profile, requirements=None).as_dict()
    document.pop("requirements")
    path = tmp_path / "profiles.toml"
    path.write_text(
        "schema_version = 1\n[[servers]]\n"
        + "\n".join(
            f"{key} = {json.dumps(value, ensure_ascii=False)}"
            for key, value in document.items()
        ),
        encoding="utf-8",
    )
    assert load_profiles(path)[0].requirements is None


def test_requirements_are_serializable_and_include_both_tiers():
    (dj2,) = load_profiles()
    assert dj2.requirements.state == "preliminary"
    assert dj2.requirements.minimum.ram_gb == 8
    assert dj2.requirements.recommended.ram_gb == 16
    assert dj2.memory_default_mb == 6144
    assert (
        json.loads(json.dumps(dj2.as_dict()))["requirements"]["recommended"]["ram_gb"]
        == 16
    )


@pytest.mark.parametrize(
    "path,value",
    [
        (("state",), []),
        (("scope",), ""),
        (("recommended", "ram_gb"), True),
        (("recommended", "storage_gb"), 0),
        (("recommended", "cpu"), "x" * 241),
        (("recommended",), "unknown"),
        (("state",), "pending"),
    ],
)
def test_invalid_editorial_data_is_rejected(path, value):
    data = tomllib.loads(
        (PROJECT_ROOT / "profiles/servers.toml").read_text(encoding="utf-8")
    )["servers"][0]["requirements"]
    target = data
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ValueError):
        _requirements(data)


def test_minimum_cannot_exceed_recommendation():
    data = tomllib.loads(
        (PROJECT_ROOT / "profiles/servers.toml").read_text(encoding="utf-8")
    )["servers"][0]["requirements"]
    data["minimum"] = deepcopy(data["recommended"])
    data["minimum"]["ram_gb"] = 32
    with pytest.raises(ValueError):
        _requirements(data)
