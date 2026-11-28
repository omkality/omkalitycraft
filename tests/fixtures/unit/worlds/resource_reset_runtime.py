"""Test dependencies for resource reset runtime."""

import pytest

from omk.worlds.reset import (
    resource_reset_runtime as runtime,
    resource_reset_stage as stage,
)
from tests.fixtures.unit.backups.ftb_restore_authority import records
from tests.fixtures.unit.worlds.resource_reset_inventory import sample
from tests.fixtures.unit.worlds.resource_reset_stage import data

__all__ = ["data", "records", "sample"]


@pytest.fixture
def prepared(data):
    request, source, storage, target, _ = data
    (source / "server.properties").write_text(
        "level-name=world\nlevel-seed=\nwhite-list=true\nrcon.password=fixture-only\n"
    )
    (source / "eula.txt").write_text("# Already accepted in source\neula=true\n")
    for name in runtime.LISTS:
        (source / name).write_text(
            "[]\n" if name == "ops.json" else '[{"uuid":"fixture"}]\n'
        )
    for name in (
        ".omk/authlib-injector.jar",
        ".omk/log4j2.xml",
        "libraries/logging.jar",
        "local/ftbutilities/ranks.txt",
        "structures/active/ae2_atum_underground_meteor.rcst",
        "structures/active/ae2_atum_underground_meteor.rcgp",
        "structures/active/ae2_atum_meteor_chest_presses.rcig",
    ):
        p = source / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"fixture-payload")
    (source / "logs").mkdir()
    (source / "logs/private.log").write_bytes(b"never-copy")
    plan = stage.execute({**request, "action": "plan"}, source, storage, target)
    request = {**request, "expected": plan}
    stage.execute({**request, "action": "stage"}, source, storage, target)
    expected = runtime.execute(
        {**request, "action": "runtime-plan"}, source, storage, target
    )
    return {**request, "runtime_expected": expected}, source, storage, target
