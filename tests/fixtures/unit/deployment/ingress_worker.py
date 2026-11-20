"""Test dependencies for ingress worker."""

import hashlib

import pytest

from omk.deployment import ingress_worker as worker


def responses(closed=True):
    state = (
        "1\n# be_name srv_name srv_fqdn srv_port srv_addr srv_admin_state srv_op_state\n"
        + f"minecraft source owned 25565 172.20.0.2 {5 if closed else 4} {0 if closed else 2}\n\n"
    )
    counters = (
        "# pxname,svname,scur,status\n"
        "game,FRONTEND,1,OPEN\n"
        + f"minecraft,source,1,{'MAINT' if closed else 'UP'}\n"
        + "minecraft,BACKEND,1,UP\n\n"
    )
    return state, counters


@pytest.fixture
def files(tmp_path, monkeypatch):
    cfg = tmp_path / "haproxy.cfg"
    cfg.write_bytes(b"reviewed template\n")
    props = tmp_path / "server.properties"
    props.write_bytes(
        b"server-port=25565\nrcon.port=25575\nonline-mode=true\nenable-rcon=true\nserver-ip=\n"
    )
    request = {
        "schema": 1,
        "action": "status",
        "config_sha256": hashlib.sha256(cfg.read_bytes()).hexdigest(),
        "backend": "owned",
        "port": 25565,
        "rcon_port": 25575,
        "source_required": False,
    }
    calls = []

    def exchange(command):
        calls.append(command)
        if command.startswith(("enable ", "disable ")):
            return "\n\n"
        return responses(request["action"] != "open")[command == "show stat"]

    monkeypatch.setattr(worker, "exchange", exchange)
    return request, cfg, props, calls
