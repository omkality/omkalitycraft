from argparse import ArgumentParser, Namespace
from unittest.mock import Mock

import pytest

from omk import mcmcp_lab as lab
from tests.unit.test_game_runner import fixture


def test_parser_requires_explicit_inputs_and_bounds_are_checked_before_setup():
    parser = ArgumentParser()
    lab.add_mcmcp_lab(parser)
    with pytest.raises(SystemExit):
        parser.parse_args([])
    with pytest.raises(ValueError, match="Windows"):
        original = lab.current_platform
        try:
            lab.current_platform = lambda: "linux-x64"
            lab._preflight(Namespace())
        finally:
            lab.current_platform = original


@pytest.mark.parametrize(
    "minutes,port", [(0, 25685), (181, 25685), (90, 80), (90, 65536), (90, 25576)]
)
def test_unsafe_limits_fail_without_writing_or_starting(monkeypatch, minutes, port):
    monkeypatch.setattr(lab, "current_platform", lambda: "windows-x64")
    with pytest.raises(ValueError):
        lab._preflight(
            Namespace(
                duration_minutes=minutes,
                client_port=port,
                link_port=25680,
                bridge_port=25681,
            )
        )


def test_bom_verification_rejects_mutated_runtime(tmp_path):
    p = tmp_path / "runtime.jar"
    p.write_bytes(b"original")
    record = {"size": p.stat().st_size, "sha256": lab._sha(p)}
    lab._artifact(p, record)
    p.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="BOM"):
        lab._artifact(p, record)


def test_register_and_unregister_never_change_default_gates(tmp_path, monkeypatch):
    args = Namespace(
        orchestrator_cli=tmp_path / "mcp.exe", orchestrator_state=tmp_path / "state"
    )
    commands = []
    monkeypatch.setattr(lab, "refresh_idle", lambda _: None)
    monkeypatch.setattr(
        lab.subprocess,
        "run",
        lambda command, **kw: commands.append(command) or Namespace(returncode=0),
    )
    folder = tmp_path / "owned-game"
    lab._register(args, folder, "owned.client")
    assert lab._unregister(args, folder, "owned.client")
    assert len(commands) == 8
    assert all("owned.client" in command for command in commands if "policy" in command)
    assert commands[0][-2:] == ["trust-root", str(folder)]
    assert commands[4][-2:] == ["untrust-root", str(folder)]
    assert all(command[-1] == "deny" for command in commands[5:])


@pytest.fixture
def isolated_candidate(tmp_path, monkeypatch):
    _, release, _ = fixture(tmp_path / "fixture")
    root = tmp_path / "repo"
    (root / ".local").mkdir(parents=True)
    jar = tmp_path / "mcmcp.jar"
    jar.write_bytes(b"test jar")
    keys = tmp_path / "keys.json"
    keys.write_text("{}")
    args = Namespace(
        trusted_public_keys=keys,
        release_dir=tmp_path / "source",
        expected_release_sha256=release.digest,
        mcmcp_jar=jar,
        client_defaults=None,
        client_port=25685,
        link_port=25680,
        duration_minutes=1,
    )
    monkeypatch.setattr(lab, "PROJECT_ROOT", root)
    monkeypatch.setattr(
        lab, "_preflight", lambda _: ({"version": "2026.11.02"}, {"theoneprobe": "1"})
    )
    monkeypatch.setattr(
        lab, "PackDirectory", lambda *a: Namespace(verify=lambda: None, release=release)
    )

    class Wire:
        def __init__(self, *a):
            pass

        def serve(self):
            return self

        def __enter__(self):
            return "http://127.0.0.1:12345"

        def __exit__(self, *a):
            pass

    monkeypatch.setattr(lab, "PackWire", Wire)
    monkeypatch.setattr(
        lab, "ReleaseClient", lambda *a: Namespace(fetch=lambda _: release)
    )

    def installer(portable, transport):
        def install(*a):
            (portable / "instances/dj2/mods").mkdir(parents=True)
            (portable / "instances/dj2/config").mkdir()
            (portable / "instances/dj2/mods/TheOneProbe.jar").write_bytes(b"author mod")

        return Namespace(install=install)

    monkeypatch.setattr(lab, "Installer", installer)
    return root, args


@pytest.mark.parametrize("failure", ["registration", "missing-log", "client-stop"])
def test_failures_still_clean_owned_server_auth_and_permissions(
    isolated_candidate, monkeypatch, failure
):
    root, args = isolated_candidate
    close = Mock(side_effect=lambda r: r.update(owned_game_clean_exit=True))
    server = Mock(close=close)
    server.process.poll.return_value = None
    monkeypatch.setattr(lab, "LinuxServer", lambda *a: server)
    register = Mock(
        side_effect=(
            RuntimeError("registration failed after trust-root")
            if failure == "registration"
            else None
        )
    )
    cleanup = Mock(return_value=True)
    auth = Mock(return_value=True)
    monkeypatch.setattr(lab, "_register", register)
    monkeypatch.setattr(lab, "_unregister", cleanup)
    monkeypatch.setattr(lab, "_cleanup", auth)
    if failure != "registration":
        monkeypatch.setattr(lab, "_accounts", lambda *a: (None, Mock(), None, None))

        def copy_server(_args, scope):
            dest = scope / "server"
            dest.mkdir()
            (dest / "server.properties").write_text("generate-structures=false\n")
            return dest, None

        def start(*a, **kw):
            # A cleanly exited client may still have no log (early process failure).
            owned_lab = next(
                p for p in (root / ".local").glob("mcmcp-client-*") if p.is_dir()
            )
            (owned_lab / "native-finish").touch()
            game = Mock()
            game.poll.return_value = 0
            game.process.pid = 123
            return game

        monkeypatch.setattr(lab, "_copy_server", copy_server)
        monkeypatch.setattr(lab, "_wait_server", lambda *a: None)
        monkeypatch.setattr(lab, "_console_sender", lambda *a: Mock())
        monkeypatch.setattr(lab, "GameRunner", lambda *a: Namespace(start=start))
        if failure == "client-stop":
            monkeypatch.setattr(
                lab,
                "_stop_game",
                Mock(side_effect=OSError("private diagnostic sentinel")),
            )
    report = lab.run_mcmcp_lab(args)
    assert not report["ok"] and report["probe_absent"]
    if failure == "registration":
        assert report["error_type"] == "RuntimeError"
    else:
        assert "error_type" not in report, report
        assert report["client_cleanup_error_type"] == (
            "FileNotFoundError" if failure == "missing-log" else "OSError"
        )
    assert "sentinel" not in str(report)
    close.assert_called_once()
    cleanup.assert_called_once()
    auth.assert_called_once()
    assert report["orchestrator_permissions_removed"]


@pytest.mark.parametrize(
    "commands", [[], ["a\nb"], ["a\rb"], ["x" * 1500], [None], ["stop"] * 25]
)
def test_console_control_is_bounded(commands):
    with pytest.raises(ValueError):
        lab._console_commands({"commands": commands})


def test_forge_config_secrets_are_local_and_endpoints_are_loopback():
    a = lab._config("1" * 12, 25685, 25680)
    b = lab._config("1" * 12, 25685, 25680)
    assert a != b
    assert "S:bindAddress=127.0.0.1" in a and "B:portFallback=false" in a
    assert "B:enableServerEndpoint=false" in a and "B:allowWorldEdits=false" in a
