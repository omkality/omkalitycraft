"""Test dependencies for project return."""

import copy
from types import SimpleNamespace

import pytest

from omk.owner.storage import project_return as journal


@pytest.fixture
def operation(policy_prepared):
    p = policy_prepared
    private = p.target.parent / ".omk-admin"
    private.mkdir(mode=0o700)
    p.target = p.target.parent / "fresh-return"
    p.target.mkdir(mode=0o700)
    p.config = SimpleNamespace(private=private, servers={"dj2": p.current})
    p.fence = {"source": "stopped-owned-source", "target": "empty-owned-target"}
    result = journal.plan(
        p.config,
        "dj2",
        p.source,
        p.target,
        p.current,
        world="lab-world",
        selection=p.raw["selection"],
        settings=p.raw["settings"],
        checkpoint=lambda: copy.deepcopy(p.fence),
    )
    p.operation = result["operation"]
    return p
