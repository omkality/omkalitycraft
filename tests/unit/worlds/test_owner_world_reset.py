import json
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from omk.cli import main
from omk.owner.admin import AdminError, _write_private
from omk.owner.panels import owner_world_reset as wipe
from omk.owner.panels.owner_volumes import reset_target
from tests.fixtures.unit.owner.operator_commands import config


def test_repeated_resets_use_distinct_destinations_bound_to_the_window():
    template = {"data_volume": "reset", "owner": "dj2"}
    a, b = (reset_target(template, character * 32) for character in ("a", "b"))
    assert a["data_volume"] == "reset-" + "a" * 32
    assert b["data_volume"] == "reset-" + "b" * 32
    assert a["owner"] == b["owner"] == template["owner"]


def test_managed_wipe_finishes_before_opening_ingress(monkeypatch):
    state = wipe.State(dimension=0, stage="start", managed=True)
    events = []
    monkeypatch.setattr(wipe, "_require_drained", lambda *_: None)
    monkeypatch.setattr(wipe, "_start", lambda *_: events.append("start"))
    monkeypatch.setattr(
        wipe, "_set_ingress", lambda _, server, action: events.append(action)
    )
    result = {}
    assert wipe._execute_stage(None, "dj2", "start", state, result)
    assert events == ["start", "open"]
    assert result["stage"] == "complete"


@pytest.mark.parametrize("invalid_history", [False, True])
def test_one_confirmation_runs_prepare_apply_and_start_in_order(
    monkeypatch, tmp_path, capsys, invalid_history
):
    settings, path = config(tmp_path)
    ticks = iter([100.5, 226.25])
    monkeypatch.setattr(wipe, "time", SimpleNamespace(time=lambda: next(ticks)))
    sequence = [
        wipe.State(dimension=0, stage=stage, managed=True)
        for stage in ("prepare", "apply", "start")
    ]
    performed = []
    monkeypatch.setattr(wipe, "_catalog", lambda *_: {})
    monkeypatch.setattr(wipe, "_selected_state", lambda *_: sequence[len(performed)])
    monkeypatch.setattr(
        wipe,
        "_execute_stage",
        lambda _config, _server, action, state, _result: (
            performed.append((action, state.stage)) or True
        ),
    )
    history = settings.private / "world-reset/dj2/capture-windows.json"
    assert not wipe.run(path, "dj2", "run", "wrong", catalog=True)["ok"]
    assert not history.exists()
    if invalid_history:
        _write_private(history, settings.private, {"schema": 9, "windows": []})
    result = wipe.run(path, "dj2", "run", sequence[0].confirmation("dj2"), catalog=True)
    assert performed == [(x, x) for x in ("prepare", "apply", "start")]
    assert result["ok"] and result["stage"] == "complete"
    if invalid_history:
        assert json.loads(history.read_bytes()) == {"schema": 9, "windows": []}
        assert "Could not record world reset timing" in capsys.readouterr().err
    else:
        assert json.loads(history.read_bytes()) == {
            "schema": 1,
            "windows": [[100.5, 226.25]],
        }


def test_wipe_closes_ingress_before_kicking_players(monkeypatch):
    events = []
    states = iter(
        [({}, {"closed": False, "sessions": 3}), ({}, {"closed": True, "sessions": 0})]
    )
    monkeypatch.setattr(wipe.ingress, "capture", lambda *_args, **_kwargs: next(states))
    monkeypatch.setattr(
        wipe, "_set_ingress", lambda *args, reason: events.append(("close", reason))
    )
    monkeypatch.setattr(
        wipe.owner_moderation,
        "kick_for_maintenance",
        lambda *args: events.append(("kick", args[-1])),
    )
    result = {
        "dimension": -18000,
        "worlds": [{"name": "Ресурсный мир", "dimension": -18000}],
    }
    progress = []
    token = wipe._progress.set(progress.append)
    try:
        wipe._close_and_drain(None, "dj2", result)
    finally:
        wipe._progress.reset(token)
    assert events == [
        ("close", "wipe:Ресурсный мир"),
        ("kick", "Сервер временно недоступен. Идёт вайп мира «Ресурсный мир»."),
    ]
    assert progress == ["closing", "disconnecting", "drained"]
    assert result["effect"] == "unknown"


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
    tmp_path,
):
    state = wipe.State(dimension=-18000, stage="prepare")
    settings, path = config(tmp_path)
    ticks = iter([100.5, 103.25])
    monkeypatch.setattr(wipe, "time", SimpleNamespace(time=lambda: next(ticks)))
    monkeypatch.setattr(wipe, "_state", lambda *_, **__: state)
    monkeypatch.setattr(wipe.backups, "locked", lambda _: nullcontext())
    monkeypatch.setattr(wipe.ingress, "capture", lambda *a, **k: ({}, {"sessions": 1}))

    def unexpected(*args):
        raise AssertionError(args)

    monkeypatch.setattr(wipe, "_prepare", unexpected)
    result = wipe.run(path, "dj2", "prepare", state.confirmation("dj2"))
    assert (result["ok"], result["effect"], result["error"]) == (
        False,
        "none",
        "ingress_not_drained",
    )
    history = settings.private / "world-reset/dj2/capture-windows.json"
    assert json.loads(history.read_bytes())["windows"] == [[100.5, 103.25]]


