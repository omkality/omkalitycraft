"""Exercise real 1.12.2 login encryption against an explicitly isolated loopback lab."""

import hashlib
import io
import secrets
import socket
import struct
import zlib
from contextlib import contextmanager
from dataclasses import dataclass

from cryptography.hazmat.decrepit.ciphers.modes import CFB8
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms

from launcher.session import Session
from omk.drasl import DraslClient, DraslError

MAX_PACKET = 2 * 1024**2


def varint(value: int) -> bytes:
    if not 0 <= value <= 0xFFFFFFFF:
        raise ValueError("Protocol integer out of bounds")
    result = bytearray()
    while True:
        byte, value = value & 127, value >> 7
        result.append(byte | (128 if value else 0))
        if not value:
            return bytes(result)


def number(read) -> int:
    result = 0
    for shift in range(0, 35, 7):
        byte = read(1)
        if len(byte) != 1:
            raise ValueError("Truncated protocol packet")
        result |= (byte[0] & 127) << shift
        if byte[0] < 128:
            return result
    raise ValueError("Invalid VarInt")


def text(value: str) -> bytes:
    data = value.encode()
    return varint(len(data)) + data


def field(read) -> bytes:
    length = number(read)
    if length > MAX_PACKET:
        raise ValueError("Protocol field too large")
    data = read(length)
    if len(data) != length:
        raise ValueError("Truncated protocol field")
    return data


@dataclass(frozen=True)
class ProbeResult:
    authenticated: bool
    join_accepted: bool
    player_uuid: str | None = None
    player_name: str | None = None


class Connection:
    def __init__(self, host: str, port: int):
        if host not in {"127.0.0.1", "::1"}:
            raise ValueError("Login probes are limited to the isolated loopback lab")
        self.socket = socket.create_connection((host, port), timeout=12)
        self.encryptor = self.decryptor = None
        self.compression = False
        self.compression_threshold = 256

    def read(self, length: int) -> bytes:
        data = bytearray()
        while len(data) < length:
            chunk = self.socket.recv(length - len(data))
            if not chunk:
                raise ValueError("Connection closed before login result")
            data.extend(self.decryptor.update(chunk) if self.decryptor else chunk)
        return bytes(data)

    def send(self, payload: bytes) -> None:
        if self.compression:
            payload = (
                varint(len(payload)) + zlib.compress(payload)
                if len(payload) >= self.compression_threshold
                else b"\0" + payload
            )
        packet = varint(len(payload)) + payload
        self.socket.sendall(self.encryptor.update(packet) if self.encryptor else packet)

    def receive(self) -> io.BytesIO:
        size = number(self.read)
        if size > MAX_PACKET:
            raise ValueError("Protocol packet too large")
        stream = io.BytesIO(self.read(size))
        if self.compression:
            expanded = number(stream.read)
            if expanded:
                if expanded > MAX_PACKET:
                    raise ValueError("Compressed packet too large")
                decoded = zlib.decompressobj().decompress(stream.read(), MAX_PACKET + 1)
                if len(decoded) != expanded:
                    raise ValueError("Invalid compressed packet")
                stream = io.BytesIO(decoded)
        return stream


@contextmanager
def login_connection(
    client: DraslClient,
    session: Session,
    host: str,
    port: int,
    *,
    nickname: str | None = None,
    access_token: str | None = None,
):
    connection = Connection(host, port)
    try:
        connection.send(
            varint(0)
            + varint(340)
            + text(host + "\0FML\0")
            + struct.pack(">H", port)
            + varint(2)
        )
        connection.send(varint(0) + text(nickname or session.player_name))
        request = connection.receive()
        if number(request.read) != 1:
            raise ValueError("Expected online-mode encryption challenge")
        server_id, public_der, challenge = (
            field(request.read),
            field(request.read),
            field(request.read),
        )
        secret = secrets.token_bytes(16)
        digest = hashlib.sha1(server_id + secret + public_der).digest()
        server_hash = format(int.from_bytes(digest, "big", signed=True), "x")
        joined = True
        try:
            client.request(
                "POST",
                "/session/minecraft/join",
                {
                    "accessToken": access_token or session.access_token,
                    "selectedProfile": session.player_uuid.replace("-", ""),
                    "serverId": server_hash,
                },
            )
        except DraslError as error:
            if error.status not in {400, 401, 403}:
                raise
            joined = False
        public = serialization.load_der_public_key(public_der)
        encrypted_secret = public.encrypt(secret, padding.PKCS1v15())
        encrypted_challenge = public.encrypt(challenge, padding.PKCS1v15())
        connection.send(
            varint(1)
            + varint(len(encrypted_secret))
            + encrypted_secret
            + varint(len(encrypted_challenge))
            + encrypted_challenge
        )
        cipher = Cipher(algorithms.AES(secret), CFB8(secret))
        connection.encryptor, connection.decryptor = (
            cipher.encryptor(),
            cipher.decryptor(),
        )
        yield connection, _result(connection, joined)
    finally:
        connection.socket.close()


def probe_login(client, session, host, port, **kwargs) -> ProbeResult:
    with login_connection(client, session, host, port, **kwargs) as (_, result):
        return result


def _result(connection: Connection, joined: bool) -> ProbeResult:
    for _ in range(5):
        response = connection.receive()
        packet = number(response.read)
        if packet == 0:
            return ProbeResult(False, joined)
        if packet == 3:
            connection.compression_threshold = number(response.read)
            connection.compression = True
        elif packet == 2:
            return ProbeResult(
                True,
                joined,
                field(response.read).decode(),
                field(response.read).decode(),
            )
        else:
            raise ValueError("Unexpected login response")
    raise ValueError("Login response limit exceeded")
