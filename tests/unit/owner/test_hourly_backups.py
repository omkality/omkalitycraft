import io
import json
import time
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


@pytest.mark.parametrize(
    ("online", "flush_confirmed"),
    [(False, True), (True, True), (True, False)],
)
def test_hourly_backup_only_for_players_and_exports_verified_archive(
    tmp_path, monkeypatch, online, flush_confirmed
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
            "save-all flush": (
                "Saving...Flushing completedSaved the world" if flush_confirmed else ""
            ),
        }.get(text, "")

    monkeypatch.setattr(hourly, "command", send)
    before = time.time()
    succeeded = hourly.run(settings, "dj2")
    after = time.time()
    windows = hourly.capture_windows(settings, "dj2")
    listed = io.BytesIO()
    hourly.export(settings, "dj2", "list", listed)
    rows = json.loads(listed.getvalue())
    if not online:
        assert succeeded is None and windows is None
        assert rows == []
        assert requests == ["list uuids"]
        assert "за прошедший час никто не играл" in hourly.overview(settings, "dj2")
        return

    [[started, finished]] = windows
    assert before <= started < finished <= after
    if not flush_confirmed:
        assert succeeded is False
        assert rows == []
        assert requests == [
            "list uuids",
            hourly.BACKUP_CHAT["started"],
            "save-all flush",
            hourly.BACKUP_CHAT["failed"],
        ]
        return

    assert succeeded is True
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


def test_changes_during_snapshot_cannot_publish_or_replace_an_existing_copy(
    tmp_path, monkeypatch
):
    world, folder = tmp_path / "test-world", tmp_path / "backups"
    world.mkdir()
    folder.mkdir()
    (world / "level.dat").write_bytes(b"initial world")
    monkeypatch.setattr(hourly, "POLICY", replace(hourly.POLICY, reserve_bytes=1))
    proof = hourly._package(world, folder, lambda _stage: None, lambda: None)

    capture_file = hourly._copy_snapshot_file

    def copy_and_mutate(source, destination, record):
        capture_file(source, destination, record)
        (world / "level.dat").write_bytes(b"partially written world")

    monkeypatch.setattr(hourly, "_copy_snapshot_file", copy_and_mutate)
    with pytest.raises(hourly.WorldChanged):
        hourly._package(world, folder, lambda _stage: None, lambda: None)
    assert [row["snapshot"] for row in hourly._exports(folder)] == [proof["id"]]
    assert not (folder / "incoming.zip").exists()
    assert not (folder / "snapshot-input").exists()


def test_live_world_can_change_while_its_snapshot_is_being_compressed(
    tmp_path, monkeypatch
):
    world = tmp_path / "test-world"
    world.mkdir()
    folder = tmp_path / "backups"
    folder.mkdir()
    (world / "level.dat").write_bytes(b"saved level")
    region = world / "DIM-1/region/r.0.0.mca"
    region.parent.mkdir(parents=True)
    region.write_bytes(b"saved Nether region")
    monkeypatch.setattr(hourly, "POLICY", replace(hourly.POLICY, reserve_bytes=1))
    old_stage = folder / "snapshot-input"
    old_stage.mkdir()
    (old_stage / "interrupted-copy").touch()
    zip_write = zipfile.ZipFile.write

    def write_while_playing(archive, source, name):
        assert source.is_relative_to(old_stage)
        region.write_bytes(b"new activity in Nether")
        return zip_write(archive, source, name)

    monkeypatch.setattr(zipfile.ZipFile, "write", write_while_playing)
    result = hourly._package(world, folder, lambda _stage: None, lambda: None)
    published = folder / "store" / result["id"] / "archive.zip"
    with zipfile.ZipFile(published) as archive:
        assert (
            archive.read("test-world/DIM-1/region/r.0.0.mca") == b"saved Nether region"
        )
    assert region.read_bytes() == b"new activity in Nether"
    assert not old_stage.exists()


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
    capture_file = hourly._copy_snapshot_file
    attempts = 0

    def copy_and_save(source, destination, record):
        nonlocal attempts
        attempts += 1
        capture_file(source, destination, record)
        if attempts <= 2:
            level.write_bytes(f"server save {attempts}".encode())

    def stage(value):
        stages.append(value)

    monkeypatch.setattr(hourly, "_copy_snapshot_file", copy_and_save)

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
