from argparse import Namespace

import pytest

from omk.recovery_lab import _validate_inputs
from omk.recovery_mod_systems_lab import PINS, bank_energy


@pytest.mark.parametrize(
    "runtime,edges,full",
    [
        ("native", False, False),
        ("linux-docker", True, False),
        ("linux-docker", False, True),
    ],
)
def test_incompatible_suites_are_rejected_before_reading_artifacts(
    runtime, edges, full
):
    with pytest.raises(ValueError, match="without other recovery suites"):
        _validate_inputs(
            Namespace(
                mod_systems=True,
                runtime=runtime,
                edge_cases=edges,
                full_backup_return=full,
            )
        )


def test_changed_pack_jar_is_rejected_before_lab_creation(tmp_path):
    mods = tmp_path / "mods"
    mods.mkdir()
    for name in PINS:
        (mods / name).write_bytes(b"untrusted different artifact")
    with pytest.raises(ValueError, match="Unpinned mod systems"):
        _validate_inputs(
            Namespace(
                mod_systems=True,
                runtime="linux-docker",
                edge_cases=False,
                full_backup_return=False,
                server_source=tmp_path,
            )
        )


@pytest.mark.parametrize("value", [0, 239000, 500000])
def test_bank_energy_reads_the_single_bounded_saved_value(value):
    assert (
        bank_energy(f"The data tag did not change: {{energyStored:{value},x:168}}")
        == value
    )


@pytest.mark.parametrize(
    "text",
    [
        "no tile",
        "energyStored:-1}",
        "energyStored:500001}",
        "energyStored:99999999999999999999}",
        "energyStored:0} energyStored:0}",
    ],
)
def test_bad_or_ambiguous_energy_output_cannot_be_a_positive_control(text):
    with pytest.raises(ValueError, match="Missing, ambiguous or invalid"):
        bank_energy(text)
