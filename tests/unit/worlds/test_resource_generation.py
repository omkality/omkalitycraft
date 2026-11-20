"""Synthetic configs: preserve gameplay settings and refuse unreviewed inputs."""

import copy
import json

import pytest

from omk.cli import main
from omk.worlds.resource_generation import (
    PROFILE,
    additional_generator_patches,
    forge_fields,
)
from omk.worlds.resource_policy import prepare_resource_bundle
from tests.fixtures.unit.worlds.resource_generation import source_fixture

__all__ = ["source_fixture"]


def test_all_memberships_preserve_settings_and_source(tmp_path):
    source = source_fixture(tmp_path / "config")
    before = {
        p.relative_to(source).as_posix(): p.read_bytes()
        for p in source.rglob("*")
        if p.is_file()
    }
    patches, metadata = additional_generator_patches(source, -18000)
    assert len(patches) == 5 and len(metadata) == 8
    for relative, raw in before.items():
        assert (source / relative).read_bytes() == raw
    cofh = "cofh/world/01_thermalfoundation_ores.json"
    expected = json.loads(before[cofh])
    for name in ["oil_ore", "amber", "aquamarine"]:
        expected["populate"][name]["dimension"]["value"].append(-18000)
    assert json.loads(patches[cofh]) == expected
    for item in json.loads(PROFILE.read_text())["forge_files"]:
        relative = item["file"]
        assert (
            patches[relative]
            .replace(b"    -18000\r\n", b"")
            .replace(b"    omk_resource\r\n", b"")
            == before[relative]
        )
        _, fields = forge_fields(patches[relative].decode())
        for rule in item["rules"]:
            assert fields[tuple(rule["path"])]["values"] == [
                rule["reference"],
                "-18000" if rule["kind"] == "I" else "omk_resource",
            ]
    # A second pass produces no extra memberships or byte changes.
    for relative, raw in patches.items():
        (source / relative).write_bytes(raw)
    again, meta = additional_generator_patches(source, -18000)
    assert not again
    assert all(x["source_sha256"] == x["output_sha256"] for x in meta)


@pytest.mark.parametrize(
    "mutation",
    [
        "unknown_feature",
        "missing_reference",
        "wrong_mode",
        "duplicate_json",
        "top_list",
        "top_null",
        "nan",
        "bad_ids",
        "missing_file",
        "bad_forge",
        "duplicate_forge",
    ],
)
def test_invalid_inputs_refuse_before_any_bundle_write(tmp_path, mutation):
    source = source_fixture(tmp_path / "config")
    cofh = source / "cofh/world/01_thermalfoundation_ores.json"
    obj = json.loads(cofh.read_text())
    if mutation == "unknown_feature":
        obj["populate"]["new"] = copy.deepcopy(obj["populate"]["amber"])
    elif mutation == "missing_reference":
        obj["populate"]["amber"]["dimension"]["value"] = [7]
    elif mutation == "bad_ids":
        obj["populate"]["amber"]["dimension"]["value"] = [False, 0]
    cofh.write_text(json.dumps(obj))
    if mutation == "duplicate_json":
        cofh.write_text('{"populate": {}, "populate": {}}')
    elif mutation == "top_list":
        cofh.write_text("[]")
    elif mutation == "top_null":
        cofh.write_text("null")
    elif mutation == "nan":
        cofh.write_text('{"populate": {}, "invalid": NaN}')
    elif mutation == "wrong_mode":
        path = source / "Extreme Reactors/Extreme Reactors.cfg"
        path.write_bytes(
            path.read_bytes().replace(b"useBlacklist=false", b"useBlacklist=true")
        )
    elif mutation == "missing_file":
        (source / "natura.cfg").unlink()
    elif mutation == "bad_forge":
        (source / "natura.cfg").write_text("broken unknown syntax")
    elif mutation == "duplicate_forge":
        path = source / "natura.cfg"
        path.write_bytes(path.read_bytes() + path.read_bytes())
    with pytest.raises(ValueError):
        prepare_resource_bundle(tmp_path / "out", {}, source_config=source)
    assert not (tmp_path / "out").exists()


def test_bundle_includes_reviewed_generation_copies_and_hashes(tmp_path):
    source = source_fixture(tmp_path / "config")
    result = prepare_resource_bundle(tmp_path / "bundle", {}, source_config=source)
    assert len(result["plan"]["generation_patches"]) == 9
    assert (tmp_path / "bundle/config/natura.cfg").is_file()
    assert not (tmp_path / "bundle/config/cofh/world/00_minecraft.json").exists()


def test_readonly_cli_reviews_generation_without_writes(tmp_path, monkeypatch, capsys):
    source = source_fixture(tmp_path / "config")
    monkeypatch.chdir(tmp_path)
    assert main(["policy", "dj2-resource", "--source-config", str(source)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert (
        result["writes"] is False and len(result["policy"]["generation_patches"]) == 9
    )
    assert sorted(p.name for p in tmp_path.iterdir()) == ["config"]