def test_prepare_requires_successful_backup_before_staging(monkeypatch, tmp_path):
    state = wipe.State(
        dimension=-18000,
        stage="prepare",
        target={"data_volume": "owned-empty"},
        window={"operation": "a" * 32, "stage": "stopped"},
    )
    _, path = config(tmp_path)
    monkeypatch.setattr(wipe, "_state", lambda *_, **__: state)
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
    result = wipe.run(path, "dj2", "prepare", state.confirmation("dj2"))
    assert result["ok"] is False and result["effect"] == "unknown"
    assert "AdminError: Backup failed" in result["diagnostic"]
    assert "test_owner_world_reset.py:" in result["diagnostic"]
    assert str(result["confirmation"]) not in result["diagnostic"]


def test_diagnostic_omits_subprocess_arguments_and_output():
    from subprocess import CalledProcessError  # noqa: PLC0415

    error = CalledProcessError(1, ["synthetic-private-input"], stderr="private-output")
    detail = wipe._diagnostic(error)
    assert detail.endswith("CalledProcessError")
    assert "private" not in detail


@pytest.mark.parametrize(
    ("reason", "summary"),
    [
        ("world_links", "В сохранениях есть привязки"),
        ("opaque_records", "Формат части файлов"),
        ("no_landing", "безопасная точка"),
        ("private/world/playerdata.dat", None),
    ],
)
def test_only_reviewed_plan_refusals_reach_the_wipe_summary(
    monkeypatch, tmp_path, reason, summary
):
    state = wipe.State(dimension=-18000, stage="prepare", managed=True)
    record = {
        "operation": "a" * 32,
        "source": {"data_volume": "source", "store_volume": "backup", "world": "world"},
        "target": {"data_volume": "candidate"},
        "dimension": state.dimension,
        "settings": wipe.backups.settings({}),
        "snapshot": "snapshot-" + "b" * 32,
        "preflight_options": {},
    }
    apply = Mock(side_effect=AssertionError("Plan refusal reached installation"))
    monkeypatch.setattr(wipe, "_apply", apply)
    _, path = config(tmp_path)
    monkeypatch.setattr(wipe, "_state", lambda *_, **__: state)
    monkeypatch.setattr(wipe.backups, "locked", lambda _: nullcontext())
    monkeypatch.setattr(wipe, "_close_and_drain", lambda *_: None)
    monkeypatch.setattr(wipe, "_require_drained", lambda *_: None)
    monkeypatch.setattr(
        wipe, "_prepare", lambda *_: wipe.staging.worker(record, "plan")
    )
    monkeypatch.setattr(wipe.backups, "volume", lambda *a: {})
    monkeypatch.setattr(wipe.owner_volumes, "destination", lambda *a, **k: {})
    monkeypatch.setattr(
        wipe.backups,
        "docker",
        lambda *a, **k: json.dumps(
            {"ok": False, "error_type": "PreflightRefused", "reason": reason}
        ),
    )
    result = wipe.run(path, "dj2", "run", state.confirmation("dj2"))
    assert not result["ok"] and result["error"] == "operation_rejected"
    assert result["stage"] == "prepare" and result["effect"] == "unknown"
    first_line = result["diagnostic"].splitlines()[0]
    if summary is None:
        assert not first_line.startswith("Summary: ")
        assert reason not in result["diagnostic"]
    else:
        assert first_line.startswith("Summary: Вайп остановлен. ")
        assert summary in first_line
    apply.assert_not_called()


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


