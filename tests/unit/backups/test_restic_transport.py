import copy
import os
import subprocess
import sys

import pytest

from omk.backups import restic_transport as transport
from omk.backups.offsite_process import OffsiteError, bounded
from tests.fixtures.unit.backups.restic_transport import setup

__all__ = ["setup"]


def test_clean_environment_and_no_password_in_argv(setup, monkeypatch):
    monkeypatch.setenv("RESTIC_PASSWORD_COMMAND", "unexpected inherited hook")
    monkeypatch.setenv("HTTPS_PROXY", "http://unexpected-proxy.invalid")
    monkeypatch.setenv("RESTIC_REPOSITORY", "wrong inherited repository")
    receipt = setup.client.upload(setup.source, "c" * 32)
    assert receipt["snapshot_id"] == "b" * 64 and not receipt["data_read_back"]
    assert setup.client.check()["all_repository_data_read"]


@pytest.mark.parametrize("ending", [b"", b"\n", b"\r\n"])
def test_private_text_accepts_one_terminal_line_ending(setup, ending):
    p = setup.client.credential_root / "password"
    p.write_bytes(b"fixture-value" + ending)
    assert (
        transport.private_text(setup.client.credential_root, "password")
        == "fixture-value"
    )


@pytest.mark.parametrize("raw", [b"v\n\n", b"v\rv", b"v\r", b"v\0"])
def test_embedded_or_repeated_credential_lines_refuse(setup, raw):
    (setup.client.credential_root / "password").write_bytes(raw)
    with pytest.raises(OffsiteError):
        transport.private_text(setup.client.credential_root, "password")


def test_transport_import_needs_only_the_python_standard_library():
    r = subprocess.run(
        [
            sys.executable,
            "-S",
            "-c",
            "import omk.backups.restic_transport;import sys;assert 'psutil' not in sys.modules",
        ],
        capture_output=True,
        check=False,
        timeout=10,
        cwd=transport.PROJECT_ROOT,
    )
    assert r.returncode == 0


def test_lost_ack_is_looked_up_without_second_upload(setup):
    original = setup.client.upload(setup.source, "c" * 32)
    found = setup.client.find("c" * 32, setup.expected)
    assert found == original
    with pytest.raises(OffsiteError, match="already exists"):
        setup.client.upload(setup.source, "c" * 32)
    assert sum(c[0] == "backup" for c in setup.calls) == 1


def test_only_metadata_reads_and_staging_restore_avoid_remote_locks(setup, monkeypatch):
    commands = []
    monkeypatch.setattr(
        transport, "bounded", lambda command, **kw: commands.append(command) or b""
    )
    setup.client.invoke("cat", "config")
    setup.client.invoke("snapshots")
    setup.client.invoke(
        "restore", "b" * 64, "--target", str(setup.client.workspace / "fresh")
    )
    setup.client.invoke("check", "--read-data")
    setup.client.invoke("backup", str(setup.source))
    assert all("--no-lock" in c for c in commands[:3])
    assert all("--no-lock" not in c for c in commands[3:])


@pytest.mark.parametrize(
    "field,value",
    [
        ("id", "invalid-snapshot-id"),
        ("hostname", "foreign"),
        ("paths", ["/foreign"]),
        ("tags", ["foreign"]),
    ],
)
def test_wrong_snapshot_scope_refuses(setup, field, value):
    setup.client.upload(setup.source, "c" * 32)
    setup.records[0][field] = value
    with pytest.raises(OffsiteError, match="frozen"):
        setup.client.find("c" * 32, setup.expected)


def test_two_matching_snapshot_records_are_ambiguous(setup):
    setup.client.upload(setup.source, "c" * 32)
    setup.records.append(copy.deepcopy(setup.records[0]))
    with pytest.raises(OffsiteError, match="ambiguous"):
        setup.client.find("c" * 32, setup.expected)


@pytest.mark.parametrize("field", ["files", "bytes", "sha256", "source"])
def test_modified_frozen_receipt_refuses_before_network(setup, field):
    expected = copy.deepcopy(setup.expected)
    expected[field] = (
        {"injected": {}} if field == "files" else (0 if field == "bytes" else "wrong")
    )
    with pytest.raises(OffsiteError, match="frozen"):
        setup.client.find("c" * 32, expected)
    assert not setup.calls


