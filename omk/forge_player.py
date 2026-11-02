"""Loopback-only 1.12.2 protocol player for server-side tests, not a Minecraft client.

It does not execute mods, render, simulate physics or validate client compatibility.
The lab supplies an explicit mod list from a previously verified real client.
"""

import contextlib
import io
import json
import math
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
        self.open_windows = deque(maxlen=20)
        self.closed_windows = deque(maxlen=20)
        self.transactions = deque(maxlen=20)
        self.position = None
        self.health = None
        self.entity_id = None
        self.dimension = None
        self.error = None
        self._lock = threading.Lock()
        self._stopping = threading.Event()
        self.ready = threading.Event()
        self._handshake = False
        self._last_chat = 0.0

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
        self._chat_packet(command)

    def chat(self, message: str):
        self.check()
        if (
            not message
            or message.startswith("/")
            or len(message) > 256
            or any(ord(c) < 32 for c in message)
        ):
            raise ValueError("Invalid lab chat")
        self._chat_packet(message)

    def _chat_packet(self, message):
        # Vanilla counts commands as chat spam too. Keep the test actor below
        # that limit rather than disabling protection on the lab server.
        delay = 1.1 - (time.monotonic() - self._last_chat)
        if delay > 0:
            self._stopping.wait(delay)
        self.check()
        self.send(0x02, text(message))
        self._last_chat = time.monotonic()

    def move(self, x: float, y: float, z: float):
        self.check()
        if not all(math.isfinite(v) and abs(v) < 30000000 for v in (x, y, z)):
            raise ValueError("Invalid lab movement")
        # This protocol actor does not simulate physics. Tests independently echo
        # the accepted server coordinates before asserting movement behavior.
        self.send(0x0D, struct.pack(">ddd?", x, y, z, True))

    def wait(self, predicate, timeout=12):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.check()
            if predicate():
                return
            self._stopping.wait(0.05)
        raise RuntimeError("Lab player assertion timed out")

    def dig(self, x: int, y: int, z: int):
        self.send(0x14, varint(0) + self._block_position(x, y, z) + b"\x01")

    def respawn(self):
        self.check()
        if self.health is None or self.health > 0:
            raise ValueError("Lab respawn requires a confirmed dead actor")
        self.send(0x03, varint(0))

    def sneak(self, enabled):
        self.check()
        if self.entity_id is None or type(enabled) is not bool:
            raise ValueError("Lab sneak requires a joined actor and boolean state")
        self.send(
            0x15, varint(self.entity_id) + varint(0 if enabled else 1) + varint(0)
        )

    @staticmethod
    def _block_position(x, y, z):
        if not (
            all(type(v) is int for v in (x, y, z))
            and -33554432 <= x < 33554432
            and 0 <= y < 256
            and -33554432 <= z < 33554432
        ):
            raise ValueError("Invalid lab block position")
        position = ((x & 0x3FFFFFF) << 38) | ((y & 0xFFF) << 26) | (z & 0x3FFFFFF)
        return struct.pack(">Q", position)

    def select_hotbar(self, slot=0):
        self.check()
        if type(slot) is not int or not 0 <= slot <= 8:
            raise ValueError("Invalid lab hotbar slot")
        self.send(0x1A, struct.pack(">h", slot))

    def use_block(self, x: int, y: int, z: int):
        self.check()
        self.send(
            0x1F,
            self._block_position(x, y, z)
            + varint(1)
            + varint(0)
            + struct.pack(">fff", 0.5, 1.0, 0.5),
        )

    def close_window(self, window_id):
        self.check()
        if type(window_id) is not int or not 1 <= window_id <= 255:
            raise ValueError("Invalid lab window")
        self.send(0x08, struct.pack(">B", window_id))

    def shift_click(self, window_id, slot, action, *, item_id, count, damage=0):
        """Shift-click an explicit, NBT-free fixture stack; no client inventory model."""
        self.check()
        values = (window_id, slot, action, item_id, count, damage)
        if not (
            all(type(v) is int for v in values)
            and 1 <= window_id <= 255
            and 0 <= slot <= 1023
            and 1 <= action <= 32767
            and 0 <= item_id <= 32767
            and 1 <= count <= 64
            and 0 <= damage <= 32767
        ):
            raise ValueError("Invalid lab inventory click")
        self.send(
            0x07,
            struct.pack(">Bhbhb", window_id, slot, 0, action, 1)
            + struct.pack(">hbh", item_id, count, damage)
            + b"\0",  # TAG_End: this fixture stack has no NBT.
        )

    def _runtime(self, payload):
        # Forge's FMLRuntimeCodec discriminator 1 is OpenGui. Observe its server
        # window ID without loading the mod or pretending to render its GUI.
        packet = io.BytesIO(payload)
        if packet.read(1) != b"\x01":
            return
        window_id = struct.unpack(">i", packet.read(4))[0]
        mod = field(packet.read).decode()
        gui, x, y, z = struct.unpack(">iiii", packet.read(16))
        remaining = len(payload) - packet.tell()
        if not 1 <= window_id <= 255 or len(mod) > 100 or remaining:
            raise ValueError(
                f"Invalid Forge lab window (id={window_id}, mod={mod[:100]}, "
                f"trailing={remaining})"
            )
        self.open_windows.append(
            {
                "id": window_id,
                "type": "forge:" + mod,
                "gui": gui,
                "position": (x, y, z),
                "slots": None,
            }
        )

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

    def _custom_packet(self, packet):
        channel = field(packet.read).decode()
        if channel == "FML|HS":
            self._forge(packet.read())
        elif channel == "FML":
            self._runtime(packet.read())

    def _container_packet(self, kind, packet):
        if kind == 0x11:
            window_id, action, accepted = struct.unpack(">Bh?", packet.read(4))
            self.transactions.append((window_id, action, accepted))
            if not accepted:
                self.send(0x05, struct.pack(">Bh?", window_id, action, True))
        elif kind == 0x12:
            self.closed_windows.append(packet.read(1)[0])
        else:
            window_id = packet.read(1)[0]
            container = field(packet.read).decode()
            title = json.loads(field(packet.read))
            slots = packet.read(1)[0]
            self.open_windows.append(
                {"id": window_id, "type": container, "title": title, "slots": slots}
            )

    def _receive(self):
        try:
            while not self._stopping.is_set():
                packet = self.connection.receive()
                kind = number(packet.read)
                if kind == 0x18:
                    self._custom_packet(packet)
                elif kind == 0x1F:
                    self.send(0x0B, packet.read())
                elif kind == 0x0F:
                    self.messages.append(json.loads(field(packet.read)))
                elif kind == 0x1A:
                    raise ValueError(
                        "Server kick: " + field(packet.read).decode()[:600]
                    )
                elif kind == 0x41:
                    self.health = struct.unpack(">f", packet.read(4))[0]
                elif kind == 0x23:
                    self.entity_id = struct.unpack(">i", packet.read(4))[0]
                    packet.read(1)  # Game mode.
                    self.dimension = struct.unpack(">i", packet.read(4))[0]
                elif kind == 0x35:
                    self.dimension = struct.unpack(">i", packet.read(4))[0]
                elif kind in {0x11, 0x12, 0x13}:
                    self._container_packet(kind, packet)
                elif kind == 0x2F:
                    values = struct.unpack(">dddffB", packet.read(33))
                    previous = self.position or (0, 0, 0, 0, 0)
                    flags = values[-1]
                    position = tuple(
                        value + previous[index] if flags & (1 << index) else value
                        for index, value in enumerate(values[:5])
                    )
                    self.send(0x00, varint(number(packet.read)))
                    self.send(0x0E, struct.pack(">dddff?", *position, True))
                    # Test actions may proceed as soon as position is visible;
                    # publish it only after the teleport ACK is on the same TCP stream.
                    self.position = position
                    self._ready()
        except Exception as error:
            if not self._stopping.is_set():
                self.error = str(error)[:700]
                self.ready.set()
