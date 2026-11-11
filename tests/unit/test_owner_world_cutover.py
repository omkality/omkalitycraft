import copy
import json
from datetime import UTC, datetime, timedelta

import pytest

from omk import (
    admin_backups as backups,
    admin_maintenance as maintenance,
    admin_reset_staging as staging,
    ingress,
    world_cutover as owner,
)
from omk.admin import AdminError
from omk.cli import main
from omk.cold_backup_worker import digest
from tests.unit.test_owner_reset_runtime import (
    flow as runtime_flow,
    runtime_plan,
)


@pytest.fixture
def flow(tmp_path, monkeypatch):
    base = runtime_flow.__wrapped__(tmp_path, monkeypatch)
    setup, operation, _ = base
    cfg, source_flow, window, backup, _data_state, _ = setup
    state = source_flow[1]
    runtime_plan(base)
    staging.execute(cfg, operation, "runtime-stage", {})
    gate = {"policy": {}, "proxy": "immutable"}
    observed = {"closed": True, "sessions": 0}
    monkeypatch.setattr(
        ingress, "capture", lambda *a, **kw: (copy.deepcopy(gate), dict(observed))
    )
    win = maintenance.read_record(cfg, window)
    win["ingress"] = gate
    maintenance.save(cfg, win, "stopped")
    p = staging.read_record(cfg, operation)
    p["maintenance_sha256"] = digest(maintenance.read_record(cfg, window))
    staging.save(cfg, p, "runtime-ready")
    docker = backups.docker

    def inspected(*args, **kw):
        if args[0] == "inspect":
            return json.dumps([{"Config": {"User": ""}}])
        if args[:2] == ("ps", "-aq"):
            return win["initial"]["container"]
        return docker(*args, **kw)

    monkeypatch.setattr(backups, "docker", inspected)
    filesystem = {"phase": "untouched", "writes": [], "lost": None}

    def work(config, record, resource, action):
        if action == "plan":
            return {
                "schema": 1,
                "operation": record["operation"],
                "world": "world",
                "test_identity": "frozen",
            }
        if action in {"apply", "recover", "revert"}:
            assert owner.read(cfg, record["operation"])["stage"] in {
                "applying",
                "reverting",
            }
            filesystem["writes"].append(action)
            filesystem["phase"] = "reverted" if action == "revert" else "installed"
            if filesystem["lost"] == action:
                filesystem["lost"] = None
                raise OSError("lost response after the filesystem action")
        if action == "cancel":
            assert owner.read(cfg, record["operation"])["stage"] == "cancelling"
            assert record["write_lease"] is None
            filesystem["phase"] = "cancelled"
        result = {
            "phase": filesystem["phase"],
            "identity_sha256": digest(record["expected"]),
            "old_world_retained": True,
            "ready_for_players": False,
            "server_started": False,
        }
        return result

    monkeypatch.setattr(owner, "worker", work)
    return cfg, state, window, backup, operation, filesystem, observed


def planned(flow):
    cfg, _, _, _, resource, _, _ = flow
    return owner.plan(cfg, resource)["operation"]


def test_install_start_commit_and_future_maintenance_keep_original_binding(flow):
    cfg, state, window, backup, resource, filesystem, _ = flow
    op = planned(flow)
    assert owner.execute(cfg, op, "apply")["stage"] == "installed"
    with pytest.raises(AdminError, match="cutover is pending"):
        maintenance.execute(cfg, window, "cancel")
    assert (
        maintenance.execute(cfg, window, "start", backup_operation=backup["operation"])[
            "stage"
        ]
        == "complete"
    )
    assert owner.execute(cfg, op, "commit")["stage"] == "committed"
    assert staging.read_record(cfg, resource)["stage"] == "installed"
    assert owner.consumed(cfg, staging.read_record(cfg, resource))
    staging.require_clear(cfg, window)
    assert state["running"] and filesystem["writes"] == ["apply"]
    # A new window captures the newly running generation without changing config.
    next_window = maintenance.plan(cfg, "dj2", {})["operation"]
    assert maintenance.read_record(cfg, next_window)["target"] == backup["target"]


