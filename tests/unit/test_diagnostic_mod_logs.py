"""Private mod-log tails share the operator export budget; no runtime log writes."""

import base64
import json
import os
import random
import zipfile
from pathlib import Path

import pytest

from omk.diagnostic_export import export_bundle, export_limits
from omk.diagnostics import MIB
from omk.profiles import PROJECT_ROOT


def contents(result):
    with zipfile.ZipFile(result["archive"]) as archive:
        assert archive.testzip() is None
        files = {name: archive.read(name) for name in archive.namelist()}
    return files, json.loads(files["diagnostic.json"])


def test_mod_tails_are_allowlisted_redacted_and_source_unchanged(tmp_path):
    source = tmp_path / "server"
    (source / "logs").mkdir(parents=True)
    fixtures = {
        "crafttweaker.log": b"ERROR recipe password=hidden-ct\n",
        "logs/groovy_server.log": b"Groovy ERROR Authorization: Bearer hidden-groovy\n",
        "logs/groovy.log": b"Groovy client traceback\n",
        "logs/other.log": b"private-other\n",
        "crafttweaker.log.gz": b"private-compressed\n",
        "groovy_server.log": b"private-wrong-location\n",
        "server.properties": b"rcon.password=private-properties\n",
    }
    for name, data in fixtures.items():
        (source / name).write_bytes(data)
    stamps = {name: (source / name).stat().st_mtime_ns for name in fixtures}
    result = export_bundle(
        tmp_path / "owner", "dj2", server_root=source, environment={}
    )
    files, metadata = contents(result)
    assert set(files) == {
        "mods/crafttweaker.log",
        "mods/groovy_server.log",
        "mods/groovy.log",
        "diagnostic.json",
    }
    combined = b"\n".join(files.values())
    assert b"ERROR recipe" in combined and b"Groovy ERROR" in combined
    assert b"hidden-" not in combined and b"private-" not in combined
    assert metadata["server"] and metadata["omitted_due_to_budget"] == 0
    for name, data in fixtures.items():
        assert (source / name).read_bytes() == data
        assert (source / name).stat().st_mtime_ns == stamps[name]


def test_large_mod_log_is_a_bounded_tail_with_explicit_truncation(tmp_path):
    source = tmp_path / "server"
    source.mkdir()
    (source / "crafttweaker.log").write_bytes(
        b"FIRST\n" + b"repeated line\n" * 250000 + b"FINAL ERROR recipe\n"
    )
    files, metadata = contents(
        export_bundle(
            tmp_path / "owner",
            "dj2",
            server_root=source,
            environment={"OMK_DIAGNOSTIC_FILE_MIB": "1"},
        )
    )
    tail = files["mods/crafttweaker.log"]
    assert len(tail) <= MIB and b"FINAL ERROR recipe" in tail and b"FIRST" not in tail
    assert metadata["files"][0]["truncated"]


def test_crash_has_priority_and_budget_omissions_are_visible(tmp_path):
    source = tmp_path / "server"
    (source / "crash-reports").mkdir(parents=True)
    (source / "crash-reports/crash-test.txt").write_bytes(b"x" * MIB)
    (source / "crafttweaker.log").write_bytes(b"recipe error\n")
    limits = {
        "OMK_DIAGNOSTIC_FILE_MIB": "1",
        "OMK_DIAGNOSTIC_BUNDLE_MIB": "1",
        "OMK_DIAGNOSTIC_STORAGE_MIB": "2",
    }
    files, metadata = contents(
        export_bundle(tmp_path / "owner", "dj2", server_root=source, environment=limits)
    )
    assert set(files) == {"crashes/crash-test.txt", "diagnostic.json"}
    assert metadata["omitted_due_to_budget"] == 1
    assert metadata["limits"]["bundle_bytes"] == MIB


@pytest.mark.parametrize("relative", ["crafttweaker.log", "logs/groovy_server.log"])
def test_linked_mod_file_is_never_read(tmp_path, relative):
    if os.name == "nt":
        pytest.skip("Read-only Linux Docker symlink acceptance")
    source = tmp_path / "server"
    (source / "logs").mkdir(parents=True)
    outside = tmp_path / "private"
    outside.write_bytes(b"outside-secret")
    (source / relative).symlink_to(outside)
    files, _ = contents(
        export_bundle(tmp_path / "owner", "dj2", server_root=source, environment={})
    )
    assert len(files) == 1 and b"outside-secret" not in files["diagnostic.json"]
    assert outside.read_bytes() == b"outside-secret"


def test_export_limits_defaults_and_valid_overrides():
    default = export_limits({})
    assert (
        default.file_bytes,
        default.bundle_bytes,
        default.keep_files,
        default.storage_bytes,
    ) == (2 * MIB, 16 * MIB, 5, 64 * MIB)
    value = export_limits(
        {
            "OMK_DIAGNOSTIC_FILE_MIB": "1",
            "OMK_DIAGNOSTIC_BUNDLE_MIB": "4",
            "OMK_DIAGNOSTIC_KEEP_FILES": "2",
            "OMK_DIAGNOSTIC_STORAGE_MIB": "8",
        }
    )
    assert (
        value.file_bytes,
        value.bundle_bytes,
        value.keep_files,
        value.storage_bytes,
    ) == (MIB, 4 * MIB, 2, 8 * MIB)


