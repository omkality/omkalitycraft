import json
from types import SimpleNamespace

import pytest

from omk.dj2_linux_lab import LABEL, LinuxServer, inspect_owned


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
