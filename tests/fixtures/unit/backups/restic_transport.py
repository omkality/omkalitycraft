"""Test dependencies for restic transport."""

import hashlib
import json
from types import SimpleNamespace

import pytest

from omk.backups import restic_transport as transport


@pytest.fixture
def setup(tmp_path, monkeypatch):
    secret = tmp_path / "secret"
    secret.mkdir(mode=0o700)
    for name, value in {
        "repository": "rest:https://owner:HTTP_SECRET@repository:8000/owner/test/",
        "password": "ENCRYPTION_SECRET",
        "ca.pem": "fixture-certificate",
    }.items():
        p = secret / name
        p.write_text(value)
        p.chmod(0o600)
    workspace = tmp_path / "workspace"
    workspace.mkdir(mode=0o700)
    source = tmp_path / "input"
    source.mkdir()
    (source / "world.zip").write_bytes(b"closed archive fixture")
    binary = tmp_path / "restic"
    binary.write_bytes(b"fixture binary")
    (tmp_path / "deploy/offsite").mkdir(parents=True)
    (tmp_path / "deploy/offsite/offsite-tools.json").write_text(
        json.dumps(
            {
                "artifacts": [
                    {
                        "name": "restic",
                        "binary_sha256": hashlib.sha256(
                            binary.read_bytes()
                        ).hexdigest(),
                    }
                ]
            }
        )
    )
    monkeypatch.setattr(transport, "PROJECT_ROOT", tmp_path)
    client = transport.Restic(secret, workspace, "a" * 64, transport.policy({}), binary)
    expected = transport.signature(source, client.settings)
    records = []
    calls = []

    def execute(command, **kw):
        assert not any(
            x in str(command) + str(kw["environment"])
            for x in ["HTTP_SECRET", "ENCRYPTION_SECRET"]
        )
        assert set(kw["environment"]) == {
            "PATH",
            "HOME",
            "TMPDIR",
            "RESTIC_REPOSITORY_FILE",
            "RESTIC_PASSWORD_FILE",
            "RESTIC_CACERT",
            "GOMAXPROCS",
        }
        assert command[:4] == [str(binary), "--no-cache", "--json", "--quiet"]
        args = command[6:]
        calls.append(args)
        if args[:2] == ["cat", "config"]:
            return json.dumps({"id": "a" * 64, "version": 2}).encode()
        if args[0] == "snapshots":
            return json.dumps(records).encode()
        if args[0] == "backup":
            records.append(
                {
                    "id": "b" * 64,
                    "hostname": transport.HOST,
                    "paths": [str(source)],
                    "tags": ["omk-op=" + "c" * 32, "omk-sha=" + expected["sha256"]],
                }
            )
            return b'{"message_type":"summary","snapshot_id":"bbbbbbbb"}\n'
        if args[0] == "check":
            return b""
        pytest.fail("Unexpected command")

    monkeypatch.setattr(transport, "bounded", execute)
    return SimpleNamespace(
        client=client,
        source=source,
        expected=expected,
        records=records,
        calls=calls,
        execute=execute,
    )