def test_catalog_selects_by_dimension_without_authorizing_other_worlds(
    monkeypatch, tmp_path
):
    worlds = [
        {"dimension": -18000, "name": "Ресурсы", "description": "Добыча ресурсов"},
        {"dimension": 0, "name": "Основной мир", "description": "Общий мир игроков"},
    ]
    state = wipe.State(
        dimension=-18000, stage="prepare", target={"data_volume": "owned"}
    )
    (tmp_path / "world-catalog.json").write_text("{}")
    monkeypatch.setattr(
        wipe,
        "load_operator_config",
        lambda _: SimpleNamespace(private=tmp_path, servers={"dj2": tmp_path}),
    )
    monkeypatch.setattr(
        wipe, "_read_json", lambda *_: {"schema": 1, "servers": {"dj2": worlds}}
    )
    monkeypatch.setattr(wipe, "_state", lambda *_, **__: state)
    monkeypatch.setattr(wipe.backups, "locked", lambda _: nullcontext())

    def never_apply(*_):
        raise AssertionError("An unconfirmed world must not reach mutation")

    monkeypatch.setattr(wipe, "_require_drained", never_apply)
    inspection = wipe.run("operator.toml", "dj2", "inspect", "", catalog=True)
    assert inspection["worlds"] == worlds
    assert inspection["confirmation"] == state.confirmation("dj2", world=worlds[0])
    overworld = wipe.run(
        "operator.toml", "dj2", "inspect", "", catalog=True, dimension=0
    )
    assert (overworld["dimension"], overworld["stage"], overworld["confirmation"]) == (
        0,
        "unsupported",
        None,
    )
    old_token = inspection["confirmation"]
    for dimension in (0, 1):
        result = wipe.run(
            "operator.toml",
            "dj2",
            "prepare",
            old_token,
            catalog=True,
            dimension=dimension,
        )
        assert not result["ok"] and result["effect"] == "none"
    worlds[0]["name"] = "Новая подпись ресурсов"
    renamed = wipe.run(
        "operator.toml", "dj2", "prepare", old_token, catalog=True, dimension=-18000
    )
    assert renamed["error"] == "state_changed"


def test_catalog_rejects_terminal_control_characters(monkeypatch, tmp_path):
    (tmp_path / "world-catalog.json").write_text("{}")
    monkeypatch.setattr(
        wipe,
        "load_operator_config",
        lambda _: SimpleNamespace(private=tmp_path, servers={"dj2": tmp_path}),
    )
    monkeypatch.setattr(
        wipe,
        "_read_json",
        lambda *_: {
            "schema": 1,
            "servers": {
                "dj2": [{"dimension": 0, "name": "bad\x1b", "description": "a"}]
            },
        },
    )
    result = wipe.run("operator.toml", "dj2", "inspect", "", catalog=True, dimension=0)
    assert result["error"] == "operation_rejected"
    assert result["effect"] == "none"


def test_discovered_world_is_visible_but_does_not_grant_reset_authority(monkeypatch):
    main = {"dimension": 0, "name": "Основной", "description": "Базы игроков"}
    dynamic = {"dimension": 60, "name": "Шахта", "description": "Мир RFTools"}
    configured = {0: main}
    context = object()
    current = wipe.State(dimension=0, stage="prepare", managed=True)
    discover = Mock(
        return_value={
            0: {**main, "name": "Collision"},
            60: {**dynamic, "rftools_identity": None},
        }
    )
    mutate = Mock(side_effect=AssertionError("Unexpected wipe"))
    monkeypatch.setattr(wipe, "load_operator_config", lambda _: context)
    monkeypatch.setattr(wipe, "_catalog", lambda *_: configured)

    def state(_config, _server, dimension=None, *, managed=False, rftools=None):
        return (
            wipe.State(dimension=dimension, stage="unsupported")
            if rftools is not None
            else current
        )

    monkeypatch.setattr(wipe, "_state", state)
    monkeypatch.setattr(wipe.backups, "locked", lambda _: nullcontext())
    monkeypatch.setattr(wipe, "discover_saved_worlds", discover)
    monkeypatch.setattr(wipe, "_execute_stage", mutate)

    initial = wipe.run("operator.toml", "dj2", "inspect", "", catalog=True)
    assert initial["ok"] and initial["worlds"] == [main, dynamic]
    selected = wipe.run(
        "operator.toml", "dj2", "inspect", "", catalog=True, dimension=60
    )
    assert selected["ok"] and selected["stage"] == "unsupported"
    assert selected["confirmation"] is None
    attempt = wipe.run(
        "operator.toml",
        "dj2",
        "run",
        initial["confirmation"],
        catalog=True,
        dimension=60,
    )
    assert not attempt["ok"] and attempt["effect"] == "none"
    mutate.assert_not_called()
    assert discover.call_count == 3


