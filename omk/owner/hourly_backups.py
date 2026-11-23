"""Owner-only live world backup service and restricted offsite export."""

import argparse
import contextlib
import json
import os
import re
import shutil
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from omk.backups.backup_archive import MAX_MANIFEST_BYTES, regular_file
from omk.backups.backup_store import BackupPolicy, BackupStore, _json_read, _lock
from omk.backups.stopped_world_backup import inventory
from omk.deployment import ingress
from omk.labs.recovery.recovery_console import BACKUP_CHAT, command, online_players
from omk.owner import (
    admin_backups as backups,
    admin_maintenance as maintenance,
)
from omk.owner.admin import AdminError, _read_json, _write_private, load_operator_config
from omk.owner.hourly_backup_schedule import (
    HOUR,
    MOSCOW,
    daily_due,
    had_players,
    hour_end,
)
from omk.shared.fs import resolved

GIB = 1024**3
RETENTION = 6
POLICY = BackupPolicy(48 * GIB, RETENTION, 17 * GIB, 16 * GIB)
WORLD_MAX = 16 * GIB
SNAPSHOT = r"snapshot-[a-f0-9]{32}"
SHA256 = r"[a-f0-9]{64}"
STAGES = {
    "checking": "Проверяем состояние сервера",
    "idle": "Пропущено — за прошедший час никто не играл",
    "duplicate": "Копия за этот час уже готова",
    "offline": "Пропущено — Minecraft остановлен",
    "saving": "Сохраняем мир в Minecraft",
    "copying": "Копируем файлы мира",
    "verifying": "Проверяем содержимое архива",
    "publishing": "Сохраняем проверенный архив",
    "complete": "Копия на VPS готова",
    "failed": "Сбой при резервном копировании",
}
TRANSFER = {
    "copying": "Передача на Windows",
    "complete": "Копия на Windows проверена",
    "failed": "Сбой при передаче на Windows",
}
LOCAL_PATH = r"F:\omkalitycraft_backup"


class WorldChanged(ValueError):
    """The live source changed before the archive reached publication."""


def _stamp():
    return datetime.now(UTC).isoformat(timespec="seconds")


def _path(config, server):
    if server not in config.servers:
        raise AdminError("Unknown backup server")
    return config.private / "hourly-backups" / server


def _read(config, path):
    return _read_json(path, config.private) if path.exists() else {}


def _write(config, path, stage, **details):
    _write_private(path, config.private, {"stage": stage, "time": _stamp(), **details})


def _store(folder, *, create=False):
    root = folder / "store"
    options = {"path_policy": "linux-server", "max_expanded_bytes": WORLD_MAX}
    if create and not root.exists():
        return BackupStore.create(root, POLICY, **options)
    return BackupStore(root, POLICY, **options)


def _world_path(target):
    rows = json.loads(backups.docker("volume", "inspect", target["data_volume"]))
    mount = Path(rows[0]["Mountpoint"])
    if len(rows) != 1 or not mount.is_absolute() or resolved(mount) != mount:
        raise AdminError("Backup source mount is unavailable")
    return mount / target["world"]


def _package(world, folder, stage, verify_source):
    options = {
        "world_name": world.name,
        "max_expanded_bytes": WORLD_MAX,
        "path_policy": "linux-server",
    }
    files = inventory(world, **options)
    size = sum(row["bytes"] for row in files.values())
    required = size + 2 * MAX_MANIFEST_BYTES + len(files) * 2048
    if required > POLICY.staging_bytes or (
        shutil.disk_usage(folder).free < 2 * required + POLICY.reserve_bytes
    ):
        raise OSError("Недостаточно свободного места для копии")
    store = _store(folder, create=True)
    pending = folder / "incoming.zip"
    # An interrupted run may leave this one private staging file. The owner
    # lock is held throughout, and this file has never been published.
    if pending.exists() or pending.is_symlink():
        regular_file(pending)
        pending.unlink()
    stage("copying")
    try:
        with pending.open("xb") as output:
            pending.chmod(0o600)
            with zipfile.ZipFile(
                output, "w", zipfile.ZIP_DEFLATED, compresslevel=1
            ) as archive:
                for name in sorted(files):
                    archive.write(world.parent / name, name)
            output.flush()
            os.fsync(output.fileno())
        stage("verifying")
        if inventory(world, **options) != files:
            raise WorldChanged("World changed during archiving")
        verify_source()
        stage("publishing")
        return store.publish(pending, files)
    finally:
        pending.unlink(missing_ok=True)


