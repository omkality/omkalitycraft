"""Loopback-only 1.12.2 protocol player for server-side tests, not a Minecraft client.

It does not execute mods, render, simulate physics or validate client compatibility.
The lab supplies an explicit mod list from a previously verified real client.
"""

import contextlib
import json
import socket
import struct
import threading
import time
from collections import deque

from omk.forge_probe import field, login_connection, number, text, varint


class LabPlayer:
    def __init__(self, client, session, port: int, mods: dict[str, str]):
        if (
            not mods
            or len(mods) > 1000
            or any(
                not isinstance(key, str)
                or not isinstance(value, str)
                or len(key) > 100
                or len(value) > 100
                for key, value in mods.items()
            )
        ):
            raise ValueError("Invalid explicit lab mod list")
        self.login = login_connection(client, session, "127.0.0.1", port)
        self.mods = dict(mods)
        self.messages = deque(maxlen=200)
        self.position = None
        self.error = None
        self._lock = threading.Lock()
        self._stopping = threading.Event()
        self.ready = threading.Event()
        self._handshake = False

    def __enter__(self):
        self.connection, result = self.login.__enter__()
        if not result.authenticated:
            self.login.__exit__(None, None, None)
            raise ValueError("Lab player login was refused")
        self.thread = threading.Thread(target=self._receive, daemon=True)
        self.thread.start()
        if not self.ready.wait(45):
            self.__exit__(None, None, None)
            raise RuntimeError("Lab player Forge handshake timed out")
        try:
            self.check()
        except RuntimeError:
            self.__exit__(None, None, None)
            raise
        return self

    def __exit__(self, *exc):
        self._stopping.set()
        with contextlib.suppress(OSError):
            self.connection.socket.shutdown(socket.SHUT_RDWR)
        self.login.__exit__(*exc)
        self.thread.join(timeout=3)

    def check(self):
        if self.error is not None:
            raise RuntimeError("Lab player disconnected: " + self.error)

    def send(self, packet: int, payload: bytes):
        with self._lock:
            self.connection.send(varint(packet) + payload)

    def custom(self, channel: str, payload: bytes):
        self.send(0x09, text(channel) + payload)

    def command(self, command: str):
        self.check()
        if (
            not command.startswith("/")
            or len(command) > 256
            or any(ord(c) < 32 for c in command)
        ):
            raise ValueError("Invalid lab command")
        self.send(0x02, text(command))

    def wait(self, predicate, timeout=12):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.check()
            if predicate():
                return
            self._stopping.wait(0.05)
        raise RuntimeError("Lab player assertion timed out")

    def dig(self, x: int, y: int, z: int):
        if not (
            -33554432 <= x < 33554432 and 0 <= y < 256 and -33554432 <= z < 33554432
        ):
            raise ValueError("Invalid lab block position")
        position = ((x & 0x3FFFFFF) << 38) | ((y & 0xFFF) << 26) | (z & 0x3FFFFFF)
        self.send(0x14, varint(0) + struct.pack(">Qb", position, 1))

    def _forge(self, payload: bytes):
        if not payload:
            raise ValueError("Empty Forge handshake")
        kind = payload[0]
        if kind == 0:
            self.custom("REGISTER", b"FML|HS\0FML\0FML|MP")
            self.custom("FML|HS", b"\x01\x02")
            self.custom(
                "FML|HS",
                b"\x02"
                + varint(len(self.mods))
                + b"".join(text(key) + text(value) for key, value in self.mods.items()),
            )
        elif kind == 2:
            self.custom("FML|HS", b"\xff\x02")
        elif kind == 3:
            if len(payload) < 2:
                raise ValueError("Truncated Forge registry")
            if not payload[1]:
                self.custom("FML|HS", b"\xff\x03")
        elif kind == 255:
            if len(payload) != 2 or payload[1] not in {2, 3}:
                raise ValueError("Unexpected Forge acknowledgement")
            self.custom("FML|HS", bytes((255, payload[1] + 2)))
            if payload[1] == 3:
                self._handshake = True
                self._ready()

    def _ready(self):
        if self._handshake and self.position is not None:
            self.ready.set()

    def _receive(self):
        try:
            while not self._stopping.is_set():
                packet = self.connection.receive()
                kind = number(packet.read)
                if kind == 0x18:
                    channel = field(packet.read).decode()
                    if channel == "FML|HS":
                        self._forge(packet.read())
                elif kind == 0x1F:
                    self.send(0x0B, packet.read())
                elif kind == 0x0F:
                    self.messages.append(json.loads(field(packet.read)))
                elif kind == 0x1A:
                    raise ValueError(
                        "Server kick: " + field(packet.read).decode()[:600]
                    )
                elif kind == 0x2F:
                    values = struct.unpack(">dddffB", packet.read(33))
                    previous = self.position or (0, 0, 0, 0, 0)
                    flags = values[-1]
                    self.position = tuple(
                        value + previous[index] if flags & (1 << index) else value
                        for index, value in enumerate(values[:5])
                    )
                    self.send(0x00, varint(number(packet.read)))
                    self.send(0x0E, struct.pack(">dddff?", *self.position, True))
                    self._ready()
        except Exception as error:
            if not self._stopping.is_set():
                self.error = str(error)[:700]
                self.ready.set()
