import hashlib
import os

import pytest

from omk import ftb_backup_policy as policy
from omk.maintenance_worker import execute

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


def test_disabled_disk_proof_is_readonly_and_not_live_or_one_writer_proof(runtime):
    before = {p: p.read_bytes() for p in runtime.rglob("*") if p.is_file()}
    proof = execute({"action": "nightly-policy"}, runtime)
    assert proof["adapter"] == policy.ADAPTER
    assert (
        proof["config_sha256"]
        == hashlib.sha256((runtime / "config/ftbbackups.cfg").read_bytes()).hexdigest()
    )
    assert proof["stock_enabled_on_disk"] is proof["stock_shutdown_on_disk"] is False
    assert proof["live_config_verified"] is proof["other_writers_verified"] is False
    assert before == {p: p.read_bytes() for p in runtime.rglob("*") if p.is_file()}
    assert "not-to-be-returned" not in str(proof)


@pytest.mark.parametrize(
    "change",
    [
        lambda s: s.replace("B:enabled=false", "B:enabled=true"),
        lambda s: s.replace("B:force_on_shutdown=false", "B:force_on_shutdown=true"),
        lambda s: s.replace("B:enabled=false", "B:enabled=False"),
        lambda s: s.replace("B:enabled=false", "B:enabled=false\nB:enabled=true"),
        lambda s: s.replace("B:enabled=false", "B:enabled=false\nB:enabled=false"),
        lambda s: s.replace("B:enabled=false\n", ""),
        lambda s: s.replace("general {", "general {\nB:unknown=false"),
        lambda s: s + "another {\nB:enabled=true\n}\n",
        lambda s: s.replace("example.txt", "{ B:enabled=true }"),
        lambda s: s.replace("\n>\n", "\n"),
        lambda s: s.replace("B:enabled=false", 'B:"enabled"=false'),
        lambda s: s + "\x00",
        lambda s: s + "#" * 65536,
    ],
)
def test_enabled_ambiguous_missing_or_unsupported_config_refuses(change):
    with pytest.raises(ValueError):
        policy.disabled_config(change(CONFIG))


def test_wrong_artifact_refuses_even_with_disabled_flags(runtime):
    (runtime / "mods" / policy.JAR).write_bytes(b"modified artifact")
    with pytest.raises(ValueError, match="Unreviewed"):
        policy.inspect(runtime)


def test_config_change_during_proof_refuses(runtime, monkeypatch):
    real = policy.runtime_digest
    calls = []

    def changed(root):
        value = real(root)
        calls.append(1)
        if len(calls) == 1:
            with (root / "config/ftbbackups.cfg").open("a") as stream:
                stream.write("# changed while inspecting\n")
        return value

    monkeypatch.setattr(policy, "runtime_digest", changed)
    with pytest.raises(ValueError, match="changed"):
        policy.inspect(runtime)


@pytest.mark.skipif(os.name == "nt", reason="Linux link semantics tested in Docker")
@pytest.mark.parametrize("kind", ["symlink", "hardlink", "directory", "parent"])
def test_runtime_links_or_wrong_types_refused(runtime, kind):
    file = runtime / "config/ftbbackups.cfg"
    if kind == "parent":
        (runtime / "config").rename(runtime / "actual")
        (runtime / "config").symlink_to(runtime / "actual", target_is_directory=True)
    else:
        file.unlink()
        if kind == "directory":
            file.mkdir()
        elif kind == "symlink":
            file.symlink_to(runtime / "server.properties")
        else:
            os.link(runtime / "server.properties", file)
    with pytest.raises(ValueError):
        policy.inspect(runtime)
