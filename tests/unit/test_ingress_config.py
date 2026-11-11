import copy
import json

import pytest

from omk import (
    ingress_config as deployment,
    ingress_template as template,
)
from omk.admin import AdminError
from omk.cold_backup_worker import digest
from tests.unit.test_operator_commands import config


@pytest.fixture
def layout(tmp_path):
    spec = {
        "container": "proxy",
        "owner": "owner",
        "network": "owned-net",
        "network_label": "omkality.owner",
        "network_owner": "net-owner",
        "control_volume": "control",
        "control_owner": "ctl-owner",
        "config_dir": "ingress-config/dj2",
        "host_port": 25580,
        "container_port": 25565,
        "backend_port": 25576,
    }
    policy = template.settings({})
    ports = {"25565/tcp": [{"HostIp": "127.0.0.1", "HostPort": "25580"}]}
    image = {
        "id": "image-id",
        "env_sha256": digest([]),
        "entrypoint_sha256": digest(["docker-entrypoint.sh"]),
    }
    data = {
        "Name": "/proxy",
        "Id": "proxy-id",
        "Created": "created",
        "Image": "image-id",
        "RestartCount": 0,
        "Config": {
            "Image": template.profile()["image"],
            "Labels": {template.LABEL: "owner"},
            "Cmd": template.profile()["command"],
            "Env": [],
            "Entrypoint": ["docker-entrypoint.sh"],
            "User": "0:0",
        },
        "HostConfig": {
            "Memory": 64 * 1024**2,
            "NanoCpus": 500000000,
            "PidsLimit": 64,
            "ReadonlyRootfs": True,
            "Privileged": False,
            "AutoRemove": False,
            "RestartPolicy": {"Name": "no"},
            "CapDrop": ["ALL"],
            "SecurityOpt": ["no-new-privileges:true"],
            "NetworkMode": "owned-net",
            "PortBindings": ports,
            "LogConfig": {
                "Type": "local",
                "Config": {"max-size": "10m", "max-file": "3"},
            },
        },
        "Mounts": [
            {
                "Type": "bind",
                "Source": str(tmp_path),
                "Destination": "/usr/local/etc/haproxy",
                "RW": False,
            },
            {
                "Type": "volume",
                "Name": "control",
                "Destination": "/run/omk-ingress",
                "RW": True,
            },
        ],
        "NetworkSettings": {
            "Networks": {"owned-net": {"NetworkID": "net-id"}},
            "Ports": ports,
        },
        "State": {
            "Status": "running",
            "Running": True,
            "OOMKilled": False,
            "Paused": False,
            "Restarting": False,
            "StartedAt": "boot",
        },
    }
    return (
        data,
        spec,
        {"id": "source-id"},
        policy,
        image,
        {"id": "net-id"},
        {"name": "control"},
        tmp_path,
    )


def test_exact_owned_deployment_is_fingerprinted(layout):
    proof = deployment.proxy_snapshot(*layout)
    assert proof["id"] == "proxy-id" and proof["source_id"] == "source-id"
    assert proof["started"] == "boot"


def test_compose_serialized_exact_readonly_bind_is_accepted(layout):
    args = copy.deepcopy(layout)
    args[0]["HostConfig"]["Binds"] = [str(args[-1]) + ":/usr/local/etc/haproxy:ro"]
    assert deployment.proxy_snapshot(*args)["id"] == "proxy-id"


def test_foreign_legacy_bind_is_refused(layout):
    args = copy.deepcopy(layout)
    args[0]["HostConfig"]["Binds"] = ["/foreign:/usr/local/etc/haproxy:ro"]
    with pytest.raises(AdminError, match="deployment"):
        deployment.proxy_snapshot(*args)


@pytest.mark.parametrize(
    "path,value",
    [
        (("Config", "Image"), "haproxy:latest"),
        (("Config", "Env"), ["EXTRA=value"]),
        (("Config", "Cmd"), ["haproxy", "-d"]),
        (("Config", "Labels", template.LABEL), "someone-else"),
        (("HostConfig", "PortBindings", "25565/tcp", 0, "HostIp"), "0.0.0.0"),
        (("NetworkSettings", "Networks", "foreign"), {"NetworkID": "foreign"}),
        (("HostConfig", "ReadonlyRootfs"), False),
        (("Mounts", 0, "RW"), True),
        (("HostConfig", "Memory"), 0),
        (("HostConfig", "NanoCpus"), 0),
        (("HostConfig", "Privileged"), True),
        (("HostConfig", "CapAdd"), ["SYS_ADMIN"]),
        (("RestartCount",), 1),
        (("State", "OOMKilled"), True),
    ],
)
def test_modified_deployment_is_refused(layout, path, value):
    args = copy.deepcopy(layout)
    target = args[0]
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(AdminError, match="deployment"):
        deployment.proxy_snapshot(*args)


def test_extra_mount_is_refused(layout):
    args = copy.deepcopy(layout)
    args[0]["Mounts"].append(
        {"Type": "bind", "Source": "/var/run/docker.sock", "Destination": "/docker"}
    )
    with pytest.raises(AdminError, match="deployment"):
        deployment.proxy_snapshot(*args)


@pytest.fixture
def definitions(tmp_path, monkeypatch, layout):
    cfg, _ = config(tmp_path)
    spec = layout[1]
    monkeypatch.setattr(deployment.owner_volumes, "document", lambda *a: {"dj2": {}})
    monkeypatch.setattr(
        deployment.backups,
        "target_for",
        lambda *a: {
            "container": "source",
            "data_volume": "data",
            "store_volume": "store",
        },
    )

    def write(value):
        p = cfg.private / "ingress.toml"
        p.write_text(
            "schema=1\n[servers.dj2]\n"
            + "\n".join(k + "=" + json.dumps(v) for k, v in value.items())
        )
        p.chmod(0o600)

    write(spec)
    return cfg, spec, write


@pytest.mark.parametrize(
    "key,value",
    [
        ("control_volume", "data"),
        ("control_volume", "store"),
        ("container", "source"),
        ("network", "bridge"),
        ("host_port", 1),
        ("backend_port", True),
        ("config_dir", "../escape"),
        ("container", "proxy\nmalicious"),
        ("unknown", "extra"),
    ],
)
def test_aliases_and_ambiguous_definitions_are_refused(definitions, key, value):
    cfg, spec, write = definitions
    write({**spec, key: value})
    with pytest.raises(AdminError):
        deployment.definition(cfg, "dj2")


def test_prepare_is_repeatable_without_overwriting_changed_config(definitions):
    cfg, spec, _ = definitions
    first = deployment.preparation(cfg, "dj2", {})
    path = cfg.private / spec["config_dir"] / "haproxy.cfg"
    assert first == deployment.preparation(cfg, "dj2", {})
    assert first["closed_on_boot"] and not first["deployed"]
    assert b"disabled\n" in path.read_bytes() and b"\r" not in path.read_bytes()
    path.write_bytes(b"do not overwrite")
    with pytest.raises(AdminError, match="never overwrite"):
        deployment.preparation(cfg, "dj2", {})
    assert path.read_bytes() == b"do not overwrite"
