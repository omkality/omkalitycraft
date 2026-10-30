import io

import pytest

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