@pytest.mark.parametrize(
    "raw", ["", "0", "9", "-1", "1.5", " 2", "2\n", "２", "secret-value", None]
)
def test_bad_limits_fail_before_creating_output_without_echoing_value(tmp_path, raw):
    owner = tmp_path / "owner"
    with pytest.raises(ValueError, match="Invalid OMK_DIAGNOSTIC_FILE_MIB") as error:
        export_bundle(owner, "dj2", environment={"OMK_DIAGNOSTIC_FILE_MIB": raw})
    assert "secret-value" not in str(error.value)
    assert not owner.exists()


@pytest.mark.parametrize(
    "settings",
    [
        {"OMK_DIAGNOSTIC_FILE_MIB": "4", "OMK_DIAGNOSTIC_BUNDLE_MIB": "2"},
        {"OMK_DIAGNOSTIC_STORAGE_MIB": "16"},
        {"OMK_DIAGNOSTIC_KEEP_FILES": "21"},
        {"OMK_DIAGNOSTIC_STORAGE_MIB": "513"},
        {"OMK_DIAGNOSTIC_BUNDLE_MIB": "65"},
    ],
)
def test_invalid_budget_combinations_are_rejected(settings):
    with pytest.raises(ValueError):
        export_limits(settings)


def test_custom_export_retention_keeps_latest_and_unrelated_files(tmp_path):
    owner = tmp_path / "owner"
    policy = {"OMK_DIAGNOSTIC_KEEP_FILES": "2"}
    for _ in range(4):
        latest = export_bundle(owner, "dj2", environment=policy)
    folder = owner / "userdata/diagnostics"
    assert len(list(folder.glob("diag-*.zip"))) == 2
    assert latest["archive"] in {str(p) for p in folder.glob("diag-*.zip")}
    sentinel = folder / "my-archive.zip"
    sentinel.write_bytes(b"keep")
    export_bundle(owner, "dj2", environment=policy)
    assert sentinel.read_bytes() == b"keep"


def test_export_storage_byte_budget_preserves_newest_archive(tmp_path):
    source = tmp_path / "server"
    source.mkdir()
    data = base64.b64encode(random.Random(42).randbytes(MIB))[: MIB - 1] + b"\n"
    (source / "crafttweaker.log").write_bytes(data)
    owner = tmp_path / "owner"
    limits = {
        "OMK_DIAGNOSTIC_FILE_MIB": "1",
        "OMK_DIAGNOSTIC_BUNDLE_MIB": "1",
        "OMK_DIAGNOSTIC_STORAGE_MIB": "2",
        "OMK_DIAGNOSTIC_KEEP_FILES": "20",
    }
    for _ in range(5):
        latest = export_bundle(owner, "dj2", server_root=source, environment=limits)
    archives = list((owner / "userdata/diagnostics").glob("diag-*.zip"))
    assert sum(path.stat().st_size for path in archives) <= 2 * MIB
    assert len(archives) < 5 and latest["archive"] in {str(path) for path in archives}


def test_redaction_expansion_stays_inside_file_budget(tmp_path):
    source = tmp_path / "server"
    source.mkdir()
    (source / "crafttweaker.log").write_bytes(b"password=x\n" * 80000)
    files, metadata = contents(
        export_bundle(
            tmp_path / "owner",
            "dj2",
            server_root=source,
            environment={"OMK_DIAGNOSTIC_FILE_MIB": "1"},
        )
    )
    assert len(files["mods/crafttweaker.log"]) <= MIB
    assert metadata["files"][0]["truncated"]
    assert b"password=x" not in files["mods/crafttweaker.log"]


def test_environment_is_read_without_persisting_raw_values(monkeypatch):
    monkeypatch.setenv("OMK_DIAGNOSTIC_KEEP_FILES", "3")
    assert export_limits().keep_files == 3


def test_clock_rollback_does_not_evict_just_published_export(tmp_path):
    first = export_bundle(tmp_path, "dj2", environment={})
    os.utime(first["archive"], (4102444800, 4102444800))
    second = export_bundle(
        tmp_path, "dj2", environment={"OMK_DIAGNOSTIC_KEEP_FILES": "1"}
    )
    assert list((tmp_path / "userdata/diagnostics").glob("diag-*.zip")) == [
        Path(second["archive"])
    ]


def test_environment_example_matches_real_defaults():
    text = (PROJECT_ROOT / "deploy/diagnostics.example.env").read_text(encoding="utf-8")
    values = dict(
        line.split("=", 1)
        for line in text.splitlines()
        if line.startswith("OMK_DIAGNOSTIC_")
    )
    assert len(values) == 4 and export_limits(values) == export_limits({})
