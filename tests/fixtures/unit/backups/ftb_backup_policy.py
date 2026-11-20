"""Test dependencies for ftb backup policy."""

import hashlib

import pytest

from omk.backups import ftb_backup_policy as policy

CONFIG = """# Synthetic fixture, not a modpack payload.
general {
D:backup_timer=0.05
I:backups_to_keep=12
I:buffer_size=4096
I:compression_level=1
B:disable_level_saving=true
B:display_file_size=true
B:enabled=false
S:extra_files <
example.txt
>
S:folder=
B:force_on_shutdown=false
S:max_total_size=48 GB
B:only_if_players_online=false
B:silent=false
}
"""


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    (tmp_path / "mods").mkdir()
    (tmp_path / "config").mkdir()
    jar = tmp_path / "mods" / policy.JAR
    jar.write_bytes(b"synthetic pinned artifact")
    monkeypatch.setattr(policy, "SHA256", hashlib.sha256(jar.read_bytes()).hexdigest())
    file = tmp_path / "config/ftbbackups.cfg"
    file.write_text(CONFIG)
    (tmp_path / "server.properties").write_text("rcon.password=not-to-be-returned\n")
    return tmp_path
