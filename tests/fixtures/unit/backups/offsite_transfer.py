"""Test dependencies for offsite transfer."""

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from omk.backups import offsite_transfer as jobs
from omk.backups.offsite_process import OffsiteError
from omk.backups.restic_transport import policy

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