def test_source_drift_during_upload_never_gets_a_receipt(setup, monkeypatch):
    def changed(command, **kw):
        r = setup.execute(command, **kw)
        if command[6] == "backup":
            (setup.source / "world.zip").write_bytes(b"changed")
        return r

    monkeypatch.setattr(transport, "bounded", changed)
    with pytest.raises(OffsiteError, match="source changed"):
        setup.client.upload(setup.source, "c" * 32)


def test_wrong_repository_is_refused_before_backup(setup, monkeypatch):
    monkeypatch.setattr(
        transport, "bounded", lambda *a, **kw: b'{"id":"wrong","version":2}'
    )
    with pytest.raises(OffsiteError, match="repository identity"):
        setup.client.upload(setup.source, "c" * 32)
    assert not setup.records


def test_binary_drift_and_credential_hardlink_refuse(setup):
    setup.client.binary.write_bytes(b"changed binary")
    with pytest.raises(OffsiteError, match="artifact pin"):
        setup.client.inspect()
    secret = setup.client.credential_root / "password"
    os.link(secret, secret.with_name("password-link"))
    with pytest.raises(OffsiteError, match="unlinked"):
        setup.client.validate()


@pytest.mark.parametrize(
    "endpoint",
    [
        "rest:http://owner:secret@host/repo/",
        "/local/repository",
        "rest:https://host/repo/",
        "rest:https://u:p@host/repo/?option=unsafe",
        "rest:https://u:p@host/repo/#fragment",
    ],
)
def test_non_tls_or_implicit_repository_refuses(setup, endpoint):
    (setup.client.credential_root / "repository").write_text(endpoint)
    with pytest.raises(OffsiteError, match="REST/TLS"):
        setup.client.validate()


@pytest.mark.parametrize(
    "action", ["init", "prune", "forget", "unlock", "repair", "key"]
)
def test_no_destructive_repository_actions(setup, action):
    with pytest.raises(OffsiteError, match="Unsupported"):
        setup.client.invoke(action)
    assert not setup.calls


@pytest.mark.parametrize(
    "entry", ["directory", "hardlink", "empty", "too-large", "too-many"]
)
def test_export_is_flat_bounded_and_unlinked(setup, entry):
    limits = setup.client.settings.copy()
    if entry == "directory":
        (setup.source / "subdir").mkdir()
    elif entry == "hardlink":
        os.link(setup.source / "world.zip", setup.source / "another.zip")
    elif entry == "empty":
        (setup.source / "world.zip").unlink()
    elif entry == "too-large":
        limits["max_bytes"] = 1
    elif entry == "too-many":
        limits["max_files"] = 1
        (setup.source / "auth.tar").write_bytes(b"archive")
    with pytest.raises(OffsiteError):
        transport.signature(setup.source, limits)


@pytest.mark.parametrize(
    "key,value",
    [
        ("TIMEOUT_SECONDS", "0"),
        ("OUTPUT_BYTES", "1023"),
        ("UPLOAD_KIB", "0"),
        ("GOMAXPROCS", "0"),
        ("MAX_FILES", "129"),
        ("MAX_BYTES", "-1"),
    ],
)
def test_invalid_policy_refuses(key, value):
    with pytest.raises(OffsiteError):
        transport.policy({"OMK_OFFSITE_" + key: value})


@pytest.mark.parametrize("mode", ["stdout", "stderr", "timeout", "partial"])
def test_real_child_failure_is_bounded_and_never_echoes_output(tmp_path, mode):
    code = {
        "stdout": "import os;os.write(1,b'PRIVATE_CANARY'*10000)",
        "stderr": "import os;os.write(2,b'PRIVATE_CANARY'*10000)",
        "timeout": "import time;print('PRIVATE_CANARY',flush=True);time.sleep(30)",
        "partial": "import sys;print('PRIVATE_CANARY');sys.exit(3)",
    }[mode]
    with pytest.raises(OffsiteError) as error:
        bounded(
            [sys.executable, "-c", code],
            environment=os.environ.copy(),
            directory=tmp_path,
            timeout=0.3 if mode == "timeout" else 5,
            maximum=1024,
        )
    assert "PRIVATE_CANARY" not in str(error.value)
    assert (
        ("exit 3" in str(error.value))
        if mode == "partial"
        else ("bound" in str(error.value))
    )


def test_real_child_success_returns_only_stdout(tmp_path):
    result = bounded(
        [
            sys.executable,
            "-c",
            "import sys;print('ok');print('ignored',file=sys.stderr)",
        ],
        environment=os.environ.copy(),
        directory=tmp_path,
        timeout=5,
        maximum=1024,
    )
    assert result == (b"ok\r\n" if os.name == "nt" else b"ok\n")
