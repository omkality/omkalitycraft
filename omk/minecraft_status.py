"""Bounded Java server-list queries; expose counts, never sample names or addresses."""

import asyncio
import contextlib
import json
import struct
import threading
import time
from datetime import UTC, datetime


def _varint(value):
    result = bytearray()
    while True:
        byte = value & 127
        value >>= 7
        result.append(byte | (128 if value else 0))
        if not value:
            return bytes(result)


async def _read_varint(reader):
    value = 0
    for shift in range(0, 35, 7):
        byte = (await reader.readexactly(1))[0]
        value |= (byte & 127) << shift
        if byte < 128:
            return value
    raise ValueError("Oversized status integer")


async def query_players(host, port, *, timeout=2):
    async def exchange():
        reader, writer = await asyncio.open_connection(host, port)
        try:
            address = host.encode("utf-8")
            handshake = (
                b"\0"
                + _varint(340)
                + _varint(len(address))
                + address
                + struct.pack(">H", port)
                + b"\x01"
            )
            writer.write(_varint(len(handshake)) + handshake + b"\x01\0")
            await writer.drain()
            size = await _read_varint(reader)
            if not 1 <= size <= 65536:
                raise ValueError("Oversized status packet")
            data = await reader.readexactly(size)
            packet = asyncio.StreamReader()
            packet.feed_data(data)
            packet.feed_eof()
            if await _read_varint(packet) != 0:
                raise ValueError("Unexpected status response")
            length = await _read_varint(packet)
            if not 1 <= length <= 65536:
                raise ValueError("Oversized status string")
            value = json.loads((await packet.readexactly(length)).decode("utf-8"))
            if await packet.read(1):
                raise ValueError("Trailing status bytes")
            players = value["players"]
            online, maximum = players["online"], players["max"]
            if (
                type(online) is not int
                or type(maximum) is not int
                or not 0 <= online <= 100000
                or not 1 <= maximum <= 100000
            ):
                raise ValueError("Invalid player counts")
            return {"state": "online", "online": online, "max": maximum}
        finally:
            writer.close()
            with contextlib.suppress(Exception):
                await asyncio.wait_for(writer.wait_closed(), 0.2)

    return await asyncio.wait_for(exchange(), timeout)


class ServerStatusCache:
    def __init__(self, targets, *, ttl=15, timeout=2):
        self.targets = dict(targets)
        self.ttl = ttl
        self.timeout = timeout
        self.guard = threading.Lock()
        self.inflight = False
        self.expires = 0
        self.value = {"servers": {key: {"state": "checking"} for key in targets}}

    async def snapshot(self):
        with self.guard:
            if self.inflight or time.monotonic() < self.expires:
                return self.value
            self.inflight = True
        try:

            async def check(key, target):
                try:
                    result = await query_players(
                        target.host, target.port, timeout=self.timeout
                    )
                except (
                    OSError,
                    ValueError,
                    RecursionError,
                    KeyError,
                    TypeError,
                    asyncio.IncompleteReadError,
                    TimeoutError,
                ):
                    result = {"state": "offline"}
                return key, {**result, "checked_at": datetime.now(UTC).isoformat()}

            results = await asyncio.gather(
                *(check(key, target) for key, target in self.targets.items())
            )
            with self.guard:
                self.value = {"servers": dict(results)}
                self.expires = time.monotonic() + self.ttl
                return self.value
        finally:
            with self.guard:
                self.inflight = False
