from types import SimpleNamespace
from unittest.mock import Mock

from deploy.offsite import pull_hourly_windows


def test_windows_sync_starts_ssh_without_console(monkeypatch):
    no_console = 0x08000000
    monkeypatch.setattr(
        pull_hourly_windows.subprocess, "CREATE_NO_WINDOW", no_console, raising=False
    )
    run = Mock(return_value=SimpleNamespace(stdout=b"[]"))
    monkeypatch.setattr(pull_hourly_windows.subprocess, "run", run)
    args = SimpleNamespace(ssh="ssh.exe", ssh_config="ssh.conf")

    assert pull_hourly_windows._remote(args, "list") == b"[]"
    assert run.call_args.kwargs["creationflags"] == no_console
