from contextlib import nullcontext
from types import SimpleNamespace

from omk.cli import main
from omk.owner.admin import AdminError
from omk.owner.panels import owner_world_reset as wipe


def test_cli_inspection_reports_unconfigured_fixture(monkeypatch, tmp_path, capsys):
    path = tmp_path / "operator.toml"
    path.write_text('schema=1\n[servers.sandbox]\nroot="sandbox"\n')
    monkeypatch.setattr(
        wipe,
        "load_operator_config",
        lambda _: SimpleNamespace(private=tmp_path, servers={"sandbox": tmp_path}),
    )
    assert (
        main(
            [
                "admin",
                "--config",
                str(path),
                "world-reset",
                "--server",
                "sandbox",
                "--command",
                "inspect",
            ]
        )
        == 0
    )
    assert '"stage": "unconfigured"' in capsys.readouterr().out
    assert sorted(p.name for p in tmp_path.iterdir()) == ["operator.toml"]


def test_mutations_require_current_server_and_stage_confirmation(monkeypatch):
    value = wipe.State(dimension=-18000, stage="prepare", target={"data_volume": "A"})
    monkeypatch.setattr(wipe, "load_operator_config", lambda _: object())
    monkeypatch.setattr(wipe, "_state", lambda *_: value)
    monkeypatch.setattr(wipe.backups, "locked", lambda _: nullcontext())

    def unexpected(*_args):
        raise AssertionError("Unconfirmed operation reached ingress or mutation")

    monkeypatch.setattr(wipe, "_require_drained", unexpected)
    monkeypatch.setattr(wipe, "_prepare", unexpected)
    valid = value.confirmation("dj2")
    for server, command, confirmation in (
        ("dj2", "prepare", ""),
        ("other", "prepare", valid),
        ("dj2", "apply", valid),
    ):
        result = wipe.run("operator.toml", server, command, confirmation)
        assert (result["ok"], result["effect"], result["error"]) == (
            False,
            "none",
            "state_changed",
        )
    value.target["data_volume"] = "B"
    assert (
        wipe.run("operator.toml", "dj2", "prepare", valid)["error"] == "state_changed"
    )


def test_confirmed_prepare_refuses_open_or_occupied_ingress_before_mutation(
    monkeypatch,
):
    state = wipe.State(dimension=-18000, stage="prepare")
    monkeypatch.setattr(wipe, "load_operator_config", lambda _: object())
    monkeypatch.setattr(wipe, "_state", lambda *_: state)
    monkeypatch.setattr(wipe.backups, "locked", lambda _: nullcontext())
    monkeypatch.setattr(wipe.ingress, "capture", lambda *a, **k: ({}, {"sessions": 1}))

    def unexpected(*args):
        raise AssertionError(args)

    monkeypatch.setattr(wipe, "_prepare", unexpected)
    result = wipe.run("operator.toml", "dj2", "prepare", state.confirmation("dj2"))
    assert (result["ok"], result["effect"], result["error"]) == (
        False,
        "none",
        "ingress_not_drained",
    )


def test_prepare_requires_successful_backup_before_staging(monkeypatch):
    state = wipe.State(
        dimension=-18000,
        stage="prepare",
        target={"data_volume": "owned-empty"},
        window={"operation": "a" * 32, "stage": "stopped"},
    )
    monkeypatch.setattr(wipe, "load_operator_config", lambda _: object())
    monkeypatch.setattr(wipe, "_state", lambda *_: state)
    monkeypatch.setattr(wipe.backups, "locked", lambda _: nullcontext())
    monkeypatch.setattr(wipe, "_require_drained", lambda *_: None)
    monkeypatch.setattr(wipe.owner_volumes, "destination", lambda *a, **k: {})
    monkeypatch.setattr(wipe.backups, "plan", lambda *a: {"operation": "b" * 32})

    def failed_backup(*_):
        raise AdminError("Backup failed")

    def never_stage(*args):
        raise AssertionError(args)

    monkeypatch.setattr(wipe.backups, "run", failed_backup)
    monkeypatch.setattr(wipe.staging, "plan", never_stage)
    result = wipe.run("operator.toml", "dj2", "prepare", state.confirmation("dj2"))
    assert result["ok"] is False and result["effect"] == "unknown"


def test_interrupted_write_requires_review_and_running_commit_does_not_restart():
    state = wipe.State(
        dimension=-18000,
        window={"operation": "a" * 32, "stage": "stopped"},
        resource={"operation": "c" * 32, "stage": "runtime-writing"},
    )
    assert wipe._phase(state) == "review"
    state.resource["stage"] = "runtime-ready"
    assert wipe._phase(state) == "apply"
    state.installation = {"operation": "d" * 32, "stage": "applying"}
    assert wipe._phase(state) == "review"
    state.installation["stage"] = "installed"
    state.window["stage"] = "start-requested"
    assert wipe._phase(state) == "review"
    state.window["stage"] = "complete"
    assert wipe._phase(state) == "start"
