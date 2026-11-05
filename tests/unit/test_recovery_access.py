import io
import tarfile
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace

import pytest

from omk.recovery_access_lab import FILES, LISTS, read_access, stage_access
from omk.recovery_lab import RecoveryRuntime, _validate_inputs


def fixture(tmp_path, entries=None):
    lab = tmp_path / "recovery-lab-access"
    folder = lab / "current-access-before"
    folder.mkdir(parents=True)
    target = lab / "recovery-lab-return/server"
    target.mkdir(parents=True)
    (lab / "full-return-staged.json").write_text("{}")
    (target / "server.properties").write_text(
        "server-port=25576\nonline-mode=true\nwhite-list=false\n"
    )
    archive = folder / "access.tar"
    data = dict.fromkeys(LISTS, b'[{"name":"synthetic"}]')
    data["server.properties"] = (
        b"white-list=true\nserver-port=1234\nrcon.password=never-copy-this-secret\n"
    )
    with tarfile.open(archive, "w") as tar:
        for name, value in entries if entries is not None else data.items():
            item = tarfile.TarInfo(name)
            item.size = len(value)
            tar.addfile(item, io.BytesIO(value))
    return lab, archive, target, data


def test_stage_current_lists_and_only_whitelist_flag_not_other_properties(tmp_path):
    lab, archive, target, data = fixture(tmp_path)
    result = stage_access(archive, target, lab=lab)
    assert result["whitelist_enabled"] and set(result["source_file_sha256"]) == set(
        FILES
    )
    for name in LISTS:
        assert (target / name).read_bytes() == data[name]
    text = (target / "server.properties").read_text()
    assert "server-port=25576" in text and "online-mode=true" in text
    assert text.count("white-list=true") == 1
    assert "1234" not in text and "never-copy-this-secret" not in text
    assert (lab / "current-access-staged.json").exists()
    with pytest.raises(ValueError, match="existing"):
        stage_access(archive, target, lab=lab)


@pytest.mark.parametrize(
    "bad",
    ["missing", "unknown", "duplicate", "traversal", "json", "flag", "duplicate-flag"],
)
def test_invalid_current_access_is_refused_before_target_changes(tmp_path, bad):
    entries = [(n, b"[]") for n in LISTS] + [
        ("server.properties", b"white-list=true\n")
    ]
    if bad == "missing":
        entries.pop(0)
    elif bad == "unknown":
        entries.append(("other.json", b"[]"))
    elif bad == "duplicate":
        entries.append(entries[0])
    elif bad == "traversal":
        entries[0] = ("../ops.json", b"[]")
    elif bad == "json":
        entries[0] = ("ops.json", b'{"secret":"do-not-log"}')
    elif bad == "flag":
        entries[-1] = ("server.properties", b"rcon.password=do-not-log\n")
    elif bad == "duplicate-flag":
        entries[-1] = ("server.properties", b"white-list=true\nwhite-list=false\n")
    lab, archive, target, _ = fixture(tmp_path, entries)
    original = (target / "server.properties").read_bytes()
    with pytest.raises(ValueError) as error:
        stage_access(archive, target, lab=lab)
    assert "do-not-log" not in str(error.value)
    assert not (lab / "current-access-plan.json").exists()
    assert not (lab / "current-access-staged.json").exists()
    assert not (target / "ops.json").exists()
    assert (target / "server.properties").read_bytes() == original


@pytest.mark.parametrize("kind", [tarfile.SYMTYPE, tarfile.LNKTYPE])
def test_access_archive_links_are_refused(tmp_path, kind):
    _, archive, _, _ = fixture(tmp_path)
    with tarfile.open(archive, "w") as tar:
        member = tarfile.TarInfo("ops.json")
        member.type, member.linkname = kind, "../outside"
        tar.addfile(member)
    with pytest.raises(ValueError, match="entry"):
        read_access(archive)


def test_oversized_policy_member_is_refused_without_extraction(tmp_path, monkeypatch):
    _, archive, _, _ = fixture(tmp_path, [("ops.json", b"x" * (65536 + 1))])
    monkeypatch.setattr("omk.recovery_access_lab.MAX_FILE", 65536)
    with pytest.raises(ValueError, match="entry"):
        read_access(archive)


def test_wrong_destination_cannot_change_original_server(tmp_path):
    lab, archive, _, _ = fixture(tmp_path)
    original = lab / "server"
    original.mkdir()
    (original / "ops.json").write_bytes(b"original-policy")
    with pytest.raises(ValueError, match="staged disposable"):
        stage_access(archive, original, lab=lab)
    assert (original / "ops.json").read_bytes() == b"original-policy"


@pytest.mark.parametrize("replacement_started", [False, True])
def test_incomplete_access_validation_preserves_original_scope(
    tmp_path, monkeypatch, replacement_started
):
    report = {"ok": True}
    runtime = RecoveryRuntime(
        Namespace(access_policy=True), tmp_path, None, None, report, None, None
    )
    calls = []

    def close(scope, **kwargs):
        calls.append(kwargs)
        scope["owned_game_clean_exit"] = True

    runtime.linux = SimpleNamespace(close=close)
    if replacement_started:
        runtime.source_linux = SimpleNamespace(close=close)
    monkeypatch.setattr("omk.recovery_lab._cleanup", lambda *a: None)
    runtime.close("unused-compose")
    assert calls[-1] == {"preserve_volume": True}
    assert not report["ok"] and report["access_policy_validation_incomplete"]


def test_partial_access_copy_never_publishes_start_marker(tmp_path, monkeypatch):
    lab, archive, target, _ = fixture(tmp_path)

    original = Path.open

    def fail(path, *args, **kwargs):
        if path == target / "banned-players.json" and args == ("xb",):
            raise OSError("controlled full disk")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fail)
    with pytest.raises(OSError):
        stage_access(archive, target, lab=lab)
    assert (target / "ops.json").exists()
    assert not (lab / "current-access-staged.json").exists()
    runtime = RecoveryRuntime(
        Namespace(access_policy=True), lab, None, None, {}, None, None
    )
    runtime.linux = SimpleNamespace()
    runtime.server = SimpleNamespace(poll=lambda: 0)
    with pytest.raises(ValueError, match="staged empty"):
        runtime.start(target)


@pytest.mark.parametrize(
    "runtime,full,edge",
    [
        ("native", True, True),
        ("linux-docker", False, True),
        ("linux-docker", True, False),
    ],
)
def test_access_option_requires_complete_linux_return_before_file_reads(
    runtime, full, edge
):
    with pytest.raises(ValueError, match="Access policy requires"):
        _validate_inputs(
            Namespace(
                access_policy=True,
                runtime=runtime,
                full_backup_return=full,
                edge_cases=edge,
            )
        )