@pytest.mark.parametrize("phase", ["planned", "installed"])
def test_pending_installation_blocks_other_owners_and_opening(flow, phase):
    cfg, _, window, _backup, resource, _, _ = flow
    op = planned(flow)
    if phase == "installed":
        owner.execute(cfg, op, "apply")
    for action in [
        lambda: maintenance.plan(cfg, "dj2", {}),
        lambda: backups.plan(cfg, "dj2", {}),
        lambda: staging.execute(cfg, resource, "abandon"),
        lambda: ingress.operations_clear(cfg, "dj2"),
    ]:
        with pytest.raises(AdminError, match="cutover is pending"):
            action()
    assert maintenance.read_record(cfg, window)["stage"] == "stopped"


@pytest.mark.parametrize("action", ["apply", "revert"])
def test_lost_acknowledgement_verifies_without_repeating_exchange(flow, action):
    cfg, _, _, _, _, filesystem, _ = flow
    op = planned(flow)
    if action == "revert":
        owner.execute(cfg, op, "apply")
    filesystem["lost"] = action
    with pytest.raises(OSError):
        owner.execute(cfg, op, action)
    assert owner.read(cfg, op)["stage"] == (
        "applying" if action == "apply" else "reverting"
    )
    result = owner.execute(cfg, op, "verify")
    assert result["stage"] == ("installed" if action == "apply" else "reverted")
    assert filesystem["writes"].count(action) == 1
    with pytest.raises(AdminError):
        owner.execute(cfg, op, "apply")


def test_prestart_revert_restores_normal_backup_start_path(flow):
    cfg, _, window, backup, resource, filesystem, _ = flow
    op = planned(flow)
    owner.execute(cfg, op, "apply")
    assert owner.execute(cfg, op, "revert")["stage"] == "reverted"
    staging.execute(cfg, resource, "abandon")
    assert (
        maintenance.execute(cfg, window, "start", backup_operation=backup["operation"])[
            "stage"
        ]
        == "complete"
    )
    assert filesystem["writes"] == ["apply", "revert"]


@pytest.mark.parametrize(
    "change",
    [
        "source-boot",
        "window-start-requested",
        "world-writer",
        "ingress-sessions",
        "ingress-id",
        "expired",
    ],
)
def test_changed_inputs_refuse_before_any_filesystem_write(flow, monkeypatch, change):
    cfg, _, window, _, _, filesystem, observed = flow
    op = planned(flow)
    if change == "source-boot":
        point = backups.checkpoint({})
        point["started"] = "another-boot"
        monkeypatch.setattr(backups, "checkpoint", lambda *a: point)
    elif change == "window-start-requested":
        record = maintenance.read_record(cfg, window)
        maintenance.save(cfg, record, "start-requested")
    elif change == "world-writer":
        monkeypatch.setattr(
            "omk.owner_volumes.destination", lambda *a, **kw: {"changed": True}
        )
    elif change == "ingress-sessions":
        observed["sessions"] = 1
    elif change == "ingress-id":
        monkeypatch.setattr(
            ingress, "capture", lambda *a, **kw: ({"changed": True}, dict(observed))
        )
    else:
        r = owner.read(cfg, op)
        r["created_at"] = (datetime.now(UTC) - timedelta(days=2)).isoformat()
        owner.save(cfg, r, "planned")
    with pytest.raises(AdminError):
        owner.execute(cfg, op, "apply")
    assert filesystem["writes"] == []


def test_partial_exchange_cannot_start_and_requires_explicit_recovery(flow):
    cfg, _, window, backup, _, filesystem, _ = flow
    op = planned(flow)
    record = owner.read(cfg, op)
    owner.save(cfg, record, "applying")
    filesystem["phase"] = "parked"
    assert owner.execute(cfg, op, "verify")["stage"] == "applying"
    with pytest.raises(AdminError, match="not confirmed"):
        maintenance.execute(cfg, window, "start", backup_operation=backup["operation"])
    assert owner.execute(cfg, op, "recover")["stage"] == "installed"
    assert filesystem["writes"] == ["recover"]


def test_revert_after_start_is_refused_without_a_filesystem_call(flow):
    cfg, _, window, backup, _, filesystem, _ = flow
    op = planned(flow)
    owner.execute(cfg, op, "apply")
    maintenance.execute(cfg, window, "start", backup_operation=backup["operation"])
    with pytest.raises(AdminError):
        owner.execute(cfg, op, "revert")
    assert filesystem["writes"] == ["apply"]


