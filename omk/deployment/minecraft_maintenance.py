"""Serve Minecraft status and login messages on the private ingress socket."""

import asyncio
import json
import stat
from contextlib import suppress
from pathlib import Path

from omk.deployment.ingress_template import (
    MAINTENANCE_MESSAGES,
    MAINTENANCE_REASON,
    MAINTENANCE_SOCKET,
)
from omk.game.minecraft_status import _read_varint, _varint


async def _packet(reader, limit):
    size = await _read_varint(reader)
    if not 1 <= size <= limit:
        raise ValueError("Unexpected Minecraft packet size")
    return await reader.readexactly(size)


async def _handshake(reader):
    raw = asyncio.StreamReader()
    raw.feed_data(await _packet(reader, 1024))
    raw.feed_eof()
    if await _read_varint(raw) != 0:
        raise ValueError("Unexpected Minecraft handshake")
    await _read_varint(raw)
    address_size = await _read_varint(raw)
    if not 1 <= address_size <= 512:
        raise ValueError("Unexpected Minecraft address size")
    await raw.readexactly(address_size + 2)
    state = await _read_varint(raw)
    if state not in {1, 2} or await raw.read():
        raise ValueError("Unexpected Minecraft connection state")
    return state


def _message(path):
    try:
        with path.open("r", encoding="ascii") as stream:
            reason = stream.read(32).strip()
    except OSError, UnicodeError:
        reason = "offline"
    return MAINTENANCE_MESSAGES.get(reason, MAINTENANCE_MESSAGES["offline"])


async def _send(writer, packet_id, payload):
    data = _varint(packet_id) + payload
    writer.write(_varint(len(data)) + data)
    await writer.drain()


async def _respond(reader, writer, reason):
    state = await _handshake(reader)
    request = await _packet(reader, 512)
    if not request.startswith(b"\0") or (state == 1 and len(request) != 1):
        raise ValueError("Unexpected Minecraft request")
    description = {"text": _message(reason)}
    payload = (
        {
            "version": {"name": "Обслуживание", "protocol": 340},
            "players": {"online": 0, "max": 0},
            "description": description,
        }
        if state == 1
        else description
    )
    encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    await _send(writer, 0, _varint(len(encoded)) + encoded)
    if state == 1:
        ping = await _packet(reader, 9)
        if len(ping) == 9 and ping[0] == 1:
            await _send(writer, 1, ping[1:])


async def listen(path=Path(MAINTENANCE_SOCKET), reason=Path(MAINTENANCE_REASON)):
    """Start a local Minecraft protocol responder with bounded session lifetime."""
    try:
        if not stat.S_ISSOCK(path.lstat().st_mode):
            raise ValueError("Expected an owned maintenance socket")
        with suppress(ConnectionRefusedError):
            _, writer = await asyncio.open_unix_connection(path)
            writer.close()
            await writer.wait_closed()
            raise ValueError("Maintenance socket is already serving")
        path.unlink()
    except FileNotFoundError:
        pass

    async def client(reader, writer):
        try:
            await asyncio.wait_for(_respond(reader, writer, reason), 3)
        except OSError, ValueError, asyncio.IncompleteReadError:
            pass
        finally:
            writer.close()
            with suppress(OSError):
                await writer.wait_closed()

    return await asyncio.start_unix_server(client, path=path, backlog=32, limit=4096)


async def main():
    """Serve until the private responder container stops."""
    async with await listen() as server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
