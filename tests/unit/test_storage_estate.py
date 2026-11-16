import json
from dataclasses import replace
from unittest.mock import Mock

import pytest

from omk import storage_estate as owner
from omk.admin import AdminError
from omk.cli import main
from omk.storage_estate import worker as real_worker
from tests.unit.test_operator_commands import config


@pytest.fixture
def controller(tmp_path, monkeypatch):
    cfg, path = config(tmp_path)
    cfg = replace(
        cfg,
        servers={
            "dj2": tmp_path / "first",
            "second": tmp_path / "second",
            "future": tmp_path / "future",
        },
    )
    path.write_text(
        'schema=1\n[servers.dj2]\nroot="../first"\n[servers.second]\nroot="../second"\n[servers.future]\nroot="../future"\n'
    )
    state = {"generation": 1, "calls": [], "worker": 0}
    file = cfg.private / "storage.toml"
    file.write_text(
        'schema=1\n[volumes.auth]\nvolume="auth-volume"\nlabel="omkality.project"\nowner="owned"\n'
    )
    file.chmod(0o600)
    monkeypatch.setattr(
        owner.owner_volumes, "document", lambda *a: {"dj2": {}, "second": {}}
    )
    monkeypatch.setattr(owner.backups, "local_engine", Mock())
    monkeypatch.setattr(
        owner.admin_storage,
        "targets",
        lambda config, server: (
            {"world": "world-" + server},
            [
                (role, server + "-" + role, {"created": "date"})
                for role in ["source", "store"]
            ],
        ),
    )

    def docker(*args, **kw):
        state["calls"].append((args, kw))
        assert args[0] == "volume"
        return json.dumps(
            [
                {
                    "Name": "auth-volume",
                    "CreatedAt": state["generation"],
                    "Labels": {"omkality.project": "owned"},
                }
            ]
        )

    monkeypatch.setattr(owner.backups, "docker", docker)

    def worker(values, limits, policy):
        state["worker"] += 1
        return {
            "schema": 1,
            "read_only": True,
            "resources": [
                {
                    "id": e["id"],
                    "role": e["role"],
                    "categories": {
                        "active_world" if e["role"] == "source" else e["role"]: {
                            "apparent_bytes": 100,
                            "allocated_bytes": 4096,
                        }
                    },
                }
                for e in values
            ],
            "filesystems": [
                {
                    "resources": [e["id"] for e in values],
                    "total_bytes": 220 * 1024**3,
                    "available_bytes": 100 * 1024**3,
                }
            ],
        }

    monkeypatch.setattr(owner, "worker", worker)
    return cfg, path, state, worker


