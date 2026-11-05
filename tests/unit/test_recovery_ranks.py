import io
import tarfile
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace

import pytest

from omk.recovery_lab import RecoveryRuntime, _validate_inputs
from omk.recovery_ranks_lab import RANKS, read_ranks, stage_ranks

CURRENT = b"[player]\nftbutilities.homes.max: 1\n"
DEFAULT = b"[player]\nftbutilities.homes.max: 3\n"


def fixture(tmp_path, entries=None):
    lab = tmp_path / "recovery-lab-ranks"
    source = lab / "current-ranks-before"
    source.mkdir(parents=True)
    archive = source / "ranks.tar"
    target = lab / "recovery-lab-return/server"
    (target / RANKS).parent.mkdir(parents=True)
    (target / RANKS).write_bytes(DEFAULT)
    for marker in ("full-return-staged.json", "current-access-staged.json"):
        (lab / marker).write_text("{}")
    with tarfile.open(archive, "w") as tar:
        for name, data in entries if entries is not None else [(RANKS, CURRENT)]:
            item = tarfile.TarInfo(name)
            item.size = len(data)
            tar.addfile(item, io.BytesIO(data))
    return lab, archive, target


def test_current_definitions_replace_only_fresh_default_with_exact_bytes(tmp_path):
    lab, archive, target = fixture(tmp_path)
    before = archive.read_bytes()
    (target / "server.properties").write_bytes(b"unchanged configuration")
    result = stage_ranks(archive, target, lab=lab)
    assert (target / RANKS).read_bytes() == CURRENT
    assert archive.read_bytes() == before
    assert (target / "server.properties").read_bytes() == b"unchanged configuration"
    assert result["source_sha256"] != result["replacement_default_sha256"]
    assert not result["historical_memberships_reconciled"]
    assert (lab / "current-ranks-staged.json").exists()
    with pytest.raises(FileExistsError):
        stage_ranks(archive, target, lab=lab)


@pytest.mark.parametrize(
    "entries",
    [
        [],
        [("../ranks.txt", CURRENT)],
        [(RANKS, CURRENT), (RANKS, CURRENT)],
        [(RANKS, CURRENT), ("other.conf", b"never copy")],
        [(RANKS, b"\0secret")],
        [(RANKS, b"\xffsecret")],
        [(RANKS, b" \n")],
    ],
)
def test_bad_rank_archive_does_not_change_default_or_publish_marker(tmp_path, entries):
    lab, archive, target = fixture(tmp_path, entries)
    with pytest.raises(ValueError) as error:
        stage_ranks(archive, target, lab=lab)
    assert "secret" not in str(error.value)
    assert (target / RANKS).read_bytes() == DEFAULT
    assert not (lab / "current-ranks-plan.json").exists()
    assert not (lab / "current-ranks-staged.json").exists()


@pytest.mark.parametrize("kind", [tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.DIRTYPE])
def test_rank_archive_links_and_directories_refused(tmp_path, kind):
    _, archive, _ = fixture(tmp_path)
    with tarfile.open(archive, "w") as tar:
        item = tarfile.TarInfo(RANKS)
        item.type, item.linkname = kind, "outside"
        tar.addfile(item)
    with pytest.raises(ValueError, match="entry"):
        read_ranks(archive)


def test_rank_file_size_bounded_before_copy(tmp_path, monkeypatch):
    lab, archive, target = fixture(tmp_path, [(RANKS, b"x" * 65537)])
    monkeypatch.setattr("omk.recovery_ranks_lab.MAX_FILE", 65536)
    with pytest.raises(ValueError, match="entry"):
        stage_ranks(archive, target, lab=lab)
    assert (target / RANKS).read_bytes() == DEFAULT


@pytest.mark.parametrize(
    "missing", ["full-return-staged.json", "current-access-staged.json"]
)
def test_world_and_access_staging_required_before_rank_copy(tmp_path, missing):
    lab, archive, target = fixture(tmp_path)
    (lab / missing).unlink()
    with pytest.raises(ValueError, match="untouched disposable"):
        stage_ranks(archive, target, lab=lab)
    assert (target / RANKS).read_bytes() == DEFAULT


def test_original_runtime_cannot_be_overwritten(tmp_path):
    lab, archive, _ = fixture(tmp_path)
    original = lab / "server"
    (original / RANKS).parent.mkdir(parents=True)
    (original / RANKS).write_bytes(b"original policy")
    with pytest.raises(ValueError, match="untouched disposable"):
        stage_ranks(archive, original, lab=lab)
    assert (original / RANKS).read_bytes() == b"original policy"


def test_replace_failure_keeps_default_and_never_allows_replacement_start(
    tmp_path, monkeypatch
):
    lab, archive, target = fixture(tmp_path)

    def fail(*args):
        raise OSError("controlled replace failure")

    monkeypatch.setattr("omk.recovery_ranks_lab.os.replace", fail)
    with pytest.raises(OSError):
        stage_ranks(archive, target, lab=lab)
    assert (target / RANKS).read_bytes() == DEFAULT
    assert not (lab / "current-ranks-staged.json").exists()
    runtime = RecoveryRuntime(
        Namespace(access_policy=True, rank_policy=True), lab, None, None, {}, None, None
    )
    runtime.linux = SimpleNamespace()
    runtime.server = SimpleNamespace(poll=lambda: 0)
    with pytest.raises(ValueError, match="staged empty"):
        runtime.start(target)


def test_partial_write_keeps_default_without_ready_marker(tmp_path, monkeypatch):
    lab, archive, target = fixture(tmp_path)
    original = Path.open

    def fail(path, *args, **kwargs):
        if path.name == "ranks.txt.current-policy" and args == ("xb",):
            raise OSError("controlled disk failure")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fail)
    with pytest.raises(OSError):
        stage_ranks(archive, target, lab=lab)
    assert (target / RANKS).read_bytes() == DEFAULT
    assert not (lab / "current-ranks-staged.json").exists()


def test_changed_source_ranks_do_not_authorize_original_volume_cleanup(tmp_path):
    def expect(ok, name):
        if not ok:
            raise AssertionError(name)

    runtime = RecoveryRuntime(
        Namespace(access_policy=True, rank_policy=True),
        tmp_path,
        None,
        None,
        {"current_ranks": {"source_sha256": "before"}},
        None,
        expect,
    )
    runtime.export_current_ranks = lambda label: (None, "changed")
    with pytest.raises(AssertionError, match="source_file_unchanged"):
        runtime.verify_current_access_source()
    assert not runtime.access_verified


def test_rank_policy_requires_access_policy_before_reading_inputs():
    with pytest.raises(ValueError, match="Rank policy requires"):
        _validate_inputs(Namespace(rank_policy=True, access_policy=False))


def test_linked_rank_parent_cannot_escape_fresh_runtime(tmp_path):
    lab, archive, target = fixture(tmp_path)
    (target / RANKS).unlink()
    (target / RANKS).parent.rmdir()
    outside = lab / "outside"
    outside.mkdir()
    (outside / "ranks.txt").write_bytes(b"outside data")
    try:
        (target / RANKS).parent.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Directory symlinks unavailable")
    with pytest.raises(ValueError, match="untouched disposable"):
        stage_ranks(archive, target, lab=lab)
    assert (outside / "ranks.txt").read_bytes() == b"outside data"