def test_rftools_confirmation_rechecks_the_saved_selection_before_wipe(monkeypatch):
    main = {"dimension": 0, "name": "Основной", "description": "Базы игроков"}
    entry = {
        "dimension": 6000,
        "name": "Шахта",
        "description": "Мир RFTools",
        "rftools_identity": "a" * 64,
    }
    mutate = Mock(side_effect=AssertionError("Stale confirmation reached a wipe"))
    monkeypatch.setattr(wipe, "load_operator_config", lambda _: object())
    monkeypatch.setattr(wipe, "_catalog", lambda *_: {0: main})
    monkeypatch.setattr(wipe.backups, "locked", lambda _: nullcontext())
    monkeypatch.setattr(wipe, "discover_saved_worlds", lambda *_: {6000: dict(entry)})

    def state(_config, _server, dimension, *, managed, rftools):
        assert managed
        return wipe.State(
            dimension=dimension,
            stage="prepare",
            managed=True,
            reset=wipe.layout(dimension, rftools_identity=rftools["rftools_identity"]),
        )

    monkeypatch.setattr(wipe, "_state", state)
    monkeypatch.setattr(wipe, "_execute_stage", mutate)
    selected = wipe.run(
        "operator.toml", "dj2", "inspect", "", catalog=True, dimension=6000
    )
    assert selected["confirmation"] and selected["stage"] == "prepare"
    assert selected["worlds"][-1] == {
        k: v for k, v in entry.items() if k != "rftools_identity"
    }
    entry["rftools_identity"] = "b" * 64
    rejected = wipe.run(
        "operator.toml",
        "dj2",
        "run",
        selected["confirmation"],
        catalog=True,
        dimension=6000,
    )
    assert rejected["error"] == "state_changed" and rejected["effect"] == "none"
    mutate.assert_not_called()


def test_rftools_restart_uses_the_sealed_cold_plan_after_the_seed_changes():
    dimension = 6000
    before = wipe.layout(dimension, rftools_identity="a" * 64)
    current = wipe.layout(dimension, rftools_identity="b" * 64)
    record = "d" * 32
    state = wipe.State(
        dimension=dimension,
        reset=current,
        resource={"operation": record, "dimension": dimension, "reset": before},
        installation={"resource_operation": record, "stage": "installed"},
    )
    assert wipe._installed_reset(state, {"rftools_identity": None}) == before
    state.installation["stage"] = "planned"
    assert wipe._installed_reset(state, {"rftools_identity": "b" * 64}) == current
    state.installation.update(stage="installed", resource_operation="e" * 32)
    assert wipe._installed_reset(state, {"rftools_identity": None}) == current


def test_unavailable_saved_catalog_keeps_the_configured_worlds(monkeypatch):
    main = {"dimension": 0, "name": "Основной", "description": "Базы игроков"}
    current = wipe.State(dimension=0, stage="prepare", managed=True)
    monkeypatch.setattr(wipe, "load_operator_config", lambda _: object())
    monkeypatch.setattr(wipe, "_catalog", lambda *_: {0: main})
    monkeypatch.setattr(wipe, "_state", lambda *_, **__: current)
    monkeypatch.setattr(
        wipe, "discover_saved_worlds", Mock(side_effect=AdminError("Source changed"))
    )
    result = wipe.run("operator.toml", "dj2", "inspect", "", catalog=True)
    assert result["ok"] and result["worlds"] == [main]
    assert result["confirmation"] == current.confirmation("dj2", world=main)
