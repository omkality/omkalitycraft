import io
import tarfile
import zipfile

import pytest

from omk.recovery_linux_lab import world_tar_to_zip


def make_tar(path, entries):
    with tarfile.open(path, "w") as archive:
        for name, data in entries:
            entry = tarfile.TarInfo(name)
            entry.size = len(data)
            archive.addfile(entry, io.BytesIO(data))


def test_linux_export_is_world_only_streamed_and_never_overwrites(tmp_path):
    source, target = tmp_path / "world.tar", tmp_path / "world.zip"
    make_tar(
        source,
        [("lab-world/level.dat", b"level"), ("lab-world/region/r.0.0.mca", b"region")],
    )
    info = world_tar_to_zip(source, target)
    assert info["files"] == 2 and info["uncompressed_bytes"] == 11
    with zipfile.ZipFile(target) as archive:
        assert archive.read("lab-world/region/r.0.0.mca") == b"region"
    content = target.read_bytes()
    with pytest.raises(FileExistsError):
        world_tar_to_zip(source, target)
    assert target.read_bytes() == content
    assert not (tmp_path / "lab-world").exists()


@pytest.mark.parametrize(
    "name", ["../escape", "/absolute", "other-world/level.dat", "lab-world/a\\b"]
)
def test_linux_export_rejects_paths_without_extracting_them(tmp_path, name):
    source = tmp_path / "world.tar"
    make_tar(source, [("lab-world/level.dat", b"level"), (name, b"payload")])
    with pytest.raises(ValueError, match="Unsafe"):
        world_tar_to_zip(source, tmp_path / "world.zip")
    assert not (tmp_path / "lab-world").exists()


@pytest.mark.parametrize("kind", [tarfile.SYMTYPE, tarfile.LNKTYPE])
def test_linux_export_rejects_links(tmp_path, kind):
    source = tmp_path / "world.tar"
    with tarfile.open(source, "w") as archive:
        entry = tarfile.TarInfo("lab-world/link")
        entry.type, entry.linkname = kind, "../outside"
        archive.addfile(entry)
    with pytest.raises(ValueError, match="Linked"):
        world_tar_to_zip(source, tmp_path / "world.zip")


@pytest.mark.parametrize(
    "entries",
    [
        [("lab-world/not-level.dat", b"x")],
        [("lab-world/level.dat", b"x"), ("lab-world/LEVEL.dat", b"y")],
        [("lab-world/level.dat", b"x"), ("lab-world/level.dat", b"y")],
        [("lab-world/level.dat", b"x"), ("lab-world/level.dat/child", b"y")],
    ],
)
def test_linux_export_rejects_missing_level_and_colliding_paths(tmp_path, entries):
    source = tmp_path / "world.tar"
    make_tar(source, entries)
    with pytest.raises(ValueError):
        world_tar_to_zip(source, tmp_path / "world.zip")


@pytest.mark.parametrize("limit", ["MAX_FILE", "MAX_TOTAL", "MAX_FILES"])
def test_linux_export_applies_resource_limits(tmp_path, monkeypatch, limit):
    source = tmp_path / "world.tar"
    make_tar(source, [("lab-world/level.dat", b"1234"), ("lab-world/other", b"5678")])
    monkeypatch.setattr("omk.recovery_linux_lab." + limit, 1)
    with pytest.raises(ValueError, match=r"oversized|exceeds"):
        world_tar_to_zip(source, tmp_path / "world.zip")
