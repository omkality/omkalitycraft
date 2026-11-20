"""Test dependencies for ingress config."""

import json

import pytest

from omk.backups.cold_backup_worker import digest
from omk.deployment import (
    ingress_config as deployment,
    ingress_template as template,
)
from tests.fixtures.unit.owner.operator_commands import config


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