def test_cli_counts_all_configured_servers_and_shared_auth_once(controller, capsys):
    cfg, path, state, _ = controller
    assert main(["admin", "--config", str(path), "storage", "estate"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["configured_servers"] == ["dj2", "second"]
    assert report["unconfigured_servers"] == ["future"]
    assert report["shared_roles"] == ["auth"]
    assert report["missing_shared_roles"] == [
        "content",
        "exports",
        "metrics",
        "reports",
    ]
    assert len(report["resources"]) == 5
    assert report["budget"]["categories"]["worlds"]["apparent_bytes"] == 200
    assert not report["budget"]["observed_within_limits"]
    assert report["budget"]["categories"]["system"]["over_budget"]
    assert not report["budget"]["admission_approved"]
    assert not report["budget"]["declared_operation_limits"]["compatible"]
    assert state["worker"] == 1 and len(state["calls"]) == 2
    assert not cfg.auth_file.exists()


def test_invalid_budget_stops_before_docker_or_worker(controller):
    cfg, _, state, _ = controller
    with pytest.raises(AdminError):
        owner.inspect(cfg, {"OMK_STORAGE_DISK_GIB": "1"})
    assert not state["calls"] and state["worker"] == 0
    owner.backups.local_engine.assert_not_called()


def test_shared_volume_recreation_during_census_is_refused(controller, monkeypatch):
    cfg, _, state, worker = controller

    def changed(*args):
        result = worker(*args)
        state["generation"] += 1
        return result

    monkeypatch.setattr(owner, "worker", changed)
    with pytest.raises(AdminError, match="identity"):
        owner.inspect(cfg, {})


def test_foreign_or_missing_shared_volume_refused_before_worker(
    controller, monkeypatch
):
    cfg, _, state, _ = controller
    monkeypatch.setattr(
        owner.backups,
        "docker",
        lambda *a, **kw: json.dumps(
            [{"Name": "auth-volume", "Labels": {}, "CreatedAt": "date"}]
        ),
    )
    with pytest.raises(AdminError, match="owned"):
        owner.inspect(cfg, {})
    assert state["worker"] == 0


def test_shared_volume_cannot_alias_any_game_or_backup_volume(controller):
    cfg, _, _, _ = controller
    file = cfg.private / "storage.toml"
    file.write_text(file.read_text().replace("auth-volume", "dj2-source"))
    # Return the alias identity too; the name/label check alone must not suffice.
    owner.backups.docker = Mock(
        return_value=json.dumps(
            [
                {
                    "Name": "dj2-source",
                    "Labels": {"omkality.project": "owned"},
                    "CreatedAt": "date",
                }
            ]
        )
    )
    with pytest.raises(AdminError, match="alias"):
        owner.resources(cfg)


@pytest.mark.parametrize(
    "text",
    [
        'schema=true\n[volumes.auth]\nvolume="name"\nlabel="omkality.role"\nowner="owner"',
        'schema=1\n[volumes.content]\nvolume="name"\nlabel="omkality.role"\nowner="owner"',
        'schema=1\n[volumes.auth]\nvolume="../escape"\nlabel="omkality.role"\nowner="owner"',
        'schema=1\n[volumes.auth]\nvolume="name"\nlabel="unknown.label"\nowner="owner"',
        'schema=1\n[volumes.auth]\nvolume="name"\nlabel="omkality.role"\nowner="owner"\npassword="secret-canary"',
    ],
)
def test_strict_private_registry_does_not_echo_invalid_values(controller, text):
    cfg, _, _, _ = controller
    (cfg.private / "storage.toml").write_text(text)
    with pytest.raises(AdminError) as error:
        owner.shared(cfg)
    assert "secret-canary" not in str(error.value)


def test_shared_registry_missing_is_not_silently_ignored(controller):
    cfg, _, _, _ = controller
    (cfg.private / "storage.toml").unlink()
    with pytest.raises(AdminError, match="explicit"):
        owner.shared(cfg)


@pytest.fixture
def metrics_controller(controller, monkeypatch):
    cfg, _, state, _ = controller
    file = cfg.private / "storage.toml"
    file.write_text(
        file.read_text()
        + '\n[volumes.metrics]\nvolume="metrics-volume"\nlabel="omkality.project"\nowner="owned"\n'
    )

    def docker(*args, **kw):
        state["calls"].append((args, kw))
        assert args[:2] == ("volume", "inspect")
        return json.dumps(
            [
                {
                    "Name": args[2],
                    "CreatedAt": (
                        state["generation"] if args[2] == "metrics-volume" else 1
                    ),
                    "Labels": {"omkality.project": "owned"},
                }
            ]
        )

    monkeypatch.setattr(owner.backups, "docker", docker)
    return controller


def test_explicit_metrics_volume_is_counted_once_in_system_budget(metrics_controller):
    cfg, _, state, _ = metrics_controller
    report = owner.inspect(cfg, {})
    assert report["shared_roles"] == ["auth", "metrics"]
    assert report["missing_shared_roles"] == ["content", "exports", "reports"]
    metrics = [r for r in report["resources"] if r["role"] == "metrics"]
    assert len(metrics) == 1 and metrics[0]["server"] is None
    assert metrics[0]["categories"]["metrics"]["apparent_bytes"] == 100
    assert report["budget"]["categories"]["system"]["apparent_bytes"] == 200
    assert not report["budget"]["admission_approved"]
    assert state["worker"] == 1


def test_metrics_recreation_during_census_is_refused(metrics_controller, monkeypatch):
    cfg, _, state, worker = metrics_controller

    def changed(*args):
        value = worker(*args)
        state["generation"] += 1
        return value

    monkeypatch.setattr(owner, "worker", changed)
    with pytest.raises(AdminError, match="identity"):
        owner.inspect(cfg, {})


def test_foreign_metrics_is_refused_before_worker(metrics_controller, monkeypatch):
    cfg, _, state, _ = metrics_controller
    docker = owner.backups.docker

    def foreign(*args, **kwargs):
        rows = json.loads(docker(*args, **kwargs))
        if args[2] == "metrics-volume":
            rows[0]["Labels"] = {}
        return json.dumps(rows)

    monkeypatch.setattr(owner.backups, "docker", foreign)
    with pytest.raises(AdminError, match="owned"):
        owner.inspect(cfg, {})
    assert state["worker"] == 0


@pytest.mark.parametrize("alias", ["auth-volume", "dj2-source", "second-store"])
def test_metrics_cannot_alias_another_owned_role(metrics_controller, alias):
    cfg, _, _, _ = metrics_controller
    file = cfg.private / "storage.toml"
    file.write_text(file.read_text().replace("metrics-volume", alias))
    with pytest.raises(AdminError, match="alias"):
        owner.resources(cfg)


def test_all_five_explicit_shared_roles_fit_the_registry(controller):
    cfg, _, _, _ = controller
    file = cfg.private / "storage.toml"
    file.write_text(
        file.read_text()
        + "".join(
            f'\n[volumes.{role}]\nvolume="{role}-volume"\nlabel="omkality.project"\nowner="owned"\n'
            for role in ("content", "reports", "exports", "metrics")
        )
    )
    assert set(owner.shared(cfg)) == {
        "auth",
        "content",
        "reports",
        "exports",
        "metrics",
    }


def test_worker_uses_readonly_owned_volumes_without_docker_socket(
    controller, monkeypatch
):
    cfg, _, _, _ = controller
    values = owner.resources(cfg)
    result = {
        "schema": 1,
        "read_only": True,
        "resources": [{"id": v["id"], "role": v["role"]} for v in values],
    }
    docker = Mock(return_value=json.dumps({"ok": True, "result": result}))
    monkeypatch.setattr(owner.backups, "docker", docker)
    assert (
        real_worker(
            values, {"max_entries": 1000, "max_depth": 64}, owner.backups.settings({})
        )
        == result
    )
    args = docker.call_args.args
    assert args[0] == "run" and "--read-only" in args
    assert args[args.index("--network") + 1] == "none"
    assert args[args.index("--cap-drop") + 1] == "ALL"
    mounts = [args[i + 1] for i, a in enumerate(args) if a == "--mount"]
    assert all(",readonly" in m for m in mounts)
    assert all("volume-nocopy" in m for m in mounts if "type=volume" in m)
    assert not any("docker.sock" in a for a in args)


def test_worker_rejects_truncated_or_substituted_census(controller, monkeypatch):
    cfg, _, _, _ = controller
    values = owner.resources(cfg)
    monkeypatch.setattr(
        owner.backups,
        "docker",
        Mock(
            return_value=json.dumps(
                {
                    "ok": True,
                    "result": {"schema": 1, "read_only": True, "resources": []},
                }
            )
        ),
    )
    with pytest.raises(AdminError, match="differs"):
        real_worker(
            values, {"max_entries": 1000, "max_depth": 64}, owner.backups.settings({})
        )
