"""Test dependencies for project stage."""

import copy
from types import SimpleNamespace

import pytest

from omk.distribution import component_archive as archive
from omk.owner.storage import project_export
from tests.fixtures.unit.storage.project_export import (
    clients as client_fixture,
    fixture as capture_fixture,
)


@pytest.fixture
def prepared(tmp_path):
    clients = client_fixture.__wrapped__(tmp_path)
    base = capture_fixture.__wrapped__(tmp_path, clients)
    # Distinct Linux names and executable mode are essential runtime properties.
    game = base.args["game"]
    (game / "config/Case").mkdir()
    (game / "config/case").mkdir()
    (game / "config/Case/value.cfg").write_bytes(b"upper")
    (game / "config/case/value.cfg").write_bytes(b"lower")
    context = {
        "source_commit": "1" * 40,
        "client_manifests": {
            "windows-x64": clients.snapshots["windows-x64"].release.digest
        },
        "declared_state_contract": "fixture-world-v1",
    }
    result = project_export.capture(
        base.out, release_context=context, **base.client_args, **base.args
    )
    target = tmp_path / "stage"
    target.mkdir(mode=0o700)
    selection = {
        "project_sha256": archive.digest(base.out / "project.json"),
        "release_identity": copy.deepcopy(result["manifest"]["release_identity"]),
    }
    args = {
        "operation": "d" * 32,
        "world": "lab-world",
        "selection": selection,
        "settings": copy.deepcopy(base.args["settings"]),
    }
    return SimpleNamespace(base=base, source=base.out, target=target, args=args)
