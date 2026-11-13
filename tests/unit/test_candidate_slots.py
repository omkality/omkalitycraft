import copy
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from omk import (
    admin_reset_staging as staging,
    candidate_slot_spec as template,
    candidate_slots as slots,
    owner_volumes,
)
from omk.admin import AdminError
from omk.cold_backup_worker import digest
from tests.unit.test_owner_reset_runtime import flow as runtime_flow

REAL_CREATION = slots.creation


def test_creation_uses_the_frozen_docker_log_policy(lab, monkeypatch):
    cfg, resource, state, _ = lab
    environment = {"OMK_SLOT_DOCKER_LOG_MIB": "1", "OMK_SLOT_DOCKER_LOG_FILES": "2"}
    operation = slots.plan(cfg, resource, environment)["operation"]
    record = slots.read(cfg, operation)
    calls = []
    monkeypatch.setattr(
        slots.backups, "docker", lambda *args, **kwargs: calls.append(args)
    )
    REAL_CREATION(cfg, record, state["parent"])
    assert "max-size=1m" in calls[0] and "max-file=2" in calls[0]
    assert "max-size=10m" not in calls[0]


def test_legacy_plan_with_implicit_default_logs_can_still_be_created(lab):
    cfg, resource, state, _ = lab
    operation = slots.plan(cfg, resource, {})["operation"]
    record = slots.read(cfg, operation)
    record["policy"].pop("docker_log_mib")
    record["policy"].pop("docker_log_files")
    slots.save(cfg, record, "planned")
    result = slots.execute(cfg, operation, "create", {})
    assert result["stage"] == "created" and state["commands"] == ["create"]
    assert "docker_log_mib" not in slots.read(cfg, operation)["policy"]


def test_legacy_plan_cannot_adopt_a_new_docker_log_override(lab):
    cfg, resource, state, _ = lab
    operation = slots.plan(cfg, resource, {})["operation"]
    record = slots.read(cfg, operation)
    record["policy"].pop("docker_log_mib")
    record["policy"].pop("docker_log_files")
    slots.save(cfg, record, "planned")
    with pytest.raises(AdminError, match="changed"):
        slots.execute(cfg, operation, "create", {"OMK_SLOT_DOCKER_LOG_MIB": "1"})
    assert state["commands"] == [] and slots.read(cfg, operation)["stage"] == "planned"


def test_snapshot_requires_the_recorded_log_driver_configuration(lab):
    cfg, resource, state, _ = lab
    environment = {"OMK_SLOT_DOCKER_LOG_MIB": "1", "OMK_SLOT_DOCKER_LOG_FILES": "2"}
    operation = slots.plan(cfg, resource, environment)["operation"]
    record = slots.read(cfg, operation)
    slots.creation(cfg, record, state["parent"])
    # The fixture creates the old 10m/3 container; a new 1m/2 plan must reject it.
    with pytest.raises(AdminError):
        slots.snapshot(record, state["parent"])
    state["candidate"]["HostConfig"]["LogConfig"] = {
        "Type": "local",
        "Config": {"max-size": "1m", "max-file": "2"},
    }
    assert slots.snapshot(record, state["parent"])["status"] == "created"
    state["candidate"]["HostConfig"]["LogConfig"]["Type"] = "json-file"
    with pytest.raises(AdminError):
        slots.snapshot(record, state["parent"])


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
            str(spec[k + "_container_port"])
            + "/tcp": [{"HostIp": "127.0.0.1", "HostPort": str(spec[k + "_host_port"])}]
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


def planned(lab):
    return slots.plan(lab[0], lab[1], {})["operation"]


def test_complete_owned_loopback_lifecycle_retains_world_and_log(lab):
    cfg, resource, state, _ = lab
    s = planned(lab)
    with pytest.raises(AdminError, match="slot is pending"):
        staging.execute(cfg, resource, "abandon")
    assert slots.execute(cfg, s, "create", {})["stage"] == "created"
    result = slots.execute(cfg, s, "start", {})
    assert (
        result["health_confirmed"]
        and result["loopback_only"]
        and not result["ready_for_players"]
        and not result["promoted"]
    )
    with pytest.raises(AdminError):
        slots.execute(cfg, s, "start", {})
    with pytest.raises(AdminError):
        slots.execute(cfg, s, "release")
    assert slots.execute(cfg, s, "stop")["stage"] == "stopped"
    assert slots.execute(cfg, s, "release")["stage"] == "released"
    assert slots.execute(cfg, s, "release")["stage"] == "released"
    assert state["commands"] == ["create", "start", "stop", "rm"]
    assert slots.log_path(cfg, slots.read(cfg, s)).exists()
    assert (
        state["runtime_complete"]
        and staging.execute(cfg, resource, "abandon")["stage"] == "abandoned"
    )


