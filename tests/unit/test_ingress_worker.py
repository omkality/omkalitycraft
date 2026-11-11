import hashlib

import pytest

from omk import (
    ingress_template as template,
    ingress_worker as worker,
)


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


@pytest.mark.parametrize("action", ["status", "open", "close"])
def test_fixed_commands_and_property_proof(files, action):
    request, cfg, props, calls = files
    request.update(action=action, source_required=action == "open")
    value = worker.execute(request, cfg, props.parent)
    assert value["closed"] is (action != "open")
    assert value["backend_up"] is (action == "open")
    assert value["sessions"] == 1
    assert value["properties_sha256"] == (
        hashlib.sha256(props.read_bytes()).hexdigest() if action == "open" else None
    )
    expected = ["show servers state", "show stat"]
    if action != "status":
        expected.insert(
            0,
            ("enable" if action == "open" else "disable") + " server minecraft/source",
        )
    assert calls == expected


@pytest.mark.parametrize(
    "change",
    [
        "command",
        "backend",
        "port",
        "unproved",
        "offline",
        "duplicate",
        "config",
        "rcon",
    ],
)
def test_invalid_binding_refuses_before_any_socket_write(files, change):
    request, cfg, props, calls = files
    request.update(action="open", source_required=True)
    if change == "command":
        request["action"] = "shutdown sessions server minecraft/source"
    elif change == "backend":
        request["backend"] = "owned\nenable server attacker/source"
    elif change == "port":
        request["port"] = True
    elif change == "unproved":
        request["source_required"] = False
    elif change == "offline":
        props.write_bytes(
            props.read_bytes().replace(b"online-mode=true", b"online-mode=false")
        )
    elif change == "duplicate":
        props.write_bytes(props.read_bytes() + b"server-port=25565\n")
    elif change == "config":
        cfg.write_bytes(b"changed\n")
    else:
        request["port"] = request["rcon_port"]
    with pytest.raises(ValueError):
        worker.execute(request, cfg, props.parent)
    assert calls == []


@pytest.mark.parametrize("change", ["route", "extra", "version", "count", "ipv6"])
def test_ambiguous_runtime_inventory_is_refused(change):
    state, counters = responses()
    if change == "route":
        state = state.replace("source owned", "source other")
    elif change == "extra":
        counters += "minecraft,other,0,UP\n"
    elif change == "version":
        state = state.replace("1\n", "2\n", 1)
    elif change == "count":
        counters = counters.replace("FRONTEND,1", "FRONTEND,-1")
    else:
        state = state.replace("172.20.0.2", "::1")
    with pytest.raises(ValueError):
        worker.parse(state, counters, "owned", 25565)


def test_regular_file_is_not_an_admin_socket(tmp_path):
    path = tmp_path / "fake.sock"
    path.write_text("not a socket")
    with pytest.raises(ValueError, match="socket"):
        worker.exchange("show stat", path)


@pytest.mark.parametrize("value", ["0", "2.1", "-1", "nan", "0.5001", "1;id", "１"])
def test_cpu_override_is_bounded_decimal(value):
    with pytest.raises(ValueError, match="CPUS"):
        template.settings({"OMK_INGRESS_CPUS": value})


def test_template_always_starts_closed_and_honors_settings():
    policy = template.settings(
        {"OMK_INGRESS_CPUS": "0.75", "OMK_INGRESS_MAX_CONNECTIONS": "64"}
    )
    text = template.render(
        {"container_port": 25590, "backend_port": 25565}, policy, "owned"
    )
    assert policy["cpu_millis"] == 750 and "maxconn 64" in text
    assert "disabled\n" in text and "bind 0.0.0.0:25590" in text
    assert "experimental" not in text and "accept-proxy" not in text
    assert template.profile()["image"].endswith(
        "@sha256:1c3568e520453cc8ba98c39501febcf450429c80e6cc27ecad779961d76e597c"
    )
