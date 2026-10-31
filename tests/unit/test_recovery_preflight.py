import hashlib
import struct
import zlib
from zipfile import ZipFile

import pytest

from launcher.nbt import Tag, write_nbt
from omk.recovery_preflight_lab import preflight


def snapshot(tmp_path, coordinates, *, wrong_coordinate=False, corrupt=False):
    regions = {}
    for x, z in coordinates:
        level = {
            "xPos": Tag(3, x + int(wrong_coordinate)),
            "zPos": Tag(3, z),
            "Sections": Tag(9, (10, [])),
            "TileEntities": Tag(9, (10, [])),
        }
        raw = write_nbt("", {"Level": Tag(10, level)})
        payload = b"corrupt compressed chunk" if corrupt else zlib.compress(raw)
        region = regions.setdefault((x // 32, z // 32), bytearray(8192))
        sector = len(region) // 4096
        offset = 4 * (x % 32 + (z % 32) * 32)
        region[offset : offset + 4] = sector.to_bytes(3, "big") + b"\x01"
        region.extend(
            (struct.pack(">IB", len(payload) + 1, 2) + payload).ljust(4096, b"\0")
        )
    path = tmp_path / "snapshot.zip"
    with ZipFile(path, "w") as archive:
        archive.writestr("lab-world/level.dat", b"synthetic fixture")
        for (x, z), region in regions.items():
            archive.writestr(f"lab-world/region/r.{x}.{z}.mca", region)
    return path


def test_complete_selection_is_readonly_and_checks_both_chunks(tmp_path):
    path = snapshot(tmp_path, [(8, 8), (9, 8)])
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    assert preflight(path, (143, 241, 132), (144, 241, 132)) == {
        "dimension": 0,
        "blocks": 2,
        "chunks": 2,
    }
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


def test_missing_chunk_is_rejected_even_when_region_exists(tmp_path):
    path = snapshot(tmp_path, [(8, 8)])
    with pytest.raises(ValueError, match="chunk location"):
        preflight(path, (143, 241, 132), (144, 241, 132))


def test_missing_region_and_negative_coordinates(tmp_path):
    path = snapshot(tmp_path, [(-1, -1), (0, -1)])
    assert preflight(path, (-1, 1, -1), (0, 1, -1))["chunks"] == 2
    with pytest.raises(ValueError, match="region"):
        preflight(path, (512, 1, 0), (512, 1, 0))


@pytest.mark.parametrize("options", [{"wrong_coordinate": True}, {"corrupt": True}])
def test_wrong_coordinate_or_broken_compression_rejected(tmp_path, options):
    path = snapshot(tmp_path, [(8, 8)], **options)
    with pytest.raises(ValueError):
        preflight(path, (130, 241, 130), (135, 243, 134))


@pytest.mark.parametrize("dimension", [False, 0.0, -1, 1])
def test_nonallowlisted_or_ambiguous_dimension_rejected(tmp_path, dimension):
    with pytest.raises(ValueError, match="dimension"):
        preflight(
            tmp_path / "does-not-exist.zip", (0, 0, 0), (0, 0, 0), dimension=dimension
        )


@pytest.mark.parametrize(
    "minimum,maximum",
    [
        ((0, 0, 0), (100, 100, 100)),
        ((1, 0, 0), (0, 0, 0)),
        ((0, -1, 0), (0, 1, 0)),
        ((0, 0, 0), (0, 256, 0)),
        ((True, 0, 0), (1, 0, 0)),
        ((0.0, 0, 0), (1, 0, 0)),
        ((0, 0, 0), (30000000, 0, 0)),
        ((0, 0, 0), (4095, 0, 0)),
    ],
)
def test_invalid_or_unbounded_selection_rejected_before_read(
    tmp_path, minimum, maximum
):
    with pytest.raises(ValueError):
        preflight(tmp_path / "does-not-exist.zip", minimum, maximum)
