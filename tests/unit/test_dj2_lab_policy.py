import json
import threading
import time
from argparse import Namespace
from unittest.mock import Mock

import pytest

from omk.dj2_lab import (
    _catalog_report,
    _cleanup,
    _console_sender,
    _copy_server,
    _validate,
    approved_mods,
)


def test_approved_mods_accept_legacy_empty_version_and_normal_r_suffix(tmp_path):
    path = tmp_path / "mods.json"
    path.write_text(json.dumps({"micdoodlecore": "", "example": "r1-preview"}))
    assert approved_mods(path) == {"micdoodlecore": "", "example": "r1-preview"}


def test_claim_guard_requires_its_explicit_command_suite():
    for commands, suite in ((False, "claim-edges"), (True, "containers")):
        with pytest.raises(ValueError, match="Claim guard checks require"):
            _validate(
                Namespace(claim_guard=True, commands=commands, command_suite=suite)
            )


def test_old_core_cannot_be_reported_as_guarded_claim_validation(tmp_path, monkeypatch):
    monkeypatch.setattr("omk.dj2_lab.PROJECT_ROOT", tmp_path)
    (tmp_path / "omk-command-catalog.json").write_text(
        json.dumps({"commands": [], "rank_configs": []})
    )

    def expect(condition, label):
        if not condition:
            raise RuntimeError(label)

    with pytest.raises(RuntimeError, match="missing adapter metadata"):
        _catalog_report(tmp_path, {}, False, expect, claim_guard=True)


@pytest.mark.parametrize("value", ["one\nother=mod", "one\rother=mod", "back\\slash"])
def test_approved_mods_reject_properties_injection(tmp_path, value):
    path = tmp_path / "mods.json"
    path.write_text(json.dumps({"example": value}))
    with pytest.raises(ValueError):
        approved_mods(path)


def test_owned_auth_cleanup_is_attempted_even_if_game_server_stop_fails(monkeypatch):
    def failed_stop(_server):
        raise OSError("test failure")

    monkeypatch.setattr("omk.dj2_lab._stop_server", failed_stop)
    run = Mock(return_value=Mock(returncode=0))
    monkeypatch.setattr("omk.dj2_lab.subprocess.run", run)
    report = {"ok": True}
    compose = ["docker", "compose", "--project-name", "omk-forge-lab-test-only"]
    _cleanup(None, None, compose, report)
    assert run.call_args.args[0] == [*compose, "down", "--timeout", "5"]
    assert not report["ok"] and report["temporary_auth_removed"]


def test_owned_auth_cleanup_survives_log_collector_failure(monkeypatch):
    monkeypatch.setattr("omk.dj2_lab._stop_server", Mock())
    run = Mock(return_value=Mock(returncode=0))
    monkeypatch.setattr("omk.dj2_lab.subprocess.run", run)
    report = {"ok": True}
    stream = Mock()
    stream.close.side_effect = OSError("test disk failure")
    _cleanup(None, stream, ["docker", "compose"], report)
    assert run.called and report["temporary_auth_removed"]
    assert report["log_collection_failed"] and not report["ok"]


def test_fresh_server_copy_excludes_existing_worlds_credentials_and_roles(tmp_path):
    source = tmp_path / "existing-server"
    (source / "config").mkdir(parents=True)
    (source / "mods").mkdir()
    (source / "world").mkdir()
    (source / "vintagefix/transformerCache").mkdir(parents=True)
    (source / "vintagefix/transformerCache/jarDiscoverer.cache").write_bytes(
        b"stale mod metadata"
    )
    (source / "world/marker").write_text("existing world must remain untouched")
    (source / "ops.json").write_text('[{"name":"old-operator"}]')
    (source / "server.properties").write_text("rcon.password=synthetic-old-secret\n")
    config = source / "config/ftbutilities.cfg"
    config.write_text("rtp_max_distance=100000.0\nrtp_min_distance=1000.0\n")
    (source / "mods/old-omkality.jar").write_bytes(b"legacy private core")
    core = tmp_path / "test-core.jar"
    core.write_bytes(b"explicit lab core")
    mods = tmp_path / "mods.json"
    mods.write_text('{"fixture":"1"}')
    lab = tmp_path / "owned-lab"
    lab.mkdir()
    before = {
        p.relative_to(source): p.read_bytes() for p in source.rglob("*") if p.is_file()
    }
    dest, _ = _copy_server(
        Namespace(server_source=source, core=core, mods_json=mods), lab
    )
    assert not (dest / "world").exists() and not (dest / "ops.json").exists()
    assert not (dest / "vintagefix").exists()
    assert not (dest / "mods/old-omkality.jar").exists()
    assert (dest / "mods/OmkalityCore.jar").read_bytes() == core.read_bytes()
    properties = (dest / "server.properties").read_text()
    assert "127.0.0.1" in properties and "enable-rcon=false" in properties
    assert "synthetic-old-secret" not in properties
    assert {
        p.relative_to(source): p.read_bytes() for p in source.rglob("*") if p.is_file()
    } == before


def test_console_waits_for_completion_and_does_not_reuse_old_success(tmp_path):
    path = tmp_path / "owned-server.log"
    path.write_text("Successfully found an unrelated earlier block\n")
    server = Mock()
    server.poll.return_value = None
    workers = []

    def write(payload):
        marker = payload.decode().split("\nsay ", 1)[1].strip()

        def complete():
            time.sleep(0.12)
            with path.open("a") as output:
                output.write(
                    "The current block is Air, expected Magma\n" + marker + "\n"
                )

        worker = threading.Thread(target=complete)
        workers.append(worker)
        worker.start()

    server.stdin.write.side_effect = write
    try:
        output = _console_sender(server, path)("testforblock 0 245 0 minecraft:magma")
        assert "expected Magma" in output
        assert "Successfully found" not in output
    finally:
        for worker in workers:
            worker.join(timeout=2)
