import io
import json
import os
import subprocess
import sys
import time
import zipfile
from pathlib import Path

import pytest

from omk.diagnostics import (
    MIB,
    BoundedLog,
    collect_output,
    export_bundle,
    failure,
    prune_native_archives,
    prune_reports,
    redact,
)


def test_rotation_retains_recent_output_and_enforces_byte_budget(tmp_path):
    path = tmp_path / "game.log"
    log = BoundedLog(path, limit=256, copies=3)
    for index in range(100):
        log.write(f"{index:03d}: " + "я" * 45 + "\n")
    files = list(tmp_path.glob("game.log*"))
    assert len(files) == 3
    assert all(p.stat().st_size <= 256 for p in files)
    assert "099:" in path.read_text(encoding="utf-8")
    assert all("000:" not in p.read_text(encoding="utf-8") for p in files)
    # A legacy oversized log is rotated away within the same fixed file budget.
    path.write_bytes(b"x" * 2000)
    log.write("new\n")
    for _ in range(3):
        log.write("y" * 200 + "\n")
    assert all(p.stat().st_size <= 256 for p in files)


@pytest.mark.parametrize(
    "text",
    [
        "--accessToken old-secret",
        '{"accessToken": "old-secret", "password": "different-secret"}',
        "Authorization: Bearer old-secret",
        "https://auth.invalid/?invite=old-secret&password=different-secret",
        "Session ID is token:old-secret:uuid",
        "api_token=old-secret",
    ],
)
def test_unknown_credentials_are_removed_from_common_formats(text):
    result = redact(text)
    assert "old-secret" not in result and "different-secret" not in result


def test_collector_redacts_split_utf8_and_tokens_and_discards_huge_line(tmp_path):
    class TinyReads(io.BytesIO):
        def read1(self, _size):
            return self.read(3)

    path = tmp_path / "game.log"
    token = "standalone-game-token"
    raw = ("Привет " + token + "\n").encode() + b"x" * 100000 + b"\nlast\n"
    collect_output(TinyReads(raw), BoundedLog(path), (token,))
    value = path.read_text(encoding="utf-8")
    assert "Привет [redacted]" in value and token not in value
    assert "[overlong output line omitted]" in value and "last" in value
    assert len(value) < 200


def test_real_child_flood_is_drained_after_disk_failure():
    class BrokenLog:
        def write(self, _text):
            raise OSError("disk full")

    process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import sys; sys.stdout.buffer.write(b'x'*200+b'\\n'); "
            "sys.stdout.buffer.write((b'y'*100+b'\\n')*100000)",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    failures = []
    try:
        collect_output(
            process.stdout, BrokenLog(), on_error=lambda: failures.append(True)
        )
        assert process.wait(timeout=5) == 0
        assert failures == [True]
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()


def test_error_events_do_not_save_exception_secrets_or_source_lines(tmp_path):
    try:
        raise ValueError("password=should-never-appear")
    except ValueError as error:
        failure(tmp_path, "skin", error)
    raw = (tmp_path / "userdata/logs/launcher.jsonl").read_text(encoding="utf-8")
    value = json.loads(raw)
    assert value["error_type"] == "ValueError" and value["frames"]
    assert "should-never-appear" not in raw


def test_minecraft_colour_codes_do_not_break_plain_log_parsing():
    assert (
        redact("§eomk_game_test§r§e joined the game§r")
        == "omk_game_test joined the game"
    )


def test_escaped_json_credential_is_removed_as_a_whole():
    value = json.dumps({"password": 'a secret with "quotes" and \\ escapes'})
    assert "quotes" not in redact(value) and "escapes" not in redact(value)


def test_linked_log_output_is_rejected_without_touching_external_file(tmp_path):
    external = tmp_path / "outside"
    external.mkdir()
    sentinel = external / "game.log"
    sentinel.write_text("preserve")
    linked = tmp_path / "logs"
    if os.name == "nt":
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(linked), str(external)],
            capture_output=True,
            check=False,
        )
        if result.returncode:
            pytest.skip("Junction creation unavailable")
    else:
        linked.symlink_to(external, target_is_directory=True)
    with pytest.raises(OSError):
        BoundedLog(linked / "game.log").write("must not write")
    assert sentinel.read_text() == "preserve"