def _notify(send, state):
    with contextlib.suppress(RuntimeError, OSError, ValueError):
        send(BACKUP_CHAT[state])


def _capture(send, world, folder, stage, verify_source):
    for attempt in (1, 2):
        stage("saving")
        flushed = send("save-all flush")
        if "Flushing completed" not in flushed or "Saved the world" not in flushed:
            raise AdminError("Minecraft did not confirm the world save")
        try:
            return _package(world, folder, stage, verify_source)
        except WorldChanged:
            if attempt == 2:
                raise
            verify_source()


def _scheduled_reason(when, latest, target, send):
    boundary = hour_end(when)
    if latest.get("slot") == boundary.isoformat():
        return "duplicate"
    if daily_due(when, latest):
        return "daily"
    online = online_players(send("list uuids")).values()
    log = backups.docker(
        "logs",
        "--timestamps",
        "--since",
        (boundary - HOUR).isoformat(),
        "--until",
        datetime.now(UTC).isoformat(),
        target["container"],
    )
    return "activity" if had_players(boundary, log, online) else "idle"


def run(config, server):
    """Back up each played hour and guarantee one copy per Moscow day."""
    folder = _path(config, server)
    status = folder / "run.json"
    last = folder / "latest.json"
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    checkpoint = "checking"
    send = None
    announced = False

    def stage(value):
        nonlocal checkpoint
        checkpoint = value
        _write(config, status, value)

    try:
        with backups.locked(config):
            stage("checking")
            ingress.operations_clear(config, server)
            backups.local_engine()
            target = backups.target_for(config, server)
            binding = maintenance.binding(config, server)
            identity = maintenance.snapshot(target, binding)
            if not identity["running"]:
                stage("offline")
                return
            endpoint, password = maintenance.credential(config, server)

            def send(text):
                return command(
                    endpoint,
                    password,
                    text,
                    timeout=30 if text == "save-all flush" else 8,
                )

            now = datetime.now(UTC)
            reason = _scheduled_reason(now, _read(config, last), target, send)
            if reason in ("idle", "duplicate"):
                stage(reason)
                return
            _notify(send, "started")
            announced = True
            world = _world_path(target)

            def verify_source():
                if maintenance.snapshot(target, binding) != identity:
                    raise AdminError("Minecraft перезапущен во время копирования")

            result = _capture(send, world, folder, stage, verify_source)
            _write(
                config,
                last,
                "complete",
                snapshot=result["id"],
                slot=hour_end(now).isoformat(),
                reason=reason,
            )
            stage("complete")
    except (OSError, RuntimeError, ValueError, KeyError) as error:
        if not isinstance(error, backups.OwnerBusy):
            _write(config, status, "failed", step=checkpoint)
        if announced:
            _notify(send, "failed")
        print(
            f"Hourly world backup failed during {checkpoint} ({type(error).__name__})",
            file=sys.stderr,
        )
        return False
    if announced:
        _notify(send, "complete")
    return True


def _exports(folder):
    root = folder / "store"
    if not root.exists():
        return []
    store = _store(folder)
    result = []
    with _lock(store.root, read_only=True):
        for entry in store.root.iterdir():
            if not re.fullmatch(SNAPSHOT, entry.name) or entry.is_symlink():
                continue
            marker = entry / "manifest.json"
            manifest = _json_read(marker)
            size = regular_file(entry / "archive.zip")
            if manifest["bytes"] != size or not re.fullmatch(
                SHA256, manifest["sha256"]
            ):
                raise ValueError("Invalid hourly backup manifest")
            result.append(
                {
                    "snapshot": entry.name,
                    "time": datetime.fromtimestamp(
                        marker.stat().st_mtime, UTC
                    ).isoformat(timespec="seconds"),
                    "sequence": manifest["sequence"],
                    "bytes": size,
                    "sha256": manifest["sha256"],
                }
            )
    return sorted(result, key=lambda row: row["sequence"])


