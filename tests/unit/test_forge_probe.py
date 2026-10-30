import io
from unittest.mock import Mock

import pytest

from omk.forge_player import LabPlayer
from omk.forge_probe import Connection, field, number, varint


def test_probe_protocol_numbers_and_packet_limits():
    for value in [0, 127, 128, 340, 2**31 - 1]:
        assert number(io.BytesIO(varint(value)).read) == value
    with pytest.raises(ValueError):
        varint(-1)
    with pytest.raises(ValueError):
        number(io.BytesIO(b"\x80" * 6).read)
    with pytest.raises(ValueError):
        field(io.BytesIO(varint(10**8)).read)


def test_security_probes_cannot_target_public_hosts():
    with pytest.raises(ValueError, match="loopback"):
        Connection("example.com", 25565)


@pytest.mark.parametrize(
    "point", [(float("nan"), 1, 1), (1, float("inf"), 1), (30000000, 1, 1)]
)
def test_lab_movement_rejects_invalid_coordinates_before_sending(point):
    player = LabPlayer.__new__(LabPlayer)
    player.check = Mock()
    player.send = Mock()
    with pytest.raises(ValueError, match="movement"):
        player.move(*point)
    player.send.assert_not_called()


@pytest.mark.parametrize("message", ["/op someone", "", "line\nbreak", "x" * 257])
def test_lab_chat_cannot_inject_commands_or_invalid_packets(message):
    player = LabPlayer.__new__(LabPlayer)
    player.check = Mock()
    player.send = Mock()
    with pytest.raises(ValueError, match="chat"):
        player.chat(message)
    player.send.assert_not_called()
