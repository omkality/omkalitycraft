"""Test dependencies for candidate slots."""

import copy
from datetime import datetime, timedelta

import pytest

from omk.backups.cold_backup_worker import digest
from omk.deployment import (
    candidate_slot_spec as template,
    candidate_slots as slots,
)
from omk.owner import admin_reset_staging as staging
from omk.owner.admin import AdminError
from omk.owner.panels import owner_volumes
from tests.fixtures.unit.worlds.owner_reset_runtime import flow as runtime_flow


@pytest.fixture
def lab(tmp_path, monkeypatch):
    setup, resource, _ = runtime_flow.__wrapped__(tmp_path, monkeypatch)
    cfg, _, _window, _backup, state, _ = setup
    state["target"].update(
        owner="owned",
        label="omkality.owner",
        image="java@sha256:" + "b" * 64,
        release="release",
    )
    p = staging.read_record(cfg, resource)
    p["target"] = dict(state["target"])
    staging.save(cfg, p, "staged")
    staging.execute(cfg, resource, "runtime-plan", {})
    staging.execute(cfg, resource, "runtime-stage", {})
    p = staging.read_record(cfg, resource)
    spec = {
        "container": "candidate-game",
        "network": "private-net",
        "network_label": "omkality.net",
        "network_owner": "net-owner",
        "game_host_port": 25578,
        "rcon_host_port": 25579,
        "game_container_port": 25576,
        "rcon_container_port": 25575,
        "auth_url": "http://drasl:25585/authlib-injector",
        "metadata_file": "public.json",
    }
    state.update(
        candidate=None,
        network={"id": "network", "name": "private-net", "created": "stable"},
        commands=[],
        parent=p,
    )
    monkeypatch.setattr(template, "definition", lambda *a: dict(spec))
    monkeypatch.setattr(template, "metadata", lambda *a: {"public": "metadata"})
    monkeypatch.setattr(template, "network", lambda *a: dict(state["network"]))
    image = {
        "id": "sha256:" + "c" * 64,
        "env_sha256": digest([]),
        "entrypoint_sha256": digest(None),
    }
    monkeypatch.setattr(template, "image", lambda *a: dict(image))
    monkeypatch.setattr(
        slots, "raw_container", lambda name: copy.deepcopy(state["candidate"])
    )
    original_destination = owner_volumes.destination

    def destination(*args, **kwargs):
        if (
            state["candidate"] is not None
            and kwargs.get("allowed_container") != state["candidate"]["Id"]
        ):
            raise AdminError("Candidate is referenced by a container/helper")
        return original_destination(*args, **kwargs)

    monkeypatch.setattr(owner_volumes, "destination", destination)
    monkeypatch.setattr(slots, "runtime_proof", lambda *a: {"sealed": True})
    base = datetime.fromisoformat(
        p["checkpoint"]["finished"].replace("Z", "+00:00")
    ) + timedelta(seconds=30)

    def creation(config, r, parent):
        state["commands"].append("create")
        ports = {
            str(spec[k + "_container_port"]) + "/tcp": [
                {"HostIp": "127.0.0.1", "HostPort": str(spec[k + "_host_port"])}
            ]
            for k in ["game", "rcon"]
        }
        state["candidate"] = {
            "Id": "d" * 64,
            "Name": "/" + spec["container"],
            "Created": base.isoformat(),
            "Image": image["id"],
            "RestartCount": 0,
            "Config": {
                "Image": parent["target"]["image"],
                "Labels": {
                    slots.LABEL: r["operation"],
                    parent["target"]["label"]: parent["target"]["owner"],
                },
                "Cmd": template.command(spec, r["policy"], {"public": "metadata"}),
                "Env": [],
                "Entrypoint": None,
                "WorkingDir": "/srv",
                "User": "",
            },
            "HostConfig": {
                "NetworkMode": spec["network"],
                "PortBindings": ports,
                "Memory": r["policy"]["memory_mib"] * 1024**2,
                "NanoCpus": r["policy"]["cpus"] * 10**9,
                "PidsLimit": r["policy"]["pids"],
                "ReadonlyRootfs": True,
                "Privileged": False,
                "AutoRemove": False,
                "RestartPolicy": {"Name": "no"},
                "CapDrop": ["ALL"],
                "SecurityOpt": ["no-new-privileges:true"],
                "LogConfig": {
                    "Type": "local",
                    "Config": {"max-size": "10m", "max-file": "3"},
                },
            },
            "Mounts": [
                {
                    "Type": "volume",
                    "Name": parent["target"]["data_volume"],
                    "Destination": "/srv",
                    "RW": True,
                }
            ],
            "NetworkSettings": {
                "Ports": ports,
                "Networks": {spec["network"]: {"NetworkID": "network"}},
            },
            "State": {
                "Status": "created",
                "Running": False,
                "OOMKilled": False,
                "Paused": False,
                "Restarting": False,
                "StartedAt": "0001-01-01T00:00:00Z",
                "FinishedAt": "0001-01-01T00:00:00Z",
                "ExitCode": 0,
            },
        }

    monkeypatch.setattr(slots, "creation", creation)
    original_docker = slots.backups.docker

    def docker(*args, **kwargs):
        if args == ("start", "d" * 64):
            state["commands"].append("start")
            state["candidate"]["State"].update(
                Status="running",
                Running=True,
                StartedAt=(base + timedelta(seconds=1)).isoformat(),
            )
            return ""
        if args[0] == "logs" and args[-1] == "d" * 64:
            return "Done (1.2s)!\nStopping server\nSaving chunks for level\n"
        if args == ("rm", "d" * 64):
            state["commands"].append("rm")
            state["candidate"] = None
            return ""
        return original_docker(*args, **kwargs)

    monkeypatch.setattr(slots.backups, "docker", docker)

    def stop(*args):
        state["commands"].append("stop")
        state["candidate"]["State"].update(
            Status="exited",
            Running=False,
            FinishedAt=(base + timedelta(seconds=2)).isoformat(),
        )

    monkeypatch.setattr(slots, "console_stop", stop)
    monkeypatch.setattr(slots, "console", lambda *a: (object(), "x" * 32))
    monkeypatch.setattr(
        slots,
        "RecoveryConsole",
        lambda *a: type("Console", (), {"ready": lambda self: None})(),
    )
    ticks = iter(range(0, 100000, 20))
    monkeypatch.setattr(slots.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(slots.time, "sleep", lambda _: None)
    return cfg, resource, state, spec
