import json
from argparse import Namespace
from types import SimpleNamespace
from urllib.error import URLError

import pytest

from omk import dj2_account_recovery_lab as labmod
from omk.cli import main
from omk.drasl import DraslError


def inputs(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    forge = source / "forge-1.12.2-14.23.5.2860.jar"
    forge.write_bytes(b"synthetic")
    mods = source / "mods.json"
    mods.write_text('{"synthetic":"1"}')
    return Namespace(
        server_source=source, agent=forge, core=forge, mods_json=mods, suite="all"
    )


@pytest.mark.parametrize("bad", ["missing", "mods"])
def test_invalid_recovery_inputs_never_touch_docker_or_auth(tmp_path, monkeypatch, bad):
    args = inputs(tmp_path)
    if bad == "missing":
        args.agent.unlink()
    elif bad == "mods":
        args.mods_json.write_text('{"bad/key":"1"}')
    monkeypatch.setattr(labmod, "LinuxServer", lambda *a: pytest.fail("Docker touched"))
    monkeypatch.setattr(labmod, "_accounts", lambda *a: pytest.fail("Auth touched"))
    with pytest.raises(ValueError):
        labmod.run_account_recovery_lab(args)


@pytest.mark.parametrize(
    "error", [URLError("fixture-secret"), DraslError(500), DraslError(404)]
)
def test_network_and_unexpected_http_failure_are_not_successful_revocation(error):
    def fail():
        raise error

    expected = URLError if isinstance(error, URLError) else RuntimeError
    with pytest.raises(expected):
        labmod._denied(
            fail, lambda *a: pytest.fail("accepted a network error"), "label"
        )


def test_successful_http_is_never_a_revoked_session():
    with pytest.raises(RuntimeError, match="must be denied"):
        labmod._denied(lambda: None, lambda *a: pytest.fail("accepted"), "label")


@pytest.mark.parametrize(
    "failure", [None, "auth", "exercise", "stop", "cleanup", "cleanup-exception"]
)
def test_acceptance_requires_real_scenario_clean_stop_and_auth_cleanup(
    tmp_path, monkeypatch, failure
):
    args = inputs(tmp_path)
    (tmp_path / ".local").mkdir()
    monkeypatch.setattr(labmod, "PROJECT_ROOT", tmp_path)
    calls = []
    sessions = [SimpleNamespace(player_uuid="00000000-0000-0000-0000-000000000001")]
    accounts = SimpleNamespace(client=object(), sessions=sessions)

    class Server:
        def __init__(self, *a):
            self.log = tmp_path / "server.log"

        def prepare(self, *a):
            return "synthetic JRE"

        def start(self):
            return object()

        def helper(self, *a, **kw):
            assert kw["readonly_volume"]
            return SimpleNamespace(stdout="[]")

        def close(self, report):
            calls.append("server-close")
            report["owned_game_clean_exit"] = failure != "stop"

    def setup(*a):
        if failure == "auth":
            raise RuntimeError("secret-sentinel")
        return accounts

    def exercise(*a):
        calls.append("exercise")
        if failure == "exercise":
            raise RuntimeError("secret-sentinel")

    def cleanup(*a):
        calls.append("auth-close")
        if failure == "cleanup-exception":
            raise OSError("secret-sentinel")
        return failure != "cleanup"

    monkeypatch.setattr(labmod, "LinuxServer", Server)
    monkeypatch.setattr(labmod, "_accounts", setup)
    monkeypatch.setattr(
        labmod, "_copy_server", lambda *a: (tmp_path, {"synthetic": "1"})
    )
    monkeypatch.setattr(labmod, "_artifact_hashes", lambda *a: {})
    monkeypatch.setattr(labmod, "_wait_server", lambda *a: None)
    monkeypatch.setattr(labmod, "_console_sender", lambda *a: object())
    monkeypatch.setattr(labmod, "_exercise", exercise)
    monkeypatch.setattr("omk.dj2_claim_regression_lab._cleanup", cleanup)
    report = labmod.run_account_recovery_lab(args)
    assert report["ok"] == (failure is None)
    assert calls[-2:] == ["server-close", "auth-close"]
    assert "secret-sentinel" not in json.dumps(report)
    saved = tmp_path / report["lab"] / "report.json"
    assert "secret-sentinel" not in saved.read_text()


def test_cli_recovery_does_not_require_or_open_a_desktop(monkeypatch, capsys):
    monkeypatch.setattr(
        labmod, "run_account_recovery_lab", lambda args: {"ok": True, "gui": False}
    )
    args = ["lab", "dj2-account-recovery"]
    for key in ["server-source", "agent", "core", "mods-json"]:
        args += ["--" + key, "synthetic"]
    assert main(args) == 0
    assert json.loads(capsys.readouterr().out) == {"ok": True, "gui": False}
