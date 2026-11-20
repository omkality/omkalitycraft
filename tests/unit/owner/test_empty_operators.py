import hashlib
import json
import os
from types import SimpleNamespace

import pytest

from omk.labs.recovery.recovery_console import ConsoleConfig, ConsoleError
from omk.owner.maintenance import maintenance_console, maintenance_worker


def actor(monkeypatch, response, calls=None):
    def command(config, password, text):
        if calls is not None:
            calls.append(text)
        return "OMK_MAINTENANCE_V1 " + json.dumps(response)

    monkeypatch.setattr(maintenance_console, "command", command)
    return maintenance_console.MaintenanceConsole(
        ConsoleConfig(25577, "fixture.json"), "fixture-password-12345"
    )


BASE = {"schema": 1, "boot": "a" * 32, "main_thread": True, "operator_count": 0}


def test_operator_probe_only_sends_the_fixed_readonly_request(monkeypatch):
    calls = []
    assert actor(monkeypatch, BASE, calls).no_operators(boot="a" * 32) == BASE
    assert calls == ["list omk-maintenance operators"]


@pytest.mark.parametrize(
    "change",
    [
        {"operator_count": 1},
        {"operator_count": True},
        {"operator_count": "0"},
        {"operator_count": -1},
        {"operator_count": 0.0},
        {"boot": "b" * 32},
        {"main_thread": False},
        {"schema": True},
        {"extra": []},
    ],
)
def test_unknown_nonzero_or_unbound_loaded_list_refuses(monkeypatch, change):
    with pytest.raises(ConsoleError):
        actor(monkeypatch, {**BASE, **change}).no_operators(boot="a" * 32)


def test_old_core_reply_does_not_prove_operators(monkeypatch):
    with pytest.raises(ConsoleError):
        actor(
            monkeypatch, {"schema": 1, "boot": "a" * 32, "main_thread": True}
        ).no_operators(boot="a" * 32)


@pytest.mark.parametrize("value", [None, "", "bad", 1, True])
def test_invalid_boot_refuses_before_transport(monkeypatch, value):
    calls = []
    with pytest.raises(ConsoleError):
        actor(monkeypatch, BASE, calls).no_operators(boot=value)
    assert calls == []


def test_empty_disk_list_is_readonly_and_hashes_exact_bytes(tmp_path):
    path = tmp_path / "ops.json"
    raw = b" [\r\n ]\r\n"
    path.write_bytes(raw)
    assert maintenance_worker.execute({"action": "operators"}, tmp_path) == {
        "operators_sha256": hashlib.sha256(raw).hexdigest(),
        "operator_count": 0,
    }
    assert path.read_bytes() == raw


def test_recreated_empty_disk_list_is_readonly(tmp_path):
    path = tmp_path / "ops.json"
    raw = b" [\r\n ]\r\n"
    for _ in range(3):
        path.write_bytes(raw)
        assert maintenance_worker.execute({"action": "operators"}, tmp_path) == {
            "operators_sha256": hashlib.sha256(raw).hexdigest(),
            "operator_count": 0,
        }
        assert path.read_bytes() == raw
        path.unlink()


def test_descriptor_ctime_change_during_read_is_refused(tmp_path, monkeypatch):
    path = tmp_path / "ops.json"
    path.write_bytes(b"[]")
    original = os.fstat
    calls = []

    def changed(fd):
        info = original(fd)
        calls.append(fd)
        values = {
            key: getattr(info, key)
            for key in (
                "st_dev",
                "st_ino",
                "st_mode",
                "st_nlink",
                "st_size",
                "st_mtime_ns",
                "st_ctime_ns",
            )
        }
        if len(calls) > 1:
            values["st_ctime_ns"] += 1
        return SimpleNamespace(**values)

    monkeypatch.setattr(os, "fstat", changed)
    with pytest.raises(ValueError, match="changed while reading"):
        maintenance_worker.execute({"action": "operators"}, tmp_path)
    assert path.read_bytes() == b"[]"


@pytest.mark.parametrize(
    "raw",
    [
        b"{}",
        b"null",
        b"false",
        b"0",
        b"[{}]",
        b"[1]",
        b"[",
        b"\xff",
        "[]".encode("utf-16"),
        b" " * 65537,
    ],
    ids=[
        "object",
        "null",
        "false",
        "number",
        "record",
        "array",
        "truncated",
        "encoding",
        "utf16",
        "oversized",
    ],
)
def test_bad_or_nonempty_disk_list_is_preserved(tmp_path, raw):
    path = tmp_path / "ops.json"
    path.write_bytes(raw)
    with pytest.raises((ValueError, UnicodeError)):
        maintenance_worker.execute({"action": "operators"}, tmp_path)
    assert path.read_bytes() == raw


def test_absent_disk_list_is_not_created(tmp_path):
    with pytest.raises(ValueError):
        maintenance_worker.execute({"action": "operators"}, tmp_path)
    assert not (tmp_path / "ops.json").exists()


def test_hardlinked_operator_file_is_refused(tmp_path):
    source = tmp_path / "source.json"
    source.write_bytes(b"[]")
    os.link(source, tmp_path / "ops.json")
    with pytest.raises(ValueError):
        maintenance_worker.execute({"action": "operators"}, tmp_path)
    assert source.read_bytes() == b"[]"


@pytest.mark.skipif(
    os.name == "nt", reason="POSIX symlink control; Windows needs privileges"
)
def test_linked_operator_file_is_refused(tmp_path):
    source = tmp_path / "source.json"
    source.write_bytes(b"[]")
    (tmp_path / "ops.json").symlink_to(source)
    with pytest.raises(ValueError):
        maintenance_worker.execute({"action": "operators"}, tmp_path)


def test_file_change_between_stat_and_open_is_refused(tmp_path, monkeypatch):
    path = tmp_path / "ops.json"
    path.write_bytes(b"[]")
    original = type(path).open

    def changed(self, *args, **kwargs):
        if self == path:
            with original(self, "wb") as stream:
                stream.write(b" [ ] ")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(type(path), "open", changed)
    with pytest.raises(ValueError, match="changed"):
        maintenance_worker.execute({"action": "operators"}, tmp_path)
