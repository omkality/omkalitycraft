"""Test dependencies for project moderation."""

from types import SimpleNamespace

import pytest

from omk.game import project_moderation as moderation

UUID = "12345678-1234-4234-8234-123456789abc"


@pytest.fixture
def project(tmp_path, monkeypatch):
    root = tmp_path / ".omk-admin"
    root.mkdir(mode=0o700)
    config = root / "operator.toml"
    config.write_text(
        'schema=1\n[servers.alpha]\nroot="../alpha"\n[servers.beta]\nroot="../beta"\n',
        encoding="utf-8",
    )
    store, _ = moderation.initialize(root)
    online = {"alpha": {UUID: "FirstJoin"}, "beta": {}}
    proof = dict.fromkeys(online, store)

    def command(server, _password, text):
        if server not in online:
            raise ConnectionRefusedError
        if text == "list omk-moderation project":
            return f"OMK_PROJECT_MODERATION_V1 {proof[server]}"
        assert text == "list uuids"
        values = ", ".join(f"{name} ({uid})" for uid, name in online[server].items())
        return f"There are {len(online[server])}/4 players online: {values}"

    monkeypatch.setattr(
        moderation, "credential", lambda _config, server: (server, "private")
    )
    monkeypatch.setattr(moderation, "command", command)
    monkeypatch.setattr(moderation.time, "time", lambda: 1_800_000_000)
    return SimpleNamespace(path=config, root=root, online=online, proof=proof)
