import io
import json
import zipfile
from contextlib import contextmanager
from dataclasses import replace
from types import SimpleNamespace

import pytest

from omk.owner import hourly_backups as hourly
from tests.fixtures.unit.owner.operator_commands import config

ONLINE = (
    "There are 1/20 players online: TestPlayer (11111111-1111-1111-1111-111111111111)"
)


@pytest.mark.parametrize("online", (False, True))
def test_hourly_backup_only_for_players_and_exports_verified_archive(
    tmp_path, monkeypatch, online
):
    settings, _ = config(tmp_path)
    world = tmp_path / "test-world"
    world.mkdir()
    (world / "level.dat").write_bytes(b"world fixture")
    for module, name, value in (
        (hourly.ingress, "operations_clear", None),
        (hourly.backups, "local_engine", None),
        (hourly.backups, "target_for", {"container": "synthetic"}),
        (hourly.backups, "docker", ""),
        (hourly.maintenance, "binding", {}),
        (hourly.maintenance, "snapshot", {"running": True}),
        (hourly.maintenance, "credential", ("local", "test")),
        (hourly, "_world_path", world),
    ):
        monkeypatch.setattr(module, name, lambda *a, value=value: value)
    monkeypatch.setattr(hourly, "POLICY", replace(hourly.POLICY, reserve_bytes=1))
    monkeypatch.setattr(hourly, "daily_due", lambda *args: False)
    requests = []

    def send(_endpoint, _password, text, **_options):
        requests.append(text)
        return {
            "list uuids": ONLINE if online else "There are 0/20 players online:",
            "save-all flush": "Saving...Flushing completedSaved the world",
        }.get(text, "")

    monkeypatch.setattr(hourly, "command", send)
    assert hourly.run(settings, "dj2") is not False
    listed = io.BytesIO()
    hourly.export(settings, "dj2", "list", listed)
    rows = json.loads(listed.getvalue())
    if not online:
        assert rows == []
        assert requests == ["list uuids"]
        assert "за прошедший час никто не играл" in hourly.overview(settings, "dj2")
        return

    assert requests == [
        "list uuids",
        hourly.BACKUP_CHAT["started"],
        "save-all flush",
        hourly.BACKUP_CHAT["complete"],
    ]
    [row] = rows
    received = io.BytesIO()
    hourly.export(settings, "dj2", "get " + row["snapshot"], received)
    with zipfile.ZipFile(received) as archive:
        assert archive.read("test-world/level.dat") == b"world fixture"
    with pytest.raises(ValueError):
        hourly.export(
            settings, "dj2", "complete " + row["snapshot"] + " invalid", received
        )
    hourly.export(
        settings, "dj2", "complete " + row["snapshot"] + " " + row["sha256"], received
    )
    status = hourly.overview(settings, "dj2")
    assert "Копия на Windows проверена" in status and row["snapshot"] in status
    with pytest.raises(ValueError):
        hourly.export(settings, "dj2", "get ../../auth.json", received)


def test_changing_live_world_cannot_publish_or_replace_a_existing_copy(
    tmp_path, monkeypatch
):
    world, folder = tmp_path / "test-world", tmp_path / "backups"
    world.mkdir()
    folder.mkdir()
    (world / "level.dat").write_bytes(b"initial world")
    monkeypatch.setattr(hourly, "POLICY", replace(hourly.POLICY, reserve_bytes=1))
    proof = hourly._package(world, folder, lambda _stage: None, lambda: None)

    def mutate(stage):
        if stage == "verifying":
            (world / "level.dat").write_bytes(b"partially written world")

    with pytest.raises(hourly.WorldChanged):
        hourly._package(world, folder, mutate, lambda: None)
    assert [row["snapshot"] for row in hourly._exports(folder)] == [proof["id"]]
    assert not (folder / "incoming.zip").exists()


def test_transient_world_changes_wait_for_a_stable_verified_archive(
    tmp_path, monkeypatch
):
    world, folder = tmp_path / "test-world", tmp_path / "backups"
    world.mkdir()
    folder.mkdir()
    level = world / "level.dat"
    level.write_bytes(b"initial")
    monkeypatch.setattr(hourly, "POLICY", replace(hourly.POLICY, reserve_bytes=1))
    delays = []
    monkeypatch.setattr(hourly.time, "sleep", delays.append)
    stages = []

    def stage(value):
        stages.append(value)
        if value == "verifying" and stages.count("verifying") <= 2:
            level.write_bytes(f"server save {stages.count('verifying')}".encode())

    def send(text):
        assert text == "save-all flush"
        return "Saving...Flushing completedSaved the world"

    result = hourly._capture(send, world, folder, stage, lambda: None)
    assert delays == [5, 15]
    assert stages.count("retrying") == 2
    assert stages.count("saving") == 3
    assert stages.count("publishing") == 1
    archived = folder / "store" / result["id"] / "archive.zip"
    with zipfile.ZipFile(archived) as archive:
        assert archive.read("test-world/level.dat") == b"server save 2"
    assert not (folder / "incoming.zip").exists()


@pytest.mark.parametrize("release_after_wait", (True, False))
def test_scheduled_backup_waits_for_owner_operation(monkeypatch, release_after_wait):
    events = []
    current_time = 0

    def pause(seconds):
        nonlocal current_time
        current_time += seconds
        events.append("waiting")

    @contextmanager
    def lock(_config):
        if not release_after_wait or not current_time:
            raise hourly.backups.OwnerBusy()
        events.append("acquired")
        try:
            yield
        finally:
            events.append("released")

    monkeypatch.setattr(hourly, "OWNER_LOCK_WAIT", 5)
    monkeypatch.setattr(
        hourly, "time", SimpleNamespace(monotonic=lambda: current_time, sleep=pause)
    )
    monkeypatch.setattr(hourly.backups, "locked", lock)
    if release_after_wait:
        with hourly._wait_for_owner_lock(None):
            events.append("running")
        assert events == ["waiting", "acquired", "running", "released"]
    else:
        with pytest.raises(hourly.backups.OwnerBusy), hourly._wait_for_owner_lock(None):
            pytest.fail("A backup must not start while the owner lock is held")
        assert events == ["waiting"]
