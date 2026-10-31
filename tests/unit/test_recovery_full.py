import hashlib
import json
import stat
from unittest.mock import Mock
from zipfile import BadZipFile, ZipFile, ZipInfo

import pytest

from omk.recovery_full_lab import _copy_entry, stage_full_world


def fixture(tmp_path, entries=None):
    lab = tmp_path / "recovery-lab-owned"
    (lab / "backups").mkdir(parents=True)
    dest = lab / "recovery-lab-return/server/lab-world"
    dest.parent.mkdir(parents=True)
    archive = lab / "backups/before.zip"
    with ZipFile(archive, "x") as output:
        for name, payload in entries or [
            ("lab-world/level.dat", b"synthetic level"),
            ("lab-world/data/ftb_lib/team.dat", b"synthetic FTB data"),
            ("lab-world/DIM-1/region/r.0.0.mca", b"synthetic dimension"),
        ]:
            # Preserve hostile raw ZIP names: ZipInfo normally normalizes the
            # host OS separator and truncates NUL, unlike an external producer.
            info = ZipInfo(name)
            info.filename = name
            output.writestr(info, payload)
    return lab, archive, dest, hashlib.sha256(archive.read_bytes()).hexdigest()


def test_full_return_preserves_source_and_verifies_all_bytes(tmp_path):
    lab, archive, dest, digest = fixture(tmp_path)
    old = lab / "server/lab-world/level.dat"
    old.parent.mkdir(parents=True)
    old.write_bytes(b"untouched current lab world")
    result = stage_full_world(Mock(poll=lambda: 0), archive, digest, dest, lab=lab)
    assert result["files"] == 3 and result["readback_verified"]
    assert (dest / "data/ftb_lib/team.dat").read_bytes() == b"synthetic FTB data"
    assert (dest / "DIM-1/region/r.0.0.mca").read_bytes() == b"synthetic dimension"
    assert old.read_bytes() == b"untouched current lab world"
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == digest
    plan = json.loads((lab / "full-return-plan.json").read_text())
    assert plan["original_world_preserved"] and plan["old_server_cleanly_stopped"]
    before = (dest / "level.dat").read_bytes()
    with pytest.raises(ValueError, match="empty replacement"):
        stage_full_world(Mock(poll=lambda: 0), archive, digest, dest, lab=lab)
    assert (dest / "level.dat").read_bytes() == before


@pytest.mark.parametrize("exit_code", [None, 1, -1])
def test_running_or_unclean_exit_never_creates_destination(tmp_path, exit_code):
    lab, archive, dest, digest = fixture(tmp_path)
    with pytest.raises(ValueError, match="cleanly stopped"):
        stage_full_world(Mock(poll=lambda: exit_code), archive, digest, dest, lab=lab)
    assert not dest.exists() and not (lab / "full-return-plan.json").exists()


@pytest.mark.parametrize(
    "name",
    [
        "../outside",
        "lab-world/../outside",
        "/lab-world/level.dat",
        "lab-world\\outside",
        "lab-world/C:/outside",
        "lab-world/aux.txt",
        "lab-world/bad.",
        "lab-world/bad ",
        "lab-world//bad",
        "other/secret",
        "lab-world/./bad",
        "lab-world/a\x00b",
        "lab-world/a\nb",
    ],
)
def test_unsafe_entries_refused_before_any_output(tmp_path, name):
    lab, archive, dest, digest = fixture(
        tmp_path, [("lab-world/level.dat", b"level"), (name, b"bad")]
    )
    with pytest.raises(ValueError):
        stage_full_world(Mock(poll=lambda: 0), archive, digest, dest, lab=lab)
    assert not dest.exists() and not (lab / "full-return-plan.json").exists()


@pytest.mark.parametrize(
    "extra",
    [
        [("lab-world/LEVEL.DAT", b"duplicate")],
        [("lab-world/a", b"file"), ("lab-world/a/b", b"collision")],
        [("lab-world/A/a", b"first"), ("lab-world/a/b", b"ambiguous")],
    ],
)
def test_cross_platform_collisions_rejected_before_output(tmp_path, extra):
    lab, archive, dest, digest = fixture(
        tmp_path, [("lab-world/level.dat", b"level"), *extra]
    )
    with pytest.raises(ValueError):
        stage_full_world(Mock(poll=lambda: 0), archive, digest, dest, lab=lab)
    assert not dest.exists()


def test_bad_hash_and_symlink_payload_are_rejected(tmp_path):
    lab, archive, dest, digest = fixture(tmp_path)
    with pytest.raises(ValueError, match="hash mismatch"):
        stage_full_world(Mock(poll=lambda: 0), archive, "0" * 64, dest, lab=lab)
    info = ZipInfo("lab-world/link")
    info.create_system = 3
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with ZipFile(archive, "a") as output:
        output.writestr(info, "../../outside")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="Unsafe"):
        stage_full_world(Mock(poll=lambda: 0), archive, digest, dest, lab=lab)
    assert not dest.exists()


def test_disk_failure_preserves_original_and_has_no_completed_marker(
    tmp_path, monkeypatch
):
    lab, archive, dest, digest = fixture(tmp_path)

    def fail_copy(archive, info, target):
        if info.filename.endswith("level.dat"):
            return _copy_entry(archive, info, target)
        raise OSError("synthetic disk full after first file")

    monkeypatch.setattr("omk.recovery_full_lab._copy_entry", fail_copy)
    with pytest.raises(OSError, match="disk full"):
        stage_full_world(Mock(poll=lambda: 0), archive, digest, dest, lab=lab)
    assert archive.exists() and dest.exists()
    assert (dest / "level.dat").read_bytes() == b"synthetic level"
    assert (lab / "full-return-plan.json").exists()
    assert not (lab / "full-return-staged.json").exists()
    with pytest.raises(ValueError, match="empty replacement"):
        stage_full_world(Mock(poll=lambda: 0), archive, digest, dest, lab=lab)


@pytest.mark.parametrize("limit", ["MAX_FILES", "MAX_TOTAL", "MAX_FILE"])
def test_resource_limits_refused_before_any_output(tmp_path, monkeypatch, limit):
    lab, archive, dest, digest = fixture(tmp_path)
    monkeypatch.setattr("omk.recovery_full_lab." + limit, 1)
    with pytest.raises(ValueError):
        stage_full_world(Mock(poll=lambda: 0), archive, digest, dest, lab=lab)
    assert not dest.exists() and not (lab / "full-return-plan.json").exists()


def test_corrupt_zip_crc_cannot_get_completed_marker(tmp_path):
    lab, archive, dest, _ = fixture(tmp_path)
    archive.write_bytes(
        archive.read_bytes().replace(b"synthetic FTB data", b"synthetic ZTB data")
    )
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    with pytest.raises(BadZipFile, match="CRC"):
        stage_full_world(Mock(poll=lambda: 0), archive, digest, dest, lab=lab)
    assert (dest / "level.dat").exists()
    assert not (lab / "full-return-staged.json").exists()


def test_missing_level_or_wrong_destination_are_refused(tmp_path):
    lab, archive, dest, digest = fixture(tmp_path, [("lab-world/data/only", b"x")])
    with pytest.raises(ValueError, match="Missing level"):
        stage_full_world(Mock(poll=lambda: 0), archive, digest, dest, lab=lab)
    with pytest.raises(ValueError, match="replacement"):
        stage_full_world(
            Mock(poll=lambda: 0), archive, digest, lab / "server/lab-world", lab=lab
        )
    assert not dest.exists() and not (lab / "full-return-plan.json").exists()
