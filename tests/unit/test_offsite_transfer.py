import copy
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from omk import offsite_transfer as jobs
from omk.offsite_process import OffsiteError, bounded
from omk.restic_transport import policy

LINUX = pytest.mark.skipif(sys.platform != "linux", reason="Linux owner service")
OP = "a" * 32


@dataclass
class Client:
    workspace: Path
    settings: dict
    repository_id: str = "b" * 64
    lease_fd: int | None = None
    state: dict = field(default_factory=dict)

    def validate(self):
        pass

    def upload(self, source, operation, *, expected=None):
        self.state["uploads"] = self.state.get("uploads", 0) + 1
        assert os.fstat(self.lease_fd).st_size == 1
        receipt = {
            "snapshot_id": "c" * 64,
            "operation": operation,
            "repository_id": self.repository_id,
            "export": expected,
            "data_read_back": False,
        }
        self.state["receipt"] = receipt
        if self.state.get("cut"):
            raise OffsiteError("lost upload acknowledgement")
        return receipt

    def find(self, operation, expected):
        self.state["finds"] = self.state.get("finds", 0) + 1
        return self.state.get("receipt")

    def restore(self, receipt):
        self.state["restores"] = self.state.get("restores", 0) + 1
        if self.state.get("bad_restore"):
            raise OffsiteError("missing restored bytes")
        return {
            **receipt,
            "data_read_back": True,
            "restored_directory": str(self.workspace / "isolated"),
            "ready_for_players": False,
        }


@pytest.fixture
def prepared(tmp_path):
    if sys.platform != "linux":
        pytest.skip("Linux owner service")
    source = tmp_path / "input"
    source.mkdir()
    (source / "closed.zip").write_bytes(b"sealed test fixture")
    workspace = tmp_path / "work"
    workspace.mkdir(mode=0o700)
    client = Client(workspace, {**policy({}), "reserve_bytes": 0})
    store = jobs.TransferStore.create(tmp_path / "jobs")
    record = store.prepare(client, source, OP)
    return store, client, source, record


def test_normal_transfer_requires_readback_and_is_idempotent(prepared):
    store, client, _, _ = prepared
    r = store.run(client, OP)
    assert r["stage"] == "verified" and r["receipt"]["data_read_back"]
    assert not r["receipt"]["ready_for_players"]
    assert store.run(client, OP) == r
    assert store.status(client, OP) == r
    assert client.state["uploads"] == client.state["restores"] == 1


def test_lost_ack_resumes_same_identity_only_after_readback(prepared):
    store, client, _, _ = prepared
    client.state["cut"] = True
    with pytest.raises(OffsiteError, match="lost"):
        store.run(client, OP)
    assert store.status(client, OP)["stage"] == "attempted"
    with pytest.raises(OffsiteError, match="already attempted"):
        store.run(client, OP)
    restarted = jobs.TransferStore(store.root)
    r = restarted.run(client, OP, recover=True)
    assert r["stage"] == "verified" and client.state["uploads"] == 1


def test_attempted_without_snapshot_never_reuploads(prepared):
    store, client, _, record = prepared
    with store.lock():
        store.transition(record, "attempted")
    for _ in range(2):
        with pytest.raises(OffsiteError, match="without retry"):
            store.run(client, OP, recover=True)
    assert "uploads" not in client.state


def test_recovery_of_prepared_does_not_start_upload(prepared):
    store, client, _, _ = prepared
    with pytest.raises(OffsiteError, match="never starts"):
        store.run(client, OP, recover=True)
    assert not client.state


def test_bad_readback_never_marks_verified_and_can_be_reinspected(prepared):
    store, client, _, _ = prepared
    client.state["bad_restore"] = True
    with pytest.raises(OffsiteError, match="missing"):
        store.run(client, OP)
    assert store.status(client, OP)["stage"] == "uploaded"
    client.state["bad_restore"] = False
    assert store.run(client, OP, recover=True)["stage"] == "verified"
    assert client.state["uploads"] == 1


@pytest.mark.parametrize(
    "changed", ["content", "entry", "repository", "workspace", "settings"]
)
def test_scope_drift_refuses_before_effects(prepared, changed):
    store, client, source, _ = prepared
    if changed == "content":
        (source / "closed.zip").write_bytes(b"changed")
    elif changed == "entry":
        (source / "extra.zip").write_bytes(b"new")
    elif changed == "repository":
        client = replace(client, repository_id="d" * 64)
    elif changed == "workspace":
        client = replace(client, workspace=client.workspace / "foreign")
    else:
        client = replace(client, settings={**client.settings, "max_bytes": 999})
    with pytest.raises(OffsiteError):
        store.run(client, OP)
    assert not client.state


def test_same_process_separate_open_is_fenced(prepared):
    store, client, _, _ = prepared
    with store.lock(), pytest.raises(OffsiteError, match="busy"):
        jobs.TransferStore(store.root).run(client, OP)
    assert not client.state