def test_bundle_uses_allowlist_redacts_tokens_paths_and_keeps_crash_cause(tmp_path):
    instance = tmp_path / "instances/dj2"
    logs = instance / "logs"
    logs.mkdir(parents=True)
    private = tmp_path / "userdata"
    private.mkdir()
    (private / "session.json").write_text(
        json.dumps({"access_token": "known-secret", "client_token": "known-client"})
    )
    (logs / "latest.log").write_text(
        f"{tmp_path} known-secret --accessToken old-secret\n", encoding="utf-8"
    )
    (logs / "private-notes.log").write_text("not-for-export")
    (instance / "server.properties").write_text("rcon.password=not-for-export")
    (instance / "world").mkdir()
    (instance / "world/level.dat").write_bytes(b"not-for-export")
    crash = instance / "crash-reports"
    crash.mkdir()
    (crash / "crash-test.txt").write_bytes(
        b"TOP exception and chunk location\n"
        + b"middle line\n" * 300000
        + b"LAST system info\n"
    )
    result = export_bundle(tmp_path, "dj2")
    with zipfile.ZipFile(result["archive"]) as archive:
        values = {n: archive.read(n).decode() for n in archive.namelist()}
        content = "\n".join(values.values())
        assert len(archive.read("crashes/crash-test.txt")) <= 2 * MIB
        assert "TOP exception" in content and "LAST system info" in content
        assert "known-secret" not in content and "old-secret" not in content
        assert str(tmp_path) not in content and "not-for-export" not in content
        assert "session.json" not in content and "[redacted]" in content
        assert json.loads(values["diagnostic.json"])["files"][0]["truncated"]
    assert not result["uploaded"]


def test_repeated_bundles_have_bounded_retention_and_preserve_other_files(tmp_path):
    for _ in range(7):
        result = export_bundle(tmp_path, "dj2")
        time.sleep(0.002)
    folder = Path(result["archive"]).parent
    assert len(list(folder.glob("diag-*.zip"))) == 5
    sentinel = folder / "my-own.zip"
    sentinel.write_bytes(b"keep")
    export_bundle(tmp_path, "dj2")
    assert sentinel.read_bytes() == b"keep"


def test_crash_and_native_cleanup_only_removes_old_allowlisted_files(tmp_path):
    crash = tmp_path / "crash-reports"
    crash.mkdir()
    for index in range(5):
        file = crash / f"crash-{index}.txt"
        file.write_bytes(b"x" * 100)
        os.utime(file, (100 + index, 100 + index))
    (crash / "notes.txt").write_text("keep")
    prune_reports(tmp_path, crash, count=2, budget=200)
    assert {p.name for p in crash.glob("crash-*.txt")} == {"crash-3.txt", "crash-4.txt"}
    assert (crash / "notes.txt").exists()
    for index in range(5):
        path = tmp_path / f"hs_err_pid{index}.log"
        path.write_bytes(b"x" * 100)
        os.utime(path, (100 + index, 100 + index))
    prune_reports(tmp_path, tmp_path, count=2, budget=200, jvm=True)
    assert {p.name for p in tmp_path.glob("hs_err_pid*.log")} == {
        "hs_err_pid3.log",
        "hs_err_pid4.log",
    }
    logs = tmp_path / "logs"
    logs.mkdir()
    for index in range(15):
        (logs / f"2026-10-30-{index}.log.gz").write_bytes(b"archive")
    (logs / "latest.log").write_text("active")
    (logs / "other.gz").write_text("keep")
    prune_native_archives(tmp_path, logs)
    assert len(list(logs.glob("2026-*.gz"))) == 12
    assert (logs / "latest.log").read_text() == "active"
    assert (logs / "other.gz").exists()


def test_explicit_server_bundle_is_read_only(tmp_path):
    server = tmp_path / "server"
    (server / "logs").mkdir(parents=True)
    (server / "logs/latest.log").write_text("server exception\n")
    before = (server / "logs/latest.log").stat().st_mtime_ns
    result = export_bundle(tmp_path / "portable", "dj2", server_root=server)
    with zipfile.ZipFile(result["archive"]) as archive:
        assert b"server exception" in archive.read("game/latest.log")
    assert (server / "logs/latest.log").stat().st_mtime_ns == before


@pytest.mark.parametrize("value", ["[]", "not json", '{"access_token": 42}'])
def test_corrupt_session_does_not_block_diagnostic_export(tmp_path, value):
    (tmp_path / "userdata").mkdir()
    (tmp_path / "userdata/session.json").write_text(value)
    assert export_bundle(tmp_path, "dj2")["ok"]


def test_linked_native_folder_is_not_exported(tmp_path):
    external = tmp_path / "external"
    external.mkdir()
    (external / "latest.log").write_text("outside-secret")
    root = tmp_path / "portable"
    instance = root / "instances/dj2"
    instance.mkdir(parents=True)
    target = instance / "logs"
    if os.name == "nt":
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(target), str(external)],
            capture_output=True,
            check=False,
        )
        if result.returncode:
            pytest.skip("Junction creation unavailable")
    else:
        target.symlink_to(external, target_is_directory=True)
    result = export_bundle(root, "dj2")
    with zipfile.ZipFile(result["archive"]) as archive:
        assert "game/latest.log" not in archive.namelist()
    assert (external / "latest.log").read_text() == "outside-secret"


@pytest.mark.parametrize("pack", ["../dj2", "DJ2", "dj2/other", "", "C:\\outside"])
def test_bundle_rejects_path_injection(tmp_path, pack):
    with pytest.raises(ValueError):
        export_bundle(tmp_path, pack)