def test_interrupted_commit_updates_only_journals_and_recovers(flow, monkeypatch):
    cfg, _, window, backup, resource, filesystem, _ = flow
    op = planned(flow)
    owner.execute(cfg, op, "apply")
    maintenance.execute(cfg, window, "start", backup_operation=backup["operation"])
    save = owner.save

    def lost(config, record, stage):
        if stage == "committed":
            raise OSError("lost between two journal acknowledgements")
        return save(config, record, stage)

    monkeypatch.setattr(owner, "save", lost)
    with pytest.raises(OSError):
        owner.execute(cfg, op, "commit")
    assert owner.read(cfg, op)["stage"] == "commit-requested"
    assert staging.read_record(cfg, resource)["stage"] == "installed"
    with pytest.raises(AdminError):
        ingress.operations_clear(cfg, "dj2")
    monkeypatch.setattr(owner, "save", save)
    assert owner.execute(cfg, op, "commit")["stage"] == "committed"
    assert filesystem["writes"] == ["apply"]


def test_status_is_saved_state_and_never_touches_docker(flow, monkeypatch, capsys):
    cfg, _, _, _, _, _, _ = flow
    op = planned(flow)
    monkeypatch.setattr(
        backups, "docker", lambda *a, **kw: pytest.fail("status called Docker")
    )
    assert (
        main(
            [
                "admin",
                "--config",
                str(cfg.private / "operator.toml"),
                "world-cutovers",
                "status",
                "--operation",
                op,
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["stage"] == "planned"


def test_cancellation_revokes_delayed_helper_before_unblocking_source(flow):
    cfg, _, _, _, _, filesystem, _ = flow
    op = planned(flow)
    record = owner.read(cfg, op)
    record["write_lease"] = "d" * 32
    owner.save(cfg, record, "applying", arm=True)
    control = cfg.private / "world-cutover-control" / op / "lease.json"
    assert json.loads(control.read_text())["write_lease"] == "d" * 32
    assert owner.execute(cfg, op, "cancel")["stage"] == "cancelled"
    assert json.loads(control.read_text())["write_lease"] is None
    assert owner.read(cfg, op)["write_lease"] is None
    assert filesystem["writes"] == []


def test_readonly_observation_does_not_rearm_a_previous_write_attempt(flow):
    cfg, _, _, _, _, filesystem, _ = flow
    op = planned(flow)
    record = owner.read(cfg, op)
    record["write_lease"] = "d" * 32
    owner.save(cfg, record, "applying", arm=True)
    filesystem["phase"] = "parked"
    assert owner.execute(cfg, op, "verify")["stage"] == "applying"
    assert owner.read(cfg, op)["write_lease"] is None
    control = cfg.private / "world-cutover-control" / op / "lease.json"
    assert json.loads(control.read_text())["write_lease"] is None


def test_lease_is_revoked_before_the_durable_journal_changes(flow, monkeypatch):
    cfg, _, _, _, _, _, _ = flow
    op = planned(flow)
    r = owner.read(cfg, op)
    write = owner._write_private
    observed = []

    def checked(path, root, value):
        shared = json.loads(
            (cfg.private / "world-cutover-control" / op / "lease.json").read_text()
        )
        assert shared["write_lease"] is None
        observed.append(value["stage"])
        return write(path, root, value)

    monkeypatch.setattr(owner, "_write_private", checked)
    r["write_lease"] = "d" * 32
    owner.save(cfg, r, "applying", arm=True)
    shared = cfg.private / "world-cutover-control" / op / "lease.json"
    assert json.loads(shared.read_text())["write_lease"] == "d" * 32
    owner.save(cfg, r, "cancelled")
    assert observed == ["applying", "cancelled"]
    assert json.loads(shared.read_text())["write_lease"] is None


def test_control_share_exposes_only_a_nonsecret_fence_with_linux_read_permissions(flow):
    cfg, _, _, _, _, _, _ = flow
    op = planned(flow)
    root = cfg.private / "world-cutover-control" / op
    shared = root / "lease.json"
    assert {p.name for p in root.iterdir()} == {"lease.json"}
    assert set(json.loads(shared.read_text())) == {
        "schema",
        "operation",
        "stage",
        "write_lease",
    }
    if __import__("os").name != "nt":
        assert root.stat().st_mode & 0o777 == 0o755
        assert shared.stat().st_mode & 0o777 == 0o644
        assert (
            cfg.private / "world-cutovers" / (op + ".json")
        ).stat().st_mode & 0o077 == 0
