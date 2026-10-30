import json
from dataclasses import replace
from pathlib import Path

import pytest

from launcher.memory import MemorySnapshot, Preferences, choose_memory
from omk.profiles import load_profiles


@pytest.mark.parametrize(
    "system_mb, expected", [(4096, 2048), (8192, 5120), (16384, 8192), (65536, 8192)]
)
def test_heap_limit_leaves_headroom_and_respects_pack_cap(system_mb, expected):
    profile = load_profiles()[0]
    machine = MemorySnapshot(system_mb, system_mb)
    choice = choose_memory(profile, machine, 1024 * 100)
    assert choice.maximum_mb == expected
    assert choice.selected_mb == expected


def test_low_memory_uses_available_budget_and_warns():
    profile = load_profiles()[0]
    choice = choose_memory(profile, MemorySnapshot(4096, 3000))
    assert choice.selected_mb == 2048
    assert "не запуститься" in choice.warning


def test_pack_defaults_are_independent_and_pressure_is_visible():
    first = load_profiles()[0]
    second = replace(
        first, id="other", memory_default_mb=4096, memory_recommended_mb=4096
    )
    machine = MemorySnapshot(16384, 2048)
    assert choose_memory(first, machine).selected_mb == 6144
    assert choose_memory(second, machine).selected_mb == 4096
    assert "свободной" in choose_memory(first, machine).warning


def test_preferences_persist_per_pack_without_any_account_fields(tmp_path: Path):
    path = tmp_path / "preferences.json"
    preferences = Preferences(path)
    preferences.save_memory("dj2", 5120)
    preferences.save_memory("gtnh", 6144)
    assert Preferences(path).memory == {"dj2": 5120, "gtnh": 6144}
    assert set(json.loads(path.read_text())) == {"schema", "memory"}
    assert not list(tmp_path.glob(".omk-write-*"))


def test_malformed_preferences_and_absurd_values_are_not_used(tmp_path: Path):
    path = tmp_path / "preferences.json"
    path.write_text('{"schema":1,"memory":{"dj2":true,"gtnh":999999}}')
    assert Preferences(path).memory == {}
    path.write_text("not JSON")
    assert Preferences(path).memory == {}
    with pytest.raises(ValueError):
        Preferences(path).save_memory("dj2", 100000)