def test_duplicate_identity_is_not_replaced(prepared):
    store, client, source, _ = prepared
    before = store.path(OP).read_bytes()
    with pytest.raises(OffsiteError, match="reserved"):
        store.prepare(client, source, OP)
    assert store.path(OP).read_bytes() == before


@pytest.mark.parametrize(
    "changed", ["oversize", "hardlink", "public", "temp", "schema", "receipt"]
)
def test_unsafe_journal_refuses_before_effects(prepared, changed):
    store, client, _, record = prepared
    p = store.path(OP)
    if changed == "oversize":
        p.write_bytes(b"x" * (jobs.MAX_RECORD + 1))
    elif changed == "hardlink":
        os.link(p, store.root / ("d" * 32 + ".json"))
    elif changed == "public":
        p.chmod(0o644)
    elif changed == "temp":
        (store.root / ".transfer-interrupted.tmp").write_bytes(b"old partial")
    else:
        r = copy.deepcopy(record)
        r["schema"] = 9 if changed == "schema" else 1
        if changed == "receipt":
            r["receipt"] = {"unexpected": True}
        p.write_text(json.dumps(r))
    with pytest.raises(OffsiteError):
        store.run(client, OP)
    assert not client.state


def test_capacity_stops_before_preparation_and_preserves_records(prepared):
    store, client, source, _ = prepared
    small = jobs.TransferStore(
        store.root, bounds={"records": 1, "bytes": jobs.MAX_RECORD}
    )
    old = store.path(OP).read_bytes()
    with pytest.raises(OffsiteError, match="capacity"):
        small.prepare(client, source, "d" * 32)
    assert store.path(OP).read_bytes() == old
    assert small.run(client, OP)["stage"] == "verified"


def test_reserve_rechecked_before_attempt_and_effect(prepared, monkeypatch):
    store, client, _, _ = prepared
    monkeypatch.setattr(jobs.shutil, "disk_usage", lambda p: SimpleNamespace(free=1))
    with pytest.raises(OffsiteError, match="reserve"):
        store.run(client, OP)
    assert store.status(client, OP)["stage"] == "prepared" and not client.state


def test_snapshot_identity_cannot_change_during_recovery(prepared):
    store, client, _, _ = prepared
    client.state["bad_restore"] = True
    with pytest.raises(OffsiteError):
        store.run(client, OP)
    client.state["receipt"] = {**client.state["receipt"], "snapshot_id": "d" * 64}
    with pytest.raises(OffsiteError, match="snapshot changed"):
        store.run(client, OP, recover=True)
    assert store.status(client, OP)["stage"] == "uploaded"


@pytest.mark.parametrize(
    "key,value",
    [
        ("RECORDS", "0"),
        ("RECORDS", "10001"),
        ("BYTES", "1"),
        ("BYTES", "-1"),
        ("BYTES", "x"),
    ],
)
def test_invalid_limits_refuse(key, value):
    with pytest.raises(OffsiteError):
        jobs.limits({"OMK_OFFSITE_JOB_MAX_" + key: value})


@LINUX
def test_child_keeps_flock_after_parent_copy_closes(tmp_path):
    store = jobs.TransferStore.create(tmp_path / "jobs")
    marker = tmp_path / "ready"
    release = tmp_path / "release"
    with store.lock() as fd:
        child = subprocess.Popen(
            [
                sys.executable,
                "-c",
                "from pathlib import Path;import sys,time;Path(sys.argv[1]).touch();"
                "exec('while not Path(sys.argv[2]).exists(): time.sleep(.01)')",
                str(marker),
                str(release),
            ],
            pass_fds=(fd,),
        )
        until = time.monotonic() + 5
        while not marker.exists():
            assert time.monotonic() < until
            time.sleep(0.01)
    try:
        with pytest.raises(OffsiteError, match="busy"), store.lock():
            pytest.fail("Orphan child lost its fence")
    finally:
        release.touch()
        child.wait(timeout=5)
    with store.lock():
        pass


@LINUX
def test_bounded_child_inherits_only_explicit_descriptor(tmp_path):
    store = jobs.TransferStore.create(tmp_path / "jobs")
    with store.lock() as fd:
        output = bounded(
            [sys.executable, "-c", f"import os;print(os.fstat({fd}).st_size)"],
            environment=os.environ.copy(),
            directory=tmp_path,
            timeout=5,
            maximum=1024,
            inherited=(fd,),
        )
    assert output == b"1\n"


def test_transfer_module_is_standard_library_only():
    p = subprocess.run(
        [
            sys.executable,
            "-S",
            "-c",
            "import omk.offsite_transfer;import sys;assert 'psutil' not in sys.modules",
        ],
        capture_output=True,
        check=False,
        timeout=10,
    )
    assert p.returncode == 0
