import copy
import json
from datetime import UTC, datetime

import pytest

from omk import admin_nightly as owner
from omk.admin import AdminError
from omk.admin_maintenance import worker as real_worker
from omk.cli import main
from omk.ftb_backup_policy import ADAPTER, SHA256
from tests.unit.test_operator_commands import config


@pytest.fixture
def flow(tmp_path, monkeypatch):
    cfg, path = config(tmp_path)
    (cfg.private / "nightly.toml").write_text(
        f'schema=1\n[servers.dj2]\nadapter="{ADAPTER}"\n'
    )
    (cfg.private / "nightly.toml").chmod(0o600)
    state = {"running": True, "container": "a" * 64}
    target = {"container": "owned", "data_volume": "source", "store_volume": "store"}
    proof = {
        "adapter": ADAPTER,
        "artifact_sha256": SHA256,
        "config_sha256": "b" * 64,
        "runtime_sha256": "c" * 64,
        "stock_enabled_on_disk": False,
        "stock_shutdown_on_disk": False,
        "live_config_verified": False,
        "other_writers_verified": False,
    }
    calls = []
    monkeypatch.setattr(owner.backups, "target_for", lambda *a: copy.deepcopy(target))
    monkeypatch.setattr(owner.backups, "local_engine", lambda: None)
    monkeypatch.setattr(
        owner.maintenance, "binding", lambda *a: {"rcon_container_port": 25575}
    )
    monkeypatch.setattr(owner.maintenance, "snapshot", lambda *a: copy.deepcopy(state))

    def worker(record, action):
        assert action == "nightly-policy"
        assert record["target"] == target
        calls.append(action)
        return copy.deepcopy(proof)

    monkeypatch.setattr(owner.maintenance, "worker", worker)
    return cfg, path, state, proof, calls, worker


def test_cli_preflight_does_not_enable_restart_or_claim_loaded_policy(flow, capsys):
    cfg, path, _state, proof, calls, _worker = flow
    assert (
        main(["admin", "--config", str(path), "nightly", "inspect", "--server", "dj2"])
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert result["source_running"]
    assert result["disk_policy"] == proof
    assert result["scheduler_enabled"] is result["activation_approved"] is False
    assert calls == ["nightly-policy"]
    assert sorted(p.name for p in cfg.private.iterdir()) == [
        "audit.jsonl",
        "backups.lock",
        "nightly.toml",
        "operator.toml",
    ]


def test_cli_calendar_does_not_need_docker_or_nightly_allowlist(
    tmp_path, monkeypatch, capsys
):
    _cfg, path = config(tmp_path)
    monkeypatch.setattr(
        owner.backups,
        "docker",
        lambda *a, **k: pytest.fail("Calendar must not call Docker"),
    )
    assert main(["admin", "--config", str(path), "nightly", "preview"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert (
        result["mode"] == "calendar_preview" and result["activation_approved"] is False
    )


@pytest.mark.parametrize(
    "text",
    [
        'schema=true\n[servers.dj2]\nadapter="' + ADAPTER + '"',
        'schema=1\n[servers.unknown]\nadapter="' + ADAPTER + '"',
        'schema=1\n[servers.dj2]\nadapter="unknown"',
        'schema=1\n[servers.dj2]\nadapter="' + ADAPTER + '"\nextra=true',
        "schema=1\nservers={}",
    ],
)
def test_unreviewed_or_unknown_bindings_refused(flow, text):
    cfg, *_ = flow
    (cfg.private / "nightly.toml").write_text(text)
    with pytest.raises(AdminError):
        owner.inspect(cfg, "dj2", {})


@pytest.mark.parametrize(
    "key,value",
    [
        ("artifact_sha256", "a" * 64),
        ("runtime_sha256", "not-a-hash"),
        ("stock_enabled_on_disk", True),
        ("stock_shutdown_on_disk", 0),
        ("other_writers_verified", True),
        ("live_config_verified", True),
        ("unexpected", "field"),
    ],
)
def test_invalid_or_overstated_worker_proof_refused(flow, key, value):
    cfg, _, _, proof, *_ = flow
    proof[key] = value
    with pytest.raises(AdminError, match="proof"):
        owner.inspect(cfg, "dj2", {})


def test_changed_lifecycle_after_worker_never_accepted(flow, monkeypatch):
    cfg, _, state, _, _, worker = flow

    def changed(*args):
        value = worker(*args)
        state["container"] = "replaced"
        return value

    monkeypatch.setattr(owner.maintenance, "worker", changed)
    with pytest.raises(AdminError, match="changed"):
        owner.inspect(cfg, "dj2", {})


def test_changed_binding_after_worker_never_accepted(flow, monkeypatch):
    cfg, *_ = flow
    calls = []

    def binding(*args):
        calls.append(1)
        return {"rcon_container_port": 25575 if len(calls) == 1 else 25574}

    monkeypatch.setattr(owner.maintenance, "binding", binding)
    with pytest.raises(AdminError, match="changed"):
        owner.inspect(cfg, "dj2", {})


def test_failing_worker_never_makes_lifecycle_calls_or_operation_journals(
    flow, monkeypatch
):
    cfg, *_ = flow

    def fail(*args):
        raise AdminError("Disk policy refused")

    monkeypatch.setattr(owner.maintenance, "worker", fail)
    with pytest.raises(AdminError, match="refused"):
        owner.inspect(cfg, "dj2", {}, now=datetime(2026, 11, 12, tzinfo=UTC))
    assert not (cfg.private / "maintenance").exists()
    assert not (cfg.private / "backups").exists()


def test_real_helper_sandbox_is_readonly_and_uses_pinned_image(flow, monkeypatch):
    _cfg, _, _, proof, *_ = flow
    monkeypatch.setattr(owner.backups, "volume", lambda *a: {})
    calls = []

    def docker(*args, **kw):
        calls.append((args, kw))
        return json.dumps({"ok": True, **proof})

    monkeypatch.setattr(owner.backups, "docker", docker)
    result = real_worker(
        {
            "operation": "a" * 32,
            "target": {"data_volume": "owned", "store_volume": "store"},
            "binding": {"rcon_container_port": 25575},
        },
        "nightly-policy",
    )
    args, kw = calls[0]
    assert result == proof and len(calls) == 1
    assert "none" in args and "--read-only" in args and "ALL" in args
    assert owner.backups.IMAGE in args and "no-new-privileges:true" in args
    mounts = [args[i + 1] for i, arg in enumerate(args) if arg == "--mount"]
    assert all(m.endswith(",readonly") for m in mounts) and len(mounts) == 2
    assert not any("docker.sock" in a or a == "store" for a in args)
    assert json.loads(kw["stdin"])["action"] == "nightly-policy"
