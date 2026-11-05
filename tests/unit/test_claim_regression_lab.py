import json
from argparse import Namespace
from types import SimpleNamespace

import pytest

from omk import dj2_claim_regression_lab as labmod


def inputs(tmp_path):
    source = tmp_path / "input"
    source.mkdir()
    forge = source / "forge-1.12.2-14.23.5.2860.jar"
    forge.write_bytes(b"synthetic forge")
    mods = source / "mods.json"
    mods.write_text('{"synthetic":"1"}')
    return Namespace(
        server_source=source, agent=forge, core=forge, mods_json=mods, suite="all"
    )


def test_invalid_inputs_refused_before_docker_or_account_creation(
    tmp_path, monkeypatch
):
    args = inputs(tmp_path)
    args.mods_json.write_text('{"bad/key":"1"}')
    monkeypatch.setattr(labmod, "LinuxServer", lambda *a: pytest.fail("Docker touched"))
    monkeypatch.setattr(labmod, "_accounts", lambda *a: pytest.fail("Auth touched"))
    with pytest.raises(ValueError, match="approved mod"):
        labmod.run_claim_regression_lab(args)


@pytest.mark.parametrize("bad", ["missing-volume", "oversized", "wrong-shape"])
def test_bad_catalog_never_publishes_guard_input(tmp_path, monkeypatch, bad):
    monkeypatch.setattr(labmod, "CATALOG_LIMIT", 128)
    monkeypatch.setattr(
        labmod, "inspect_owned", lambda *a: None if bad == "missing-volume" else {}
    )

    def helper(*a, **kw):
        assert bad != "missing-volume" and kw["readonly_volume"]
        return SimpleNamespace(stdout="x" * 129 if bad == "oversized" else "[]")

    server = SimpleNamespace(volume="owned", run_id="this-run", helper=helper)
    with pytest.raises(ValueError):
        labmod._catalog(server, tmp_path)
    assert not (tmp_path / "omk-command-catalog.json").exists()


@pytest.mark.parametrize(
    "failure",
    [
        None,
        "guard",
        "dirty-stop",
        "export",
        "auth",
        "auth-exception",
        "unexpected-restart",
    ],
)
def test_acceptance_requires_guards_clean_server_and_auth_cleanup(
    tmp_path, monkeypatch, failure
):
    args = inputs(tmp_path)
    (tmp_path / ".local").mkdir()
    monkeypatch.setattr(labmod, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr("omk.dj2_lab.PROJECT_ROOT", tmp_path)
    calls = []

    def copy(args, lab):
        dest = lab / "server"
        (dest / "mods").mkdir(parents=True)
        for name in (
            "FTBUtilities-5.4.1.131.jar",
            "FTBLib-5.4.7.2.jar",
            "ironchest-1.12.2-7.0.72.847.jar",
        ):
            (dest / "mods" / name).write_bytes(b"synthetic mod")
        (dest / "forge-1.12.2-14.23.5.2860.jar").write_bytes(b"synthetic forge")
        return dest, {"synthetic": "1"}

    class Server:
        def __init__(self, lab, *a):
            self.volume, self.run_id, self.log = "owned", "fixture", lab / "log.txt"

        def prepare(self, *a):
            return "synthetic JRE"

        def start(self):
            return "synthetic process"

        def helper(self, command, **kw):
            assert kw["readonly_volume"]
            if command.startswith("cat /srv/ops"):
                return SimpleNamespace(stdout="[]")
            return SimpleNamespace(
                stdout=json.dumps(
                    {
                        "core": "synthetic",
                        "commands": [],
                        "rank_configs": [],
                        "ftb_claim_guard": (
                            "disabled" if failure == "guard" else "enabled"
                        ),
                        "ftb_mute_guard": "enabled",
                    }
                )
            )

        def close(self, report):
            calls.append("server-close")
            if failure == "export":
                raise OSError("controlled export failure")
            report["owned_game_clean_exit"] = failure != "dirty-stop"

    def cleanup(*a):
        calls.append("auth-close")
        if failure == "auth-exception":
            raise OSError("controlled auth failure")
        return failure != "auth"

    sessions = [SimpleNamespace(player_uuid="0" * 31 + n) for n in ("1", "2")]
    monkeypatch.setattr(labmod, "LinuxServer", Server)
    monkeypatch.setattr(labmod, "_copy_server", copy)
    monkeypatch.setattr(labmod, "_accounts", lambda *a: ("client", None, *sessions))
    monkeypatch.setattr(labmod, "inspect_owned", lambda *a: {})
    monkeypatch.setattr(labmod, "_wait_server", lambda *a: None)
    monkeypatch.setattr(labmod, "_console_sender", lambda *a: "console")
    monkeypatch.setattr(labmod, "_protocol_tests", lambda *a: calls.append("protocol"))
    monkeypatch.setattr(
        labmod, "run_command_checks", lambda *a, **kw: failure == "unexpected-restart"
    )
    monkeypatch.setattr(labmod, "_cleanup", cleanup)
    result = labmod.run_claim_regression_lab(args)
    assert result["ok"] == (failure is None)
    assert calls[-2:] == ["server-close", "auth-close"]
    if failure == "guard":
        assert "protocol" not in calls
        assert "initialized" in result["error"]
