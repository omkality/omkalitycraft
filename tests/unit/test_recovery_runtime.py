from types import SimpleNamespace

import pytest

from omk.recovery_lab import RecoveryRuntime


@pytest.mark.parametrize(
    "failure", ["running", "not-staged", "different-path", "repeat"]
)
def test_linux_replacement_refuses_unverified_transition(tmp_path, failure):
    runtime = RecoveryRuntime(None, tmp_path, None, None, {}, None, None)
    runtime.linux = SimpleNamespace()
    runtime.server = SimpleNamespace(poll=lambda: None if failure == "running" else 0)
    if failure != "not-staged":
        (tmp_path / "full-return-staged.json").write_text("{}")
    if failure == "repeat":
        runtime.source_linux = SimpleNamespace()
    target = tmp_path / (
        "other/server" if failure == "different-path" else "recovery-lab-return/server"
    )
    with pytest.raises(ValueError, match="staged empty Linux replacement"):
        runtime.start(target)


def test_linux_replacement_keeps_source_and_cleans_both_scopes(tmp_path, monkeypatch):
    report = {"ok": True}
    runtime = RecoveryRuntime("args", tmp_path, None, "auth", report, None, None)
    source = SimpleNamespace(
        server=SimpleNamespace(network="owned-network"), world_digest=lambda: "source"
    )
    replacement = SimpleNamespace()
    runtime.linux = source
    runtime.server = SimpleNamespace(poll=lambda: 0)
    (tmp_path / "full-return-staged.json").write_text("{}")
    calls = []
    replacement.prepare = lambda *a: calls.append(("prepare", a))
    replacement.start = lambda: ("replacement-process", "log", "stream")

    def cleanup(label):
        def close(scope):
            calls.append(("close", label))
            scope["owned_game_clean_exit"] = True

        return close

    source.close, replacement.close = cleanup("source"), cleanup("replacement")
    monkeypatch.setattr("omk.recovery_linux_lab.LinuxRecovery", lambda *a: replacement)
    monkeypatch.setattr("omk.recovery_lab._wait_server", lambda *a: None)
    monkeypatch.setattr("omk.recovery_lab._console_sender", lambda *a: "console")
    monkeypatch.setattr("omk.recovery_lab._cleanup", lambda *a: calls.append(("auth",)))
    target = tmp_path / "recovery-lab-return/server"
    assert runtime.start(target) == "console"
    assert runtime.source_linux is source and runtime.linux is replacement
    assert runtime.original_world_digest() == "source"
    runtime.close("compose")
    assert calls == [
        ("prepare", (target, "args", "auth")),
        ("close", "replacement"),
        ("close", "source"),
        ("auth",),
    ]
    assert report["ok"] and report["linux_original"]["owned_game_clean_exit"]
