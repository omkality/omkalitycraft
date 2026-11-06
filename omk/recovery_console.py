"""Restricted loopback RCON adapter for verified Forge 1.12.2 recovery operations."""

import json
import re
import socket
import struct
import time
from dataclasses import dataclass
from uuid import UUID


class ConsoleError(RuntimeError):
    pass


@dataclass(frozen=True)
class ConsoleConfig:
    port: int
    credential_file: str
    host: str = "127.0.0.1"
    adapter: str = "omk-core112-rcon-v1"

    def __post_init__(self):
        if (
            self.host != "127.0.0.1"
            or self.adapter != "omk-core112-rcon-v1"
            or type(self.port) is not int
            or not 1024 <= self.port <= 65535
            or not isinstance(self.credential_file, str)
            or not self.credential_file
        ):
            raise ConsoleError("Invalid loopback recovery console configuration")


def _packet(number, kind, text):
    body = struct.pack("<ii", number, kind) + text.encode("utf-8") + b"\0\0"
    if len(body) > 4096:
        raise ConsoleError("Recovery console request too large")
    return struct.pack("<i", len(body)) + body


def _read(stream, size, deadline):
    value = bytearray()
    while len(value) < size:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ConsoleError("Recovery console response timed out")
        stream.settimeout(remaining)
        chunk = stream.recv(size - len(value))
        if not chunk:
            raise ConsoleError("Recovery console closed its connection")
        value.extend(chunk)
    return bytes(value)


def _receive(stream, deadline):
    size = struct.unpack("<i", _read(stream, 4, deadline))[0]
    if not 10 <= size <= 4096:
        raise ConsoleError("Invalid recovery console frame size")
    body = _read(stream, size, deadline)
    if body[-2:] != b"\0\0":
        raise ConsoleError("Invalid recovery console frame ending")
    number, kind = struct.unpack("<ii", body[:8])
    return number, kind, body[8:-2].decode("utf-8", errors="strict")


def command(config, password, text):
    # Only these fixed read/kick operations are exposed by this adapter.
    if text not in {"list uuids", "list omk-recovery version"} and not re.fullmatch(
        r"list omk-recovery (?:inspect|drain) [a-f0-9-]{36} [A-Za-z0-9_]{3,16}", text
    ):
        raise ConsoleError("Unsupported recovery console command")
    if (
        not isinstance(password, str)
        or not 16 <= len(password) <= 1024
        or "\0" in password
    ):
        raise ConsoleError("Invalid recovery console credential")
    deadline = time.monotonic() + 8
    with socket.create_connection((config.host, config.port), timeout=3) as stream:
        stream.sendall(_packet(1, 3, password))
        for _ in range(3):
            number, kind, _ = _receive(stream, deadline)
            if number == -1:
                raise ConsoleError("Recovery console authentication failed")
            if number == 1 and kind == 2:
                break
        else:
            raise ConsoleError("Invalid recovery console authentication response")
        # A second read-only command marks the end of a possibly split response.
        # Older Minecraft RCON reads one request at a time; do not pipeline requests
        # into the same TCP write. Wait for the first response before the delimiter.
        stream.sendall(_packet(2, 2, text))
        number, kind, body = _receive(stream, deadline)
        if number != 2 or kind != 0:
            raise ConsoleError("Invalid recovery console response identity")
        output = [body]
        stream.sendall(_packet(3, 2, "list uuids"))
        for _ in range(32):
            number, kind, body = _receive(stream, deadline)
            if number == 3 and kind == 0:
                return "".join(output)
            if number != 2 or kind != 0:
                raise ConsoleError("Invalid recovery console response identity")
            output.append(body)
        raise ConsoleError("Recovery console response exceeded its limit")


def online_players(text):
    match = re.fullmatch(
        r"There are (\d+)/(\d+) players online:\s*(.*)", text.strip(), re.S
    )
    if not match or not 0 <= int(match[1]) <= int(match[2]) <= 10000:
        raise ConsoleError("Unrecognized server player inventory")
    values = [] if not match[3] else match[3].split(", ")
    result = {}
    for value in values:
        player = re.fullmatch(r"([A-Za-z0-9_]{1,16}) \(([a-fA-F0-9-]{36})\)", value)
        if not player:
            raise ConsoleError("Invalid server player identity")
        identity = str(UUID(player[2]))
        if identity in result:
            raise ConsoleError("Duplicate server player identity")
        result[identity] = player[1]
    if len(result) != int(match[1]):
        raise ConsoleError("Incomplete server player inventory")
    return result


class RecoveryConsole:
    def __init__(self, config, password):
        self.config, self.password = config, password

    def online(self):
        return online_players(command(self.config, self.password, "list uuids"))

    def _recovery(self, suffix):
        output = command(self.config, self.password, "list omk-recovery " + suffix)
        if not output.startswith("OMK_RECOVERY_V1 "):
            raise ConsoleError("Server lacks the required account recovery adapter")
        try:
            value = json.loads(output[len("OMK_RECOVERY_V1 ") :])
        except ValueError:
            raise ConsoleError("Invalid account recovery adapter response") from None
        if (
            not isinstance(value, dict)
            or type(value.get("schema")) is not int
            or value.get("schema") != 1
        ):
            raise ConsoleError("Invalid account recovery adapter schema")
        return value

    def ready(self):
        if self._recovery("version") != {"schema": 1, "pending": True}:
            raise ConsoleError("Server adapter does not cover pending connections")

    def _counts(self, action, identity, name):
        identity = str(UUID(identity))
        value = self._recovery(f"{action} {identity} {name}")
        if set(value) != {"schema", "active", "pending"} or any(
            type(value[k]) is not int or not 0 <= value[k] <= 10000
            for k in ("active", "pending")
        ):
            raise ConsoleError("Invalid account connection counts")
        return value["active"] + value["pending"]

    def remaining(self, players):
        return sum(
            self._counts("inspect", identity, name)
            for identity, name in players.items()
        )

    def disconnect(self, players):
        for identity, name in players.items():
            self._counts("drain", identity, name)
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if not self.remaining(players):
                return
            time.sleep(0.2)
        raise ConsoleError("Account still has an active or pending game connection")
