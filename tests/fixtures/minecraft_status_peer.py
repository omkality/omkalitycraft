"""Disposable Minecraft Java status-protocol peer with fixture-only data."""

import json
from socketserver import StreamRequestHandler, ThreadingTCPServer


def varint(number: int) -> bytes:
    result = bytearray()
    while number > 127:
        result.append((number & 127) | 128)
        number >>= 7
    return bytes(result) + bytes([number])


def read_frame(stream) -> bytes:
    length = 0
    for shift in range(0, 35, 7):
        byte = stream.read(1)
        if not byte:
            raise EOFError
        length |= (byte[0] & 127) << shift
        if byte[0] < 128:
            if not 1 <= length <= 4096:
                raise ValueError("Fixture packet size")
            return stream.read(length)
    raise ValueError("Fixture frame length")


class StatusHandler(StreamRequestHandler):
    """Accept a handshake followed by a status query and return fixed counts."""

    def handle(self) -> None:
        self.connection.settimeout(2)
        try:
            handshake = read_frame(self.rfile)
            if handshake[0] != 0 or handshake[-1] != 1 or read_frame(self.rfile) != b"\0":
                return
        except (EOFError, OSError, ValueError, IndexError):
            return
        payload = json.dumps({
            "version": {"name": "fixture", "protocol": 340},
            "players": {
                "online": 3, "max": 15, "sample": [{"name": "SyntheticPlayer"}],
            },
            "description": {"text": "Internal host status-peer"},
        }).encode()
        packet = b"\0" + varint(len(payload)) + payload
        self.wfile.write(varint(len(packet)) + packet)


if __name__ == "__main__":
    with ThreadingTCPServer(("0.0.0.0", 25565), StatusHandler) as server:
        server.serve_forever()
