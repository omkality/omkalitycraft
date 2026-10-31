import struct
import zlib
from argparse import Namespace
from unittest.mock import Mock
from zipfile import ZipFile

import pytest

from launcher.nbt import Tag, write_nbt
from omk.recovery_lab import _snapshot, _validate_inputs
from omk.recovery_nbt_lab import fixture_tiles
from omk.recovery_snapshot_lab import prepare_overworld_snapshot


def test_snapshot_requires_clean_exit_and_owned_lab(tmp_path):
    dest = tmp_path / "recovery-lab-test/server"
    (dest / "lab-world").mkdir(parents=True)
    (dest / "lab-world/level.dat").write_bytes(b"synthetic lab level")
    target = tmp_path / "snapshot.zip"
    for exit_code in (None, -1, 1):
        with pytest.raises(ValueError, match="cleanly stopped"):
            _snapshot(Mock(poll=Mock(return_value=exit_code)), dest, target)
    with pytest.raises(ValueError, match="owned recovery lab"):
        _snapshot(Mock(poll=Mock(return_value=0)), tmp_path / "real-server", target)
    assert not target.exists()


def test_snapshot_is_world_only_and_never_overwrites(tmp_path):
    dest = tmp_path / "recovery-lab-test/server"
    (dest / "lab-world/region").mkdir(parents=True)
    (dest / "lab-world/level.dat").write_bytes(b"synthetic level")
    (dest / "lab-world/region/r.0.0.mca").write_bytes(b"synthetic region")
    (dest / "ops.json").write_text("synthetic operator data")
    (dest / "server.properties").write_text("synthetic server configuration")
    target = tmp_path / "snapshot.zip"
    server = Mock(poll=Mock(return_value=0))
    result = _snapshot(server, dest, target)
    assert result["files"] == 2
    with ZipFile(target) as archive:
        assert set(archive.namelist()) == {
            "lab-world/level.dat",
            "lab-world/region/r.0.0.mca",
        }
    content = target.read_bytes()
    with pytest.raises(ValueError, match="already exists"):
        _snapshot(server, dest, target)
    assert target.read_bytes() == content


def test_snapshot_requires_world_marker(tmp_path):
    dest = tmp_path / "recovery-lab-test/server"
    dest.mkdir(parents=True)
    with pytest.raises(ValueError, match="Missing fresh world"):
        _snapshot(Mock(poll=Mock(return_value=0)), dest, tmp_path / "snapshot.zip")


def test_unpinned_worldedit_is_rejected_before_lab_creation(tmp_path):
    jar = tmp_path / "synthetic.jar"
    jar.write_bytes(b"untrusted candidate")
    mods = tmp_path / "mods.json"
    mods.write_text('{"fixture":"1"}')
    args = Namespace(java=jar, agent=jar, core=jar, mods_json=mods, worldedit=jar)
    with pytest.raises(ValueError, match="pinned official WorldEdit"):
        _validate_inputs(args)


def test_fixture_reader_preserves_nbt_types_and_rejects_bad_sectors(tmp_path):
    tile = {
        "x": Tag(3, 134),
        "y": Tag(3, 241),
        "z": Tag(3, 130),
        "Energy": Tag(3, 12345),
        "Facing": Tag(1, 5),
        "ForgeCaps": Tag(10, {"fixture": Tag(7, b"\x01\x02")}),
    }
    nbt = write_nbt(
        "", {"Level": Tag(10, {"TileEntities": Tag(9, (10, [Tag(10, tile)]))})}
    )
    payload = zlib.compress(nbt)
    region = bytearray(3 * 4096)
    offset = 4 * (8 + 8 * 32)
    region[offset : offset + 4] = b"\0\0\x02\x01"
    region[8192 : 8197 + len(payload)] = (
        struct.pack(">IB", len(payload) + 1, 2) + payload
    )
    snapshot = tmp_path / "fixture.zip"
    with ZipFile(snapshot, "w") as archive:
        archive.writestr("lab-world/region/r.0.0.mca", region)
    assert fixture_tiles(snapshot) == {(134, 241, 130): tile}
    region[offset : offset + 4] = b"\0\0\xff\x01"
    with ZipFile(snapshot, "w") as archive:
        archive.writestr("lab-world/region/r.0.0.mca", region)
    with pytest.raises(ValueError, match="Invalid fixture chunk location"):
        fixture_tiles(snapshot)


def test_snapshot_preparation_excludes_other_dimensions_and_private_files(tmp_path):
    source, output = tmp_path / "backup.zip", tmp_path / "snapshot.zip"
    with ZipFile(source, "w") as archive:
        archive.writestr("lab-world/DIM-1/region/r.0.0.mca", b"NETHER_DECOY")
        archive.writestr("lab-world/region/r.0.0.mca", b"OVERWORLD_EXPECTED")
        archive.writestr("lab-world/level.dat", b"synthetic level")
        archive.writestr("lab-world/playerdata/synthetic.dat", b"private fixture")
        archive.writestr("lab-world/region/../../synthetic-secret", b"not a region")
    original = source.read_bytes()
    result = prepare_overworld_snapshot(source, output)
    assert result["dimension"] == 0 and result["excluded_entries"] == 3
    with ZipFile(output) as archive:
        assert set(archive.namelist()) == {
            "lab-world/level.dat",
            "lab-world/region/r.0.0.mca",
        }
        assert archive.read("lab-world/region/r.0.0.mca") == b"OVERWORLD_EXPECTED"
    assert source.read_bytes() == original
    prepared = output.read_bytes()
    with pytest.raises(FileExistsError):
        prepare_overworld_snapshot(source, output)
    assert output.read_bytes() == prepared


@pytest.mark.parametrize("duplicate", [False, True])
def test_missing_or_ambiguous_overworld_snapshot_is_rejected(tmp_path, duplicate):
    source, output = tmp_path / "backup.zip", tmp_path / "snapshot.zip"
    with ZipFile(source, "w") as archive:
        archive.writestr("lab-world/level.dat", b"synthetic level")
        if duplicate:
            archive.writestr("lab-world/region/r.0.0.mca", b"first fixture")
            with pytest.warns(UserWarning, match="Duplicate"):
                archive.writestr("lab-world/region/r.0.0.mca", b"ambiguous fixture")
    with pytest.raises(ValueError, match="Missing or duplicate"):
        prepare_overworld_snapshot(source, output)
    assert not output.exists()
