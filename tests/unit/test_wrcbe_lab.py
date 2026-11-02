import hashlib
import json
from types import SimpleNamespace

import pytest

from omk import dj2_wrcbe_lab as lab


def inputs(tmp_path, monkeypatch):
    source = tmp_path / "server"
    (source / "mods").mkdir(parents=True)
    for name in ("forge-1.12.2-14.23.5.2860.jar", "core.jar", "agent.jar"):
        (source / name).write_bytes(b"test-only")
    mods = tmp_path / "mods.json"
    mods.write_text(json.dumps({"wrcbe": "2.3.2"}))
    probe = tmp_path / "probe.jar"
    pins = {}
    for label, (filename, _expected) in lab.PINS.items():
        data = ("synthetic " + label).encode()
        (source / "mods" / filename if filename else probe).write_bytes(data)
        pins[label] = (filename, hashlib.sha256(data).hexdigest())
    monkeypatch.setattr(lab, "PINS", pins)
    return SimpleNamespace(
        server_source=source,
        core=source / "core.jar",
        agent=source / "agent.jar",
        mods_json=mods,
        probe=probe,
        cycles=3,
    )


@pytest.mark.parametrize("cycles", [0, 6, True, "3"])
def test_invalid_cycles_rejected_before_filesystem_access(cycles):
    with pytest.raises(ValueError, match="cycles"):
        lab.validate_inputs(SimpleNamespace(cycles=cycles))


def test_explicit_artifacts_are_checked_without_creating_a_lab(tmp_path, monkeypatch):
    args = inputs(tmp_path, monkeypatch)
    before = set(tmp_path.rglob("*"))
    assert lab.validate_inputs(args) == {key: row[1] for key, row in lab.PINS.items()}
    assert set(tmp_path.rglob("*")) == before


def test_unknown_pack_rejected_before_filesystem_access():
    with pytest.raises(ValueError, match="Unknown reviewed"):
        lab.validate_inputs(SimpleNamespace(cycles=3, pack_version="unreviewed"))


def test_candidate_uses_its_own_exact_pin_and_rejects_mutation(tmp_path, monkeypatch):
    args = inputs(tmp_path, monkeypatch)
    old_name, digest = lab.PINS["mixinbooter"]
    candidate_name = "!mixinbooter-candidate.jar"
    (args.server_source / "mods" / old_name).rename(
        args.server_source / "mods" / candidate_name
    )
    monkeypatch.setattr(
        lab,
        "PIN_OVERRIDES",
        {"2.21.3": {}, "2.23.4": {"mixinbooter": (candidate_name, digest)}},
    )
    args.pack_version = "2.23.4"
    assert lab.validate_inputs(args)["mixinbooter"] == digest
    args.pack_version = "2.21.3"
    with pytest.raises(ValueError, match="Missing or invalid"):
        lab.validate_inputs(args)
    args.pack_version = "2.23.4"
    (args.server_source / "mods" / candidate_name).write_bytes(b"changed candidate")
    with pytest.raises(ValueError, match="hash mismatch"):
        lab.validate_inputs(args)


@pytest.mark.parametrize("label", ["wrcbe", "mixinbooter", "probe"])
def test_corrupt_pin_rejected_without_echoing_payload(tmp_path, monkeypatch, label):
    args = inputs(tmp_path, monkeypatch)
    name = lab.PINS[label][0]
    target = args.server_source / "mods" / name if name else args.probe
    target.write_bytes(b"synthetic-secret-content")
    with pytest.raises(ValueError, match="hash mismatch") as error:
        lab.validate_inputs(args)
    assert "synthetic-secret-content" not in str(error.value)


def test_bad_mod_policy_rejected_before_lab_creation(tmp_path, monkeypatch):
    args = inputs(tmp_path, monkeypatch)
    args.mods_json.write_text('{"bad\\nmod":"version"}')
    with pytest.raises(ValueError, match="mod entry"):
        lab.validate_inputs(args)


def test_unlisted_probe_request_never_reaches_shell():
    scenario = lab.WrcbeScenario(SimpleNamespace(), {})
    with pytest.raises(ValueError, match="Unknown"):
        scenario.request("check; echo injected")


def test_probe_response_is_bounded():
    server = SimpleNamespace(helper=lambda _script: SimpleNamespace(stdout="x" * 8193))
    with pytest.raises(ValueError, match="Oversized"):
        lab.WrcbeScenario(server, {}).result()
