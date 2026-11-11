"""Bounded local HAProxy control; no Docker socket, network, or generic commands."""

import csv
import hashlib
import io
import ipaddress
import json
import re
import socket
import stat
import sys
from pathlib import Path

from omk.ingress_template import CONFIG, SOCKET
from omk.linux_restore_policy import _read


def exchange(command, path=Path(SOCKET)):
    if not stat.S_ISSOCK(path.lstat().st_mode):
        raise ValueError("Ingress admin socket is absent or linked")
    with socket.socket(socket.AF_UNIX) as stream:
        stream.settimeout(3)
        stream.connect(str(path))
        stream.sendall((command + "\n").encode())
        stream.shutdown(socket.SHUT_WR)
        output = bytearray()
        while chunk := stream.recv(4096):
            output.extend(chunk)
            if len(output) > 65536:
                raise ValueError("Ingress response exceeds bound")
    return output.decode("ascii")


def parse(state, counters, backend, port):
    lines = [line for line in state.splitlines() if line]
    if len(lines) != 3 or lines[0] != "1" or not lines[1].startswith("# "):
        raise ValueError("Unexpected ingress server-state schema")
    keys, values = lines[1][2:].split(), lines[2].split()
    if len(keys) != len(values) or len(set(keys)) != len(keys):
        raise ValueError("Ambiguous ingress server state")
    row = dict(zip(keys, values, strict=True))
    if (
        row.get("be_name") != "minecraft"
        or row.get("srv_name") != "source"
        or row.get("srv_fqdn") != backend
        or row.get("srv_port") != str(port)
    ):
        raise ValueError("Ingress route differs from the configured source")
    address = row["srv_addr"]
    if address == "-":
        address = None
    elif ipaddress.ip_address(address).version != 4:
        raise ValueError("Unexpected backend address family")
    data = list(csv.DictReader(io.StringIO(counters.removeprefix("# "))))
    expected = {("game", "FRONTEND"), ("minecraft", "source"), ("minecraft", "BACKEND")}
    actual = {(r.get("pxname"), r.get("svname")): r for r in data}
    if len(data) != 3 or set(actual) != expected:
        raise ValueError("Unexpected ingress statistics inventory")
    count = actual["game", "FRONTEND"]["scur"]
    if not count.isascii() or not count.isdecimal() or len(count) > 8:
        raise ValueError("Invalid ingress session counter")
    closed = bool(int(row["srv_admin_state"]) & 1)
    return {
        "closed": closed,
        "sessions": int(count),
        "address": address,
        "backend_up": not closed
        and row["srv_op_state"] == "2"
        and actual["minecraft", "source"]["status"] == "UP",
    }


def source_proof(request, source):
    props = _read(source, "server.properties", limit=65536)
    for key, wanted in {
        "server-port": str(request["port"]),
        "rcon.port": str(request["rcon_port"]),
        "online-mode": "true",
        "enable-rcon": "true",
        "server-ip": "",
    }.items():
        if re.findall(
            rb"^" + re.escape(key.encode()) + rb"=([^\r\n]*)\r?$", props, re.M
        ) != [wanted.encode()]:
            raise ValueError("Source properties do not match the private ingress route")
    return hashlib.sha256(props).hexdigest()


def execute(request, config=Path(CONFIG), source=Path("/server")):
    if not isinstance(request, dict) or set(request) != {
        "schema",
        "action",
        "config_sha256",
        "backend",
        "port",
        "rcon_port",
        "source_required",
    }:
        raise ValueError("Invalid ingress worker request")
    if (
        type(request["schema"]) is not int
        or request["schema"] != 1
        or request["action"] not in {"status", "open", "close"}
        or type(request["source_required"]) is not bool
        or (request["action"] == "open" and not request["source_required"])
        or not isinstance(request["backend"], str)
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", request["backend"])
        or any(
            type(request[k]) is not int or not 1024 <= request[k] <= 65535
            for k in ("port", "rcon_port")
        )
        or request["port"] == request["rcon_port"]
    ):
        raise ValueError("Unsupported ingress action or binding")
    raw = _read(config.parent, config.name, limit=65536)
    if hashlib.sha256(raw).hexdigest() != request["config_sha256"]:
        raise ValueError("Ingress template bytes changed")
    proof = source_proof(request, source) if request["source_required"] else None
    if request["action"] != "status":
        verb = "enable" if request["action"] == "open" else "disable"
        reply = exchange(verb + " server minecraft/source")
        if reply.strip():
            raise ValueError("Ingress command was not acknowledged")
    result = parse(
        exchange("show servers state"),
        exchange("show stat"),
        request["backend"],
        request["port"],
    )
    return {
        **result,
        "config_sha256": request["config_sha256"],
        "properties_sha256": proof,
    }


if __name__ == "__main__":
    try:
        raw = sys.stdin.buffer.read(65537)
        if len(raw) > 65536:
            raise ValueError("Oversized ingress request")
        print(json.dumps({"ok": True, "result": execute(json.loads(raw))}))
    except Exception as error:
        print(json.dumps({"ok": False, "error_type": type(error).__name__}))
        raise SystemExit(1) from None
