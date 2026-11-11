import json
from copy import deepcopy

import pytest

from omk import admin_storage as owner
from omk.admin import AdminError
from omk.cli import main
from tests.unit.test_operator_commands import config


@pytest.fixture
def controller(tmp_path, monkeypatch):
    cfg, path = config(tmp_path)
    target = {"world": "world", "data_volume": "source", "store_volume": "store"}
    state = {"calls": [], "engine": 0, "generation": 1, "lost": False}
    report = {
        "schema": 1,
        "resources": [],
        "filesystems": [{"roles": ["source", "store"], "available_bytes": 200}],
        "read_only": True,
        "metadata_only": True,
        "host_disk_complete": False,
    }

    def engine():
        state["engine"] += 1

    def source(config, server):
        if server not in config.servers:
            raise AdminError("Server is not in the operator allowlist")
        return dict(target)

    def volume(target, store=False):
        return {
            "created": state["generation"],
            "name": target["store_volume" if store else "data_volume"],
        }

    def docker(*args, **kw):
        state["calls"].append((args, kw))
        if state["lost"]:
            raise AdminError("Docker unavailable")
        return json.dumps({"ok": True, "result": deepcopy(report)})

    monkeypatch.setattr(owner.backups, "local_engine", engine)
    monkeypatch.setattr(owner.backups, "target_for", source)
    monkeypatch.setattr(owner.backups, "volume", volume)
    monkeypatch.setattr(owner.backups, "docker", docker)
    return cfg, path, state, report


def test_cli_only_reads_explicit_volumes_in_sandboxed_pinned_helper(
    controller, capsys, monkeypatch
):
    cfg, path, state, _ = controller
    monkeypatch.setenv("OMK_BACKUP_RESERVE_BYTES", "201")
    monkeypatch.setenv("OMK_STORAGE_MAX_ENTRIES", "50000")
    assert (
        main(["admin", "--config", str(path), "storage", "inspect", "--server", "dj2"])
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert result["filesystems"][0]["below_reserve"] is True
    assert result["host_disk_complete"] is False
    assert state["engine"] == 1
    assert len(state["calls"]) == 1
    args, kwargs = state["calls"][0]
    assert args[0] == "run" and "--rm" in args and "--read-only" in args
    assert args[args.index("--network") + 1] == "none"
    assert args[args.index("--cap-drop") + 1] == "ALL"
    assert owner.backups.IMAGE in args
    mounts = [args[i + 1] for i, arg in enumerate(args) if arg == "--mount"]
    assert all(",readonly" in mount for mount in mounts)
    assert all("volume-nocopy" in mount for mount in mounts if "type=volume" in mount)
    assert not any("docker.sock" in value for value in args)
    assert json.loads(kwargs["stdin"])["limits"]["max_entries"] == 50000
    assert not (cfg.private / "world-cutovers").exists()
    assert not cfg.auth_file.exists()


def test_foreign_server_is_refused_before_worker(controller):
    cfg, _, state, _ = controller
    with pytest.raises(AdminError, match="allowlist"):
        owner.inspect(cfg, "other", {})
    assert not state["calls"]


def test_remote_engine_refusal_precedes_all_volume_work(controller, monkeypatch):
    cfg, _, state, _ = controller

    def remote():
        raise AdminError("Require local Linux Docker")

    monkeypatch.setattr(owner.backups, "local_engine", remote)
    with pytest.raises(AdminError, match="local Linux"):
        owner.inspect(cfg, "dj2", {})
    assert not state["calls"]


def test_lost_worker_response_has_no_mutating_retry(controller):
    cfg, _, state, _ = controller
    state["lost"] = True
    with pytest.raises(AdminError):
        owner.inspect(cfg, "dj2", {})
    assert len(state["calls"]) == 1


def test_recreated_volume_during_inspection_is_not_accepted(controller, monkeypatch):
    cfg, _, state, _ = controller
    original = owner.backups.docker

    def changed(*args, **kw):
        result = original(*args, **kw)
        state["generation"] += 1
        return result

    monkeypatch.setattr(owner.backups, "docker", changed)
    with pytest.raises(AdminError, match="identity"):
        owner.inspect(cfg, "dj2", {})


@pytest.mark.parametrize("field,value", [("schema", 2), ("read_only", False)])
def test_invalid_helper_report_refused(controller, field, value):
    cfg, _, _, report = controller
    report[field] = value
    with pytest.raises(AdminError, match="response"):
        owner.inspect(cfg, "dj2", {})


@pytest.mark.parametrize("raw", ["0", "-1", "1.5", "true", "1000001", "", "１２"])
def test_invalid_scan_limit_refused(raw):
    with pytest.raises(AdminError):
        owner.limits({"OMK_STORAGE_MAX_ENTRIES": raw})


@pytest.mark.parametrize("foreign", [False, True])
def test_optional_staging_volume_requires_matching_owner_without_unused_requirement(
    controller, monkeypatch, foreign
):
    cfg, _, state, _ = controller
    (cfg.private / "resource-resets.toml").write_text("fixture")
    monkeypatch.setattr(owner.owner_volumes, "document", lambda *a: {"dj2": {}})
    monkeypatch.setattr(
        owner.owner_volumes,
        "target_for",
        lambda *a: {
            "data_volume": "candidate",
            "label": "omkality.fixture",
            "owner": "ours",
        },
    )
    original = owner.backups.docker

    def docker(*args, **kw):
        if args[0] == "volume":
            return json.dumps(
                [
                    {
                        "Name": "candidate",
                        "CreatedAt": "date",
                        "Labels": {
                            "omkality.fixture": "foreign" if foreign else "ours"
                        },
                    }
                ]
            )
        return original(*args, **kw)

    monkeypatch.setattr(owner.backups, "docker", docker)
    if foreign:
        with pytest.raises(AdminError, match="owned"):
            owner.inspect(cfg, "dj2", {})
        assert not state["calls"]
    else:
        owner.inspect(cfg, "dj2", {})
        assert json.loads(state["calls"][0][1]["stdin"])["roles"] == [
            "source",
            "store",
            "reset",
        ]
