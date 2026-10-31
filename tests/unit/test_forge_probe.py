import io
import struct
from collections import deque
from unittest.mock import Mock

import pytest

from omk.forge_player import LabPlayer
from omk.forge_probe import Connection, field, number, text, varint


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


def test_lab_inventory_rejects_out_of_range_fixture_before_sending():
    player = LabPlayer.__new__(LabPlayer)
    player.check = Mock()
    player.send = Mock()
    valid = {
        "window_id": 1,
        "slot": 0,
        "action": 1,
        "item_id": 265,
        "count": 1,
        "damage": 0,
    }
    for key, bad in [
        ("window_id", 0),
        ("window_id", 256),
        ("slot", -1),
        ("slot", 1024),
        ("action", 32768),
        ("item_id", -1),
        ("count", 65),
        ("damage", -1),
        ("count", True),
    ]:
        with pytest.raises(ValueError, match="inventory click"):
            player.shift_click(**{**valid, key: bad})
    player.send.assert_not_called()


def test_lab_forge_window_rejects_invalid_ids_and_trailing_payload():
    player = LabPlayer.__new__(LabPlayer)
    player.open_windows = deque(maxlen=20)
    tail = text("ironchest") + struct.pack(">iiii", 0, 10, 241, 8)
    for payload in (
        b"\x01" + struct.pack(">i", 0) + tail,
        b"\x01" + struct.pack(">i", 256) + tail,
        b"\x01" + struct.pack(">i", 1) + tail + b"extra",
    ):
        with pytest.raises(ValueError, match="Forge lab window"):
            player._runtime(payload)
    # Other runtime messages (e.g. entity spawns) are not container openings.
    player._runtime(b"\x02unrelated")
    assert not player.open_windows


def test_forge_multipart_is_not_mistaken_for_runtime_gui_channel():
    player = LabPlayer.__new__(LabPlayer)
    player._runtime = Mock()
    player._custom_packet(io.BytesIO(text("FML|MP") + b"\x01multipart data"))
    player._runtime.assert_not_called()
    player._custom_packet(io.BytesIO(text("FML") + b"\x01gui data"))
    player._runtime.assert_called_once_with(b"\x01gui data")
