import json
from types import SimpleNamespace

import pytest

from omk.dj2_linux_lab import LABEL, LinuxServer, forge_log_crashed, inspect_owned


@pytest.mark.parametrize("kind", ["container", "volume"])
def test_linux_lab_refuses_unowned_resources(monkeypatch, kind):
    data = (
        {"Labels": {LABEL: "someone-else"}}
        if kind == "volume"
        else {"Config": {"Labels": {LABEL: "someone-else"}}}
    )
    monkeypatch.setattr(
        "omk.dj2_linux_lab.docker",
        lambda *a, **kw: SimpleNamespace(returncode=0, stdout=json.dumps([data])),
    )
    with pytest.raises(ValueError, match="unowned"):
        inspect_owned(kind, "explicit-test-resource", "this-run")


def test_missing_resource_is_not_treated_as_owned(monkeypatch):
    monkeypatch.setattr(
        "omk.dj2_linux_lab.docker", lambda *a, **kw: SimpleNamespace(returncode=1)
    )
    assert inspect_owned("container", "absent-test-resource", "this-run") is None


def test_existing_volume_is_refused_before_seed_changes(tmp_path, monkeypatch):
    calls = []

    def present(*args, **kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("omk.dj2_linux_lab.docker", present)
    server = LinuxServer(tmp_path, "this-run", "new-test-network")
    with pytest.raises(ValueError, match="new Docker volume"):
        server.prepare(tmp_path / "unused-server", None, None)
    assert calls == [("volume", "inspect", server.volume)]
    assert not server.volume_created


@pytest.mark.parametrize(
    ("log", "expected"),
    [
        ("Stopping server\nSaving worlds\n", False),
        ("Optional integration failed: NullPointerException\nStopping server", False),
        (
            "Encountered an unexpected exception\nNullPointerException\nStopping server",
            True,
        ),
        ("This crash report has been saved to: /srv/crash-reports/example.txt", True),
    ],
)
def test_forge_crash_is_detected_even_when_process_exit_code_would_be_zero(
    tmp_path, log, expected
):
    file = tmp_path / "server.log"
    file.write_text(log)
    assert forge_log_crashed(file) is expected


def test_missing_or_oversized_log_cannot_prove_a_clean_exit(tmp_path):
    file = tmp_path / "server.log"
    assert forge_log_crashed(file) is None
    file.write_bytes(b" " * (8 * 1024**2 + 1))
    assert forge_log_crashed(file) is None


def test_zero_exit_forge_crash_changes_success_report_to_failure(tmp_path):
    server = LinuxServer(tmp_path, "test-run", "test-network")
    server.process = SimpleNamespace(poll=lambda: 0)
    server.log.write_text("Encountered an unexpected exception\nStopping server\n")
    report = {"ok": True}
    server._observe_exit(report)
    assert report["ok"] is False
    assert report["owned_game_clean_exit"] is False
    assert report["game_crash_detected"] is True
