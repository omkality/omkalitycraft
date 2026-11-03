import hashlib

import pytest

from omk.dj2_client_policy import configure_load_sounds


@pytest.fixture
def artifact(tmp_path, monkeypatch):
    jar = tmp_path / "UniversalTweaks-1.12.2-1.20.0.jar"
    jar.write_bytes(b"controlled artifact fixture")
    monkeypatch.setattr(
        "omk.dj2_client_policy.LOAD_SOUND_ARTIFACT_SHA256",
        hashlib.sha256(jar.read_bytes()).hexdigest(),
    )
    return jar


def config(mode=b"MINECRAFT_AND_WORLD", newline=b"\n"):
    return newline.join(
        [
            b"# retained",
            b'"unrelated" {',
            b' S:"[1] Mode"=WORLD',
            b"}",
            b'    "load sounds" {',
            b'        S:"[1] Mode"=' + mode,
            b'        S:"[2] Minecraft Loaded Sounds" <',
            b"            projecte:item.pecharge;1.0;0.3",
            b"        >",
            b"    }",
            b"B:other=true",
            b"",
        ]
    )


@pytest.mark.parametrize("newline", [b"\n", b"\r\n"])
@pytest.mark.parametrize("mode", [b"MINECRAFT_AND_WORLD", b"MINECRAFT", b"WORLD", b"NOTHING"])
def test_only_reviewed_category_changes_and_repeated_staging_is_stable(tmp_path, artifact, mode, newline):
    path = tmp_path / "tweaks.cfg"
    before = config(mode, newline)
    path.write_bytes(before)
    result = configure_load_sounds(path, universal_tweaks=artifact)
    assert result["changed"] is (mode != b"NOTHING")
    assert path.read_bytes() == config(b"NOTHING", newline)
    assert not configure_load_sounds(path, universal_tweaks=artifact)["changed"]


@pytest.mark.parametrize(
    "data",
    [
        b"# missing category\n",
        config() + config(),
        config(b"invalid"),
        config().replace(
            b' S:"[1] Mode"=MINECRAFT_AND_WORLD',
            b' S:"[1] Mode"=WORLD\n S:"[1] Mode"=invalid',
        ),
        config().replace(b'        S:"[1] Mode"', b'        "nested" {\n        S:"[1] Mode"'),
        b"x" * (1024**2 + 1),
    ],
    ids=[
        "missing-category",
        "duplicate-category",
        "bad-mode",
        "duplicate-mode",
        "nested",
        "oversize",
    ],
)
def test_unrecognized_layout_is_rejected_without_rewriting(tmp_path, artifact, data):
    path = tmp_path / "tweaks.cfg"
    path.write_bytes(data)
    with pytest.raises(ValueError):
        configure_load_sounds(path, universal_tweaks=artifact)
    assert path.read_bytes() == data


def test_changed_same_name_jar_is_not_silently_allowed(tmp_path, artifact):
    path = tmp_path / "tweaks.cfg"
    path.write_bytes(config())
    artifact.write_bytes(artifact.read_bytes() + b"changed")
    with pytest.raises(ValueError, match="Unreviewed"):
        configure_load_sounds(path, universal_tweaks=artifact)
    assert path.read_bytes() == config()


def test_directory_and_link_cannot_be_a_staged_configuration(tmp_path, artifact):
    with pytest.raises(ValueError):
        configure_load_sounds(tmp_path, universal_tweaks=artifact)
    source = tmp_path / "real.cfg"
    source.write_bytes(config())
    link = tmp_path / "link.cfg"
    try:
        link.symlink_to(source)
    except OSError:
        pytest.skip("Symlinks unavailable on this host")
    with pytest.raises(ValueError):
        configure_load_sounds(link, universal_tweaks=artifact)
    assert source.read_bytes() == config()