def export(config, server, request, output):
    """Expose only the hourly snapshots and fixed acknowledgments to the sync key."""
    verb, _, argument = request.partition(" ")
    if request == "list":
        output.write((json.dumps(_exports(_path(config, server))) + "\n").encode())
        return
    snapshot, _, digest = argument.partition(" ")
    if verb not in {"get", *TRANSFER} or not re.fullmatch(SNAPSHOT, snapshot):
        raise ValueError("Unsupported backup sync request")
    folder = _path(config, server)
    rows = {row["snapshot"]: row for row in _exports(folder)}
    if snapshot not in rows:
        raise ValueError("Snapshot is no longer retained")
    if verb == "get" and not digest:
        with (folder / "store" / snapshot / "archive.zip").open("rb") as stream:
            shutil.copyfileobj(stream, output, length=1024**2)
    elif verb in TRANSFER and digest == rows[snapshot]["sha256"]:
        _write(config, folder / "transfer.json", verb, snapshot=snapshot)
        if verb == "complete":
            _write(config, folder / "received.json", verb, snapshot=snapshot)
    else:
        raise ValueError("Invalid backup transfer receipt")


def _moscow(value):
    return (
        datetime.fromisoformat(value).astimezone(MOSCOW).strftime("%d.%m.%Y %H:%M МСК")
    )


def overview(config, server):
    """Show current, last successful server and last verified local backup state."""
    folder = _path(config, server)
    if not folder.is_dir():
        return "Почасовые копии для этого сервера ещё не настроены."
    status = _read(config, folder / "run.json")
    latest = _read(config, folder / "latest.json")
    transfer = _read(config, folder / "transfer.json")
    received = _read(config, folder / "received.json")
    lines = [
        "Резервные копии мира",
        "После каждого часа с игроками. Ежедневная копия к 04:00 МСК.",
        "",
    ]
    if status:
        stage = STAGES[status["stage"]]
        if status["stage"] == "failed":
            stage += " · " + STAGES[status["step"]]
        lines.append(_moscow(status["time"]) + "  " + stage)
    if latest:
        kind = {"daily": "Ежедневная", "activity": "После игровой активности"}
        lines += [
            "Последняя копия на VPS · " + _moscow(latest["time"]),
            *([kind[latest["reason"]]] if latest.get("reason") in kind else []),
            str(folder / "store" / latest["snapshot"] / "archive.zip"),
        ]
    lines.append("")
    if transfer:
        lines.append(_moscow(transfer["time"]) + "  " + TRANSFER[transfer["stage"]])
    if received:
        lines += [
            "Последняя копия на Windows · " + _moscow(received["time"]),
            LOCAL_PATH
            + "\\"
            + server
            + "\\hourly\\"
            + received["snapshot"]
            + "\\archive.zip",
        ]
    else:
        lines += [
            "Ожидаем первую почасовую копию на Windows",
            LOCAL_PATH + "\\" + server + "\\hourly",
        ]
    return "\n".join(lines)


def main():
    """Serve the hourly systemd unit or one request from the forced SSH command."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--server", required=True)
    parser.add_argument("action", choices=("run", "export"))
    args = parser.parse_args()
    config = load_operator_config(args.config)
    if args.action == "run":
        return int(run(config, args.server) is False)
    raw = sys.stdin.readline(192)
    if not raw.endswith("\n") or sys.stdin.read(1):
        return 2
    try:
        export(config, args.server, raw.removesuffix("\n"), sys.stdout.buffer)
    except ValueError, RuntimeError, OSError, KeyError:
        print("Backup sync request could not be completed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