@pytest.mark.parametrize("action", ["create", "start", "stop", "release"])
def test_completed_docker_action_with_lost_reply_reconciles_without_repeat(
    lab, monkeypatch, action
):
    cfg, _, state, _ = lab
    s = planned(lab)
    if action != "create":
        slots.execute(cfg, s, "create", {})
    if action in ["stop", "release"]:
        slots.execute(cfg, s, "start", {})
    if action == "release":
        slots.execute(cfg, s, "stop")
    if action in ["create", "stop"]:
        name = "creation" if action == "create" else "console_stop"
        real = getattr(slots, name)

        def lost(*args, **kwargs):
            real(*args, **kwargs)
            raise KeyboardInterrupt("lost")

        monkeypatch.setattr(slots, name, lost)
    else:
        real = slots.backups.docker

        def lost(*args, **kwargs):
            result = real(*args, **kwargs)
            if args[0] == ("start" if action == "start" else "rm"):
                raise OSError("lost reply")
            return result

        monkeypatch.setattr(slots.backups, "docker", lost)
    with pytest.raises((KeyboardInterrupt, OSError)):
        slots.execute(cfg, s, action, {})
    commands = list(state["commands"])
    expected = {
        "create": "created",
        "start": "running",
        "stop": "stopped",
        "release": "released",
    }[action]
    assert slots.execute(cfg, s, "reconcile")["stage"] == expected
    assert state["commands"] == commands


def test_created_candidate_can_be_released_without_any_start(lab):
    cfg, _, state, _ = lab
    s = planned(lab)
    slots.execute(cfg, s, "create", {})
    assert slots.execute(cfg, s, "release")["stage"] == "released"
    assert state["commands"] == ["create", "rm"]


def test_planned_slot_can_be_cancelled_without_container(lab):
    cfg, resource, state, _ = lab
    s = planned(lab)
    assert slots.execute(cfg, s, "release")["stage"] == "released"
    assert (
        state["commands"] == []
        and staging.execute(cfg, resource, "abandon")["stage"] == "abandoned"
    )


@pytest.mark.parametrize(
    "action,stage", [("start", "planned"), ("release", "create-requested")]
)
def test_invalid_transition_without_container_refuses_without_key_error(
    lab, action, stage
):
    cfg, _, state, _ = lab
    s = planned(lab)
    r = slots.read(cfg, s)
    slots.save(cfg, r, stage)
    with pytest.raises(AdminError):
        slots.execute(cfg, s, action, {})
    assert state["commands"] == []


@pytest.mark.parametrize("key,value", [("OOMKilled", True), ("ExitCode", 1)])
def test_bad_stop_is_never_removed(lab, key, value):
    cfg, _, state, _ = lab
    s = planned(lab)
    slots.execute(cfg, s, "create", {})
    slots.execute(cfg, s, "start", {})
    slots.execute(cfg, s, "stop")
    state["candidate"]["State"][key] = value
    if key == "ExitCode":
        # The real cold checkpoint rejects this; keep the fixture contract exact.
        original = slots.backups.checkpoint

        def checkpoint(target):
            if target["container"] == "d" * 64:
                raise AdminError("Not a clean stop")
            return original(target)

        with (
            patch.object(slots.backups, "checkpoint", checkpoint),
            pytest.raises(AdminError),
        ):
            slots.execute(cfg, s, "release")
    else:
        with pytest.raises(AdminError):
            slots.execute(cfg, s, "release")
    assert "rm" not in state["commands"]


@pytest.mark.parametrize(
    "change",
    [
        "image",
        "command",
        "env",
        "ports",
        "privileged",
        "mount",
        "restart",
        "network",
        "label",
    ],
)
def test_container_drift_refuses_start_before_any_command(lab, change):
    cfg, _, state, _ = lab
    s = planned(lab)
    slots.execute(cfg, s, "create", {})
    d = state["candidate"]
    if change == "image":
        d["Image"] = "other"
    elif change == "command":
        d["Config"]["Cmd"] = ["sh"]
    elif change == "env":
        d["Config"]["Env"] = ["SECRET=unexpected"]
    elif change == "ports":
        d["HostConfig"]["PortBindings"]["25576/tcp"][0]["HostIp"] = "0.0.0.0"
    elif change == "privileged":
        d["HostConfig"]["Privileged"] = True
    elif change == "mount":
        d["Mounts"].append({"Destination": "/var/run/docker.sock"})
    elif change == "restart":
        d["HostConfig"]["RestartPolicy"]["Name"] = "always"
    elif change == "network":
        d["HostConfig"]["NetworkMode"] = "host"
    else:
        d["Config"]["Labels"][slots.LABEL] = "other"
    with pytest.raises(AdminError):
        slots.execute(cfg, s, "start", {})
    assert state["commands"] == ["create"]


def test_retained_logs_tampering_blocks_uncertain_release_acceptance(lab, monkeypatch):
    cfg, _, _state, _ = lab
    s = planned(lab)
    slots.execute(cfg, s, "create", {})
    original = slots.backups.docker

    def lost(*args, **kwargs):
        result = original(*args, **kwargs)
        if args[0] == "rm":
            raise OSError("lost")
        return result

    monkeypatch.setattr(slots.backups, "docker", lost)
    with pytest.raises(OSError):
        slots.execute(cfg, s, "release")
    slots.log_path(cfg, slots.read(cfg, s)).write_text("changed")
    with pytest.raises(AdminError):
        slots.execute(cfg, s, "reconcile")
