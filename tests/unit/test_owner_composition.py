import json
import subprocess
import sys
import threading

import pytest

from omk import admin_backups as owner
from omk.admin import AdminError
from tests.unit.test_operator_commands import config


def test_nested_lock_and_exception_release_but_other_thread_cannot_enter(tmp_path):
    cfg, _ = config(tmp_path)
    errors = []

    def other():
        try:
            with owner.locked(cfg):
                errors.append("entered")
        except OSError:
            errors.append("blocked")

    with (
        pytest.raises(RuntimeError, match="fixture"),
        owner.locked(cfg),
        owner.locked(cfg),
    ):
        thread = threading.Thread(target=other)
        thread.start()
        thread.join(2)
        assert not thread.is_alive() and errors == ["blocked"]
        raise RuntimeError("fixture")
    with owner.locked(cfg):
        pass


def test_nested_owner_lock_does_not_release_outer_process_exclusion(tmp_path):
    cfg, _ = config(tmp_path)
    script = (
        "from pathlib import Path\nfrom types import SimpleNamespace\n"
        "from omk.admin_backups import locked\nimport sys\ntry:\n"
        " with locked(SimpleNamespace(private=Path(sys.argv[1]))):pass\n"
        "except OSError:sys.exit(7)\n"
    )
    with owner.locked(cfg):
        with owner.locked(cfg):
            pass
        result = subprocess.run(
            [sys.executable, "-c", script, str(cfg.private)],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        assert result.returncode == 7
    result = subprocess.run(
        [sys.executable, "-c", script, str(cfg.private)],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0


@pytest.mark.parametrize("value", ["", True, "bad", "../escape", "a" * 31])
def test_preallocated_operation_refuses_invalid_identity(tmp_path, value):
    cfg, _ = config(tmp_path)
    with pytest.raises(AdminError):
        owner.planned_id(cfg, "maintenance", value)


def test_preallocated_identity_never_overwrites_existing_metadata(tmp_path):
    cfg, _ = config(tmp_path)
    operation = "a" * 32
    assert owner.planned_id(cfg, "maintenance", operation) == operation
    folder = cfg.private / "maintenance"
    folder.mkdir()
    file = folder / (operation + ".json")
    file.write_text("fixture")
    with pytest.raises(AdminError, match="already exists"):
        owner.planned_id(cfg, "maintenance", operation)
    assert file.read_text() == "fixture"


@pytest.mark.parametrize("action", ["list", "inspect", "prepare"])
def test_backup_inspection_mount_is_read_only_without_changing_write_steps(
    monkeypatch, action
):
    calls = []
    monkeypatch.setattr(owner, "volume", lambda *a, **kw: {})

    def docker(*args, **kw):
        calls.append((args, kw))
        return json.dumps({"ok": True, "history": []})

    monkeypatch.setattr(owner, "docker", docker)
    owner.worker(
        {"store_volume": "store", "data_volume": "source"},
        {"action": action, "operation": "a" * 32, "settings": owner.settings({})},
    )
    args, _kw = calls[0]
    store = [
        v
        for v in args
        if isinstance(v, str) and v.startswith("type=volume,source=store,")
    ]
    assert len(store) == 1 and store[0].endswith(",readonly") == (
        action in {"list", "inspect"}
    )
    assert "--network" in args and args[args.index("--network") + 1] == "none"
