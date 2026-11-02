from types import SimpleNamespace

import pytest

from omk.dj2_rtp_lab import _landed


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
