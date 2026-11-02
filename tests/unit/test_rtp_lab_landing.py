from types import SimpleNamespace

import pytest

from omk.dj2_rtp_lab import RtpScenario, _landed


@pytest.mark.parametrize(
    ("position", "dimension", "expected"),
    [
        (None, 7, False),
        ((24.5, 246.01, 24.5), 7, False),  # Correct height at the departure is not RTP.
        ((8.5, 246.01, 0.5), 0, False),  # Same coordinates in a different world.
        ((8.5, 241, 0.5), 7, False),
        ((0.5, 246.01, 0.5), 7, False),
        ((12.5, 246.01, 0.5), 7, False),
        ((8.5, 246.01, 0.5), 7, True),
    ],
)
def test_landing_requires_destination_world_floor_and_annulus(
    position, dimension, expected
):
    actor = SimpleNamespace(position=position, dimension=dimension)
    assert _landed(actor, 7, 246) is expected


def test_landing_uses_the_actual_border_center():
    actor = SimpleNamespace(position=(136.5, 246.01, 128.5), dimension=7)
    assert not _landed(actor, 7, 246)
    assert _landed(actor, 7, 246, 128, 128)


@pytest.mark.parametrize(
    ("requested", "actual", "accepted"),
    [
        ("water", "water", True),
        ("water", "flowing_water", True),
        ("water", "air", False),
        ("wool", "flowing_water", False),
    ],
)
def test_surface_proves_a_fluid_variant_and_does_not_accept_a_different_material(
    tmp_path, monkeypatch, requested, actual, accepted
):
    monkeypatch.setattr("omk.dj2_rtp_lab._place", lambda *_: None)
    monkeypatch.setattr("omk.dj2_rtp_lab.PROJECT_ROOT", tmp_path)
    (tmp_path / ".local").mkdir()
    scenario = RtpScenario(None, {"checks": []})
    scenario.wait_loaded = lambda *_: None
    scenario.at = lambda _name, command: (
        "Successfully found the block"
        if command.startswith("testforblock ")
        and command.endswith("minecraft:" + actual)
        else "The block is Water (expected Water)"
    )
    actor = SimpleNamespace(dimension=0)
    if accepted:
        scenario.surface(actor, "fixture", material=requested)
        assert scenario.report["surface_fixtures"][-1]["observed"] == actual
    else:
        with pytest.raises(RuntimeError, match="surface_fixture_"):
            scenario.surface(actor, "fixture", material=requested)
