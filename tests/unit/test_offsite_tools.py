import bz2
import hashlib
import io
import tarfile

import pytest

from scripts import fetch_offsite_tools as tools


def artifact(name, raw, binary):
    return {
        "name": name,
        "download_sha256": hashlib.sha256(raw).hexdigest(),
        "binary_sha256": hashlib.sha256(binary).hexdigest(),
        "binary_bytes": len(binary),
    }


def test_pinned_restic_decompresses_exactly():
    binary = b"fixed Linux binary fixture"
    raw = bz2.compress(binary)
    assert tools.decode(artifact("restic", raw, binary), raw) == binary


@pytest.mark.parametrize("change", ["download", "binary", "size", "trailing-stream"])
def test_changed_tool_material_is_refused(change):
    binary = b"fixed"
    raw = bz2.compress(binary)
    pin = artifact("restic", raw, binary)
    if change == "download":
        raw += b"changed"
    elif change == "binary":
        pin["binary_sha256"] = "0" * 64
    elif change == "size":
        pin["binary_bytes"] = 1
    else:
        raw += bz2.compress(binary)
        pin["download_sha256"] = hashlib.sha256(raw).hexdigest()
    with pytest.raises(ValueError):
        tools.decode(pin, raw)


@pytest.mark.parametrize("kind", ["regular", "duplicate", "symlink", "too-many"])
def test_tar_is_read_without_extracting_member_paths(tmp_path, kind):
    binary = b"fixed server"
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode="w:gz") as archive:
        for i in range(33 if kind == "too-many" else 2 if kind == "duplicate" else 1):
            entry = tarfile.TarInfo(
                ("../outside" if i == 0 else "second") + "/rest-server"
            )
            entry.size = len(binary)
            if kind == "symlink":
                entry.type = tarfile.SYMTYPE
                entry.linkname = "/outside"
            archive.addfile(entry, io.BytesIO(binary) if entry.isfile() else None)
    raw = out.getvalue()
    pin = artifact("rest-server", raw, binary)
    if kind == "regular":
        assert tools.decode(pin, raw) == binary
    else:
        with pytest.raises(ValueError):
            tools.decode(pin, raw)
    assert not list(tmp_path.iterdir())
