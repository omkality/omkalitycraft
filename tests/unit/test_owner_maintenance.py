import copy
import json
import socket
import threading
import time
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from itertools import count

import pytest

from omk import (
    admin_backups as backups,
    admin_maintenance as owner,
)
from omk.admin import AdminError, _write_private
from omk.maintenance_worker import execute as work
from omk.recovery_console import ConsoleConfig, ConsoleError, command
from tests.unit.test_cold_backups import (
    fixture as cold_fixture,
    stopped,
)
from tests.unit.test_operator_commands import config


@pytest.fixture
def flow(tmp_path, monkeypatch):
    cfg, _ = config(tmp_path)
    cfg = replace(cfg, recovery_consoles={"dj2": ConsoleConfig(25577, "rcon.json")})
    (cfg.private / "maintenance.toml").write_text(
        "schema=1\n[servers.dj2]\nrcon_container_port=25575\n"
    )
    (cfg.private / "maintenance.toml").chmod(0o600)
    _write_private(
        cfg.private / "rcon.json", cfg.private, {"password": "private-credential-12345"}
    )
    target = {
        "container": "owned",
        "data_volume": "data",
        "store_volume": "store",
        "world": "world",
    }
    original = {
        "container": "a" * 64,
        "image": "image",
        "created": "create",
        "started": "old",
        "restart_count": 0,
        "source": {},
        "store": {},
        "running": True,
    }
    state = copy.deepcopy(original)
    point = {
        "container": "a" * 64,
        "started": "old",
        "finished": (datetime.now(UTC) - timedelta(seconds=60)).isoformat(),
        "source": {},
        "store": {},
    }
    actions = []
    monkeypatch.setattr(backups, "target_for", lambda *a: dict(target))
    monkeypatch.setattr(backups, "local_engine", lambda: None)
    monkeypatch.setattr(owner, "snapshot", lambda *a: copy.deepcopy(state))
    monkeypatch.setattr(backups, "checkpoint", lambda *a: copy.deepcopy(point))
    monkeypatch.setattr(owner.RecoveryConsole, "ready", lambda self: None)

    def worker(record, action, backup=None):
        actions.append(action)
        return (
            {"runtime_sha256": "a" * 64}
            if action == "runtime"
            else {"snapshot": backup["result"]}
        )

    def stop(*args):
        actions.append("stop")
        state["running"] = False

    def docker(*args, **kwargs):
        if args[0] == "start":
            actions.append("start")
            assert args[1] == original["container"]
            state.update(running=True, started=datetime.now(UTC).isoformat())
            return args[1]
        if args[0] == "logs":
            return 'Done (3.000s)! For help, type "help"'
        pytest.fail("Unexpected Docker call")

    monkeypatch.setattr(owner, "worker", worker)
    monkeypatch.setattr(owner, "console_stop", stop)
    monkeypatch.setattr(backups, "docker", docker)
    ticks = count(0, 10)
    monkeypatch.setattr(owner.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(owner.time, "sleep", lambda seconds: None)
    return cfg, state, point, actions


def stop_and_backup(flow):
    cfg, _state, point, _actions = flow
    op = owner.plan(cfg, "dj2", {})["operation"]
    assert owner.execute(cfg, op, "stop", environment={})["stage"] == "stopped"
    record = owner.read_record(cfg, op)
    backup = {
        "schema": 1,
        "operation": "b" * 32,
        "stage": "complete",
        "server": "dj2",
        "target": record["target"],
        "operator_root": record["operator_root"],
        "checkpoint": copy.deepcopy(point),
        "source": {"runtime_sha256": "a" * 64},
        "settings": backups.settings({}),
        "result": {"id": "snapshot-" + "c" * 32, "sha256": "d" * 64},
    }
    (cfg.private / "backups").mkdir()
    backups.save(cfg, backup, "complete")
    return op, backup


def test_clean_window_needs_backup_and_starts_same_id(flow):
    op, backup = stop_and_backup(flow)
    cfg, state, _, actions = flow
    with pytest.raises(AdminError, match="identifier"):
        owner.execute(cfg, op, "start")
    assert "start" not in actions and state["running"] is False
    result = owner.execute(cfg, op, "start", backup_operation=backup["operation"])
    assert result["stage"] == "complete" and result["ready_for_players"] is False
    assert actions.count("stop") == actions.count("start") == 1
    assert owner.execute(cfg, op, "status") == result
    contents = "".join(p.read_text() for p in (cfg.private / "maintenance").iterdir())
    assert "private-credential" not in contents and '"password"' not in contents
    with pytest.raises(AdminError, match="stage"):
        owner.execute(cfg, op, "start", backup_operation=backup["operation"])


def test_existing_window_blocks_plan_and_cancel_does_not_start(flow):
    cfg, state, _, actions = flow
    op = owner.plan(cfg, "dj2", {})["operation"]
    with pytest.raises(AdminError, match="existing"):
        owner.plan(cfg, "dj2", {})
    owner.execute(cfg, op, "stop", environment={})
    assert owner.execute(cfg, op, "cancel")["stage"] == "cancelled"
    assert state["running"] is False and "start" not in actions
    with pytest.raises(AdminError, match="running source"):
        owner.plan(cfg, "dj2", {})


@pytest.mark.parametrize(
    "change", ["identity", "runtime", "endpoint", "age", "settings", "boot"]
)
def test_changed_plan_refuses_stop(flow, monkeypatch, change):
    cfg, state, _, actions = flow
    op = owner.plan(cfg, "dj2", {})["operation"]
    if change == "identity":
        state["container"] = "replaced"
    elif change == "runtime":
        monkeypatch.setattr(owner, "worker", lambda *a: {"runtime_sha256": "changed"})
    elif change == "endpoint":
        (cfg.private / "maintenance.toml").write_text(
            "schema=1\n[servers.dj2]\nrcon_container_port=25574\n"
        )
    elif change == "age":
        record = owner.read_record(cfg, op)
        record["created_at"] = (datetime.now(UTC) - timedelta(days=2)).isoformat()
        owner.save(cfg, record, "planned")
    elif change == "settings":
        monkeypatch.setenv("OMK_MAINTENANCE_STOP_TIMEOUT_SECONDS", "30")
    else:
        state["started"] = "new-boot"
    with pytest.raises(AdminError):
        owner.execute(cfg, op, "stop", environment=None if change == "settings" else {})
    assert "stop" not in actions


@pytest.mark.parametrize(
    "change", ["stage", "server", "checkpoint", "target", "runtime", "proof"]
)
def test_incomplete_stale_or_corrupt_backup_never_starts(flow, monkeypatch, change):
    op, backup = stop_and_backup(flow)
    cfg, state, _, actions = flow
    if change == "stage":
        backup["stage"] = "published"
    elif change == "server":
        backup["server"] = "gtnh"
    elif change == "checkpoint":
        backup["checkpoint"]["finished"] = "another-stop"
    elif change == "target":
        backup["target"]["data_volume"] = "other"
    elif change == "runtime":
        backup["source"]["runtime_sha256"] = "other"
    else:

        def fail(*args):
            raise AdminError("Changed backup proof")

        monkeypatch.setattr(owner, "worker", fail)
    backups.save(cfg, backup, backup["stage"])
    with pytest.raises(AdminError):
        owner.execute(cfg, op, "start", backup_operation=backup["operation"])
    assert "start" not in actions and state["running"] is False


def test_interrupted_stop_reconciles_without_second_command(flow, monkeypatch):
    cfg, state, _, actions = flow
    op = owner.plan(cfg, "dj2", {})["operation"]
    original = owner.console_stop

    def crash(*args):
        original(*args)
        raise KeyboardInterrupt

    monkeypatch.setattr(owner, "console_stop", crash)
    with pytest.raises(KeyboardInterrupt):
        owner.execute(cfg, op, "stop", environment={})
    assert owner.read_record(cfg, op)["stage"] == "stop-requested"
    with pytest.raises(AdminError):
        owner.execute(cfg, op, "cancel")
    assert owner.execute(cfg, op, "reconcile")["stage"] == "stopped"
    assert actions.count("stop") == 1 and not state["running"]


@pytest.mark.parametrize("crash_type", [KeyboardInterrupt, AdminError])
def test_interrupted_start_reconciles_without_second_start(
    flow, monkeypatch, crash_type
):
    op, backup = stop_and_backup(flow)
    cfg, _, _, actions = flow
    original = backups.docker

    def crash(*args, **kwargs):
        value = original(*args, **kwargs)
        if args[0] == "start":
            raise crash_type("Controller lost the start outcome")
        return value

    monkeypatch.setattr(backups, "docker", crash)
    with pytest.raises(crash_type):
        owner.execute(cfg, op, "start", backup_operation=backup["operation"])
    assert owner.read_record(cfg, op)["stage"] == "start-requested"
    assert owner.execute(cfg, op, "reconcile")["stage"] == "complete"
    assert actions.count("start") == 1


@pytest.mark.parametrize("fault", ["readiness", "fatal", "early-boot", "crashed"])
def test_failed_boot_is_never_complete(flow, monkeypatch, fault):
    op, backup = stop_and_backup(flow)
    cfg, state, _, actions = flow
    original = backups.docker

    def docker(*args, **kwargs):
        result = original(*args, **kwargs)
        if args[0] == "start":
            if fault == "crashed":
                state["running"] = False
            if fault == "early-boot":
                state["started"] = "2020-01-01T00:00:00+00:00"
        if args[0] == "logs" and fault == "fatal":
            return "Encountered an unexpected exception"
        return result

    monkeypatch.setattr(backups, "docker", docker)
    if fault == "readiness":

        def unavailable(self):
            raise ConsoleError("unavailable")

        monkeypatch.setattr(owner.RecoveryConsole, "ready", unavailable)
        monkeypatch.setattr(owner.time, "sleep", lambda seconds: None)
        ticks = iter([0, 601])
        monkeypatch.setattr(owner.time, "monotonic", lambda: next(ticks))
    with pytest.raises(AdminError):
        owner.execute(cfg, op, "start", backup_operation=backup["operation"])
    assert owner.read_record(cfg, op)["stage"] == "start-requested"
    assert actions.count("start") == 1


@pytest.mark.parametrize(
    "fault",
    [
        "foreign-label",
        "image",
        "mount",
        "nested",
        "restart",
        "log",
        "oom",
        "published-ip",
        "published-port",
        "active-port",
        "writer",
    ],
)
def test_metadata_binds_console_to_owned_container(monkeypatch, fault):
    data = stopped()
    data["Id"] = "a" * 64
    data["State"].update(Running=True, Status="running", Paused=False, Restarting=False)
    endpoint = {"port": 25577, "rcon_container_port": 25575}
    ports = {"25575/tcp": [{"HostIp": "127.0.0.1", "HostPort": "25577"}]}
    data["HostConfig"].update(PortBindings=copy.deepcopy(ports), NetworkMode="bridge")
    data["NetworkSettings"] = {"Ports": copy.deepcopy(ports)}
    target = {
        "container": "owned",
        "label": "omkality.test",
        "source_owner": "source-owner",
        "data_volume": "source-volume",
        "image": data["Config"]["Image"],
    }
    active = data["Id"]
    if fault == "foreign-label":
        data["Config"]["Labels"] = {}
    elif fault == "image":
        data["Config"]["Image"] = "other"
    elif fault == "mount":
        data["Mounts"][0]["Name"] = "other"
    elif fault == "nested":
        data["Mounts"].append({"Destination": "/srv/world"})
    elif fault == "restart":
        data["HostConfig"]["RestartPolicy"]["Name"] = "always"
    elif fault == "log":
        data["HostConfig"]["LogConfig"]["Type"] = "json-file"
    elif fault == "oom":
        data["State"]["OOMKilled"] = True
    elif fault == "published-ip":
        data["HostConfig"]["PortBindings"]["25575/tcp"][0]["HostIp"] = "0.0.0.0"
    elif fault == "published-port":
        data["HostConfig"]["PortBindings"] = {}
    elif fault == "active-port":
        data["NetworkSettings"]["Ports"] = {}
    else:
        active += "\nforeign-writer"
    monkeypatch.setattr(
        backups,
        "docker",
        lambda *args: json.dumps([data]) if args[0] == "inspect" else active,
    )
    monkeypatch.setattr(backups, "volume", lambda *a: {})
    with pytest.raises(AdminError):
        owner.snapshot(target, endpoint)


def test_recovery_adapter_does_not_gain_stop_privilege():
    with pytest.raises(ConsoleError, match="Unsupported"):
        command(ConsoleConfig(25577, "rcon.json"), "secret" * 4, "stop")


def test_fatal_after_done_during_stability_period_is_refused(flow, monkeypatch):
    op, backup = stop_and_backup(flow)
    cfg, _, _, _ = flow
    original = backups.docker
    replies = iter(["Done (3s)!", "Done (3s)!\nThis crash report has been saved to:"])

    def docker(*args, **kwargs):
        return next(replies) if args[0] == "logs" else original(*args, **kwargs)

    monkeypatch.setattr(backups, "docker", docker)
    with pytest.raises(AdminError, match="fatal"):
        owner.execute(cfg, op, "start", backup_operation=backup["operation"])
    assert owner.read_record(cfg, op)["stage"] == "start-requested"


def test_engine_clock_behind_host_still_accepts_boot_after_its_own_stop(
    flow, monkeypatch
):
    op, backup = stop_and_backup(flow)
    cfg, state, _, _ = flow
    original = backups.docker

    def docker(*args, **kwargs):
        result = original(*args, **kwargs)
        if args[0] == "start":
            # Docker VM is 30 seconds behind the controller. Its new boot is
            # still later than its previous clean stop (60 seconds ago).
            state["started"] = (datetime.now(UTC) - timedelta(seconds=30)).isoformat()
        return result

    monkeypatch.setattr(backups, "docker", docker)
    assert (
        owner.execute(cfg, op, "start", backup_operation=backup["operation"])["stage"]
        == "complete"
    )


def test_intermittent_console_readiness_resets_stability_interval(flow, monkeypatch):
    op, backup = stop_and_backup(flow)
    cfg, _, _, _ = flow
    calls = []

    def ready(self):
        calls.append(True)
        if len(calls) == 2:
            raise ConsoleError("temporary gap")

    monkeypatch.setattr(owner.RecoveryConsole, "ready", ready)
    assert (
        owner.execute(cfg, op, "start", backup_operation=backup["operation"])["stage"]
        == "complete"
    )
    assert len(calls) >= 4


@pytest.mark.parametrize(
    "key",
    [
        "STOP_TIMEOUT_SECONDS",
        "START_TIMEOUT_SECONDS",
        "POLL_MILLISECONDS",
        "JOURNAL_COUNT",
        "PLAN_TTL_SECONDS",
    ],
)
def test_invalid_policy_is_redacted(key):
    with pytest.raises(AdminError) as error:
        owner.settings({"OMK_MAINTENANCE_" + key: "secret-123"})
    assert "secret-123" not in str(error.value)


@pytest.fixture
def data(tmp_path):
    return cold_fixture.__wrapped__(tmp_path)


def completed_fixture(data):
    from omk import cold_backup_worker as cold  # noqa: PLC0415

    root, storage, request = data
    (root / "server.properties").write_text(
        "enable-rcon=true\nrcon.port=25575\nrcon.password=" + "p" * 24 + "\n"
    )
    request.update(cold.execute({**request, "action": "plan"}, root, storage))
    request["prepared"] = cold.prepare(root, storage, request)
    request["result"] = cold.publish(storage, request)
    cold.acknowledge(storage, request)
    return root, storage, {**request, "action": "proof", "snapshot": request["result"]}


def test_runtime_and_snapshot_proof_are_readonly_and_redacted(data):
    root, storage, request = completed_fixture(data)
    before = {
        p.relative_to(storage).as_posix(): p.read_bytes()
        for p in storage.rglob("*")
        if p.is_file()
    }
    result = work(request, root, storage)
    runtime = work({"action": "runtime", "rcon_container_port": 25575}, root, storage)
    assert result["source"] == request["source"]
    assert runtime["runtime_sha256"] == result["source"]["runtime_sha256"]
    assert "p" * 24 not in json.dumps([runtime, result])
    assert before == {
        p.relative_to(storage).as_posix(): p.read_bytes()
        for p in storage.rglob("*")
        if p.is_file()
    }


@pytest.mark.parametrize(
    "change",
    [
        "world",
        "runtime",
        "archive",
        "pending",
        "snapshot",
        "duplicate-port",
        "disabled",
    ],
)
def test_readonly_worker_refuses_changed_inputs(data, change):
    root, storage, request = completed_fixture(data)
    if change == "world":
        (root / "world/level.dat").write_bytes(b"changed")
    elif change == "runtime":
        (root / "server.jar").write_bytes(b"changed")
    elif change == "archive":
        (storage / "store" / request["snapshot"]["id"] / "archive.zip").write_bytes(
            b"changed"
        )
    elif change == "pending":
        (storage / "receipt.json").write_text("{}")
    elif change == "snapshot":
        request["snapshot"] = {**request["snapshot"], "id": "snapshot-" + "0" * 32}
    else:
        with (root / "server.properties").open("a") as stream:
            stream.write(
                "rcon.port=25575\n"
                if change == "duplicate-port"
                else "enable-rcon=false\n"
            )
        request = {"action": "runtime", "rcon_container_port": 25575}
    with pytest.raises((ValueError, OSError)):
        work(request, root, storage)


@pytest.mark.parametrize("authenticated", [True, False])
def test_fixed_stop_transport_waits_for_auth_and_sends_no_delimiter(authenticated):
    from omk import (  # noqa: PLC0415
        maintenance_console as transport,
        recovery_console as wire,
    )

    seen, failures = [], []
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()

        def serve():
            try:
                with listener.accept()[0] as stream:
                    packet = wire._receive(stream, time.monotonic() + 3)
                    seen.append(packet)
                    stream.sendall(wire._packet(1 if authenticated else -1, 2, ""))
                    if authenticated:
                        seen.append(wire._receive(stream, time.monotonic() + 3))
                    assert stream.recv(1) == b""
            except BaseException as error:
                failures.append(type(error).__name__)

        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        console = ConsoleConfig(listener.getsockname()[1], "rcon.json")
        if authenticated:
            transport.stop(console, "local-test-credential")
        else:
            with pytest.raises(ConsoleError, match="authentication"):
                transport.stop(console, "local-test-credential")
        thread.join(5)
    assert not thread.is_alive() and failures == []
    assert seen == [(1, 3, "local-test-credential")] + (
        [(2, 2, "stop")] if authenticated else []
    )
