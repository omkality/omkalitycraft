import hashlib
import json

import pytest

import omk.resource_policy as policy
from omk.cli import main
from omk.resource_policy import jed_dimension, prepare_resource_bundle, resource_plan
from omk.stopped_world_backup import inventory
from tests.unit.test_resource_generation import source_fixture


def test_policy_bundle_is_offline_exclusive_and_hash_complete(tmp_path):
    output = tmp_path / "candidate"
    manifest = prepare_resource_bundle(output, {"OMK_DJ2_RESOURCE_SEED": "12345"})
    assert manifest["complete"] and not manifest["world_changes"]
    assert not manifest["plan"]["ready_for_players"]
    for name, digest in manifest["files"].items():
        assert hashlib.sha256((output / name).read_bytes()).hexdigest() == digest
    before = (output / "bundle.json").read_bytes()
    with pytest.raises(FileExistsError):
        prepare_resource_bundle(output, {})
    assert (output / "bundle.json").read_bytes() == before
    config = output / "config"
    assert "RandomSeed" in (config / "justenoughdimensions/dimensions.json").read_text()
    assert (
        "-18000:surface:1:250" in (config / "omkalitycore-rtp.properties").read_text()
    )
    assert (
        "0:-300:300:-300:300;-18000:-100:100:-100:100"
        in (config / "omkalitycore-spawn.properties").read_text()
    )
    assert (
        "regions_per_member=3"
        in (config / "omkalitycore-territories.properties").read_text()
    )


@pytest.mark.parametrize(
    "dimension", ["0", "-1", "1", "-100", "-9999", "-11325", "-32001", "junk"]
)
def test_bad_or_reserved_dimension_never_creates_bundle(tmp_path, dimension):
    with pytest.raises(ValueError):
        prepare_resource_bundle(
            tmp_path / "out", {"OMK_DJ2_RESOURCE_DIMENSION": dimension}
        )
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize(
    "key,value",
    [
        ("OMK_DJ2_RESOURCE_SEED", "9223372036854775808"),
        ("OMK_DJ2_RESOURCE_SEED", "-9223372036854775809"),
        ("OMK_DJ2_RESOURCE_DIAMETER", "100001"),
        ("OMK_DJ2_RESOURCE_DIAMETER", "512"),
        ("OMK_DJ2_RESOURCE_SPAWN_RADIUS", "0"),
        ("OMK_DJ2_RTP_MIN_DISTANCE", "6000"),
        ("OMK_DJ2_TERRITORIES_PER_MEMBER", "0"),
        ("OMK_DJ2_RESOURCE_SEARCH_CHUNK_LOADS", "15"),
        ("OMK_DJ2_RESOURCE_SEARCH_CHUNK_LOADS", "65"),
    ],
)
def test_inconsistent_policy_rejected_before_directory_creation(tmp_path, key, value):
    with pytest.raises(ValueError):
        prepare_resource_bundle(tmp_path / "out", {key: value})
    assert not (tmp_path / "out").exists()


def test_jed_options_do_not_override_or_automatically_wipe_worlds():
    plan = resource_plan({})
    dimension = jed_dimension(plan)["dimensions"][0]
    assert dimension["dim"] == -18000
    assert not dimension["override"] and not dimension["unregister"]
    assert not dimension["temporary_dimension"]
    assert not dimension["dimensiontype"]["keeploaded"]
    assert dimension["dimensiontype"]["require_exact_match"]
    assert not dimension["dimensiontype"]["allow_different_id"]
    assert (
        "world_template" not in dimension and "post_deletion_command" not in dimension
    )
    assert dimension["worldinfo_onetime"]["generatorName"] == "default"
    assert dimension["jed"]["RespawnDimension"] == 0


def test_duplicate_resource_dimension_in_operator_rtp_profile_rejected(tmp_path):
    profile = tmp_path / "rtp.json"
    profile.write_text(
        json.dumps(
            {
                "version": 1,
                "worlds": [{"id": -18000, "mode": "surface", "min_y": 1, "max_y": 250}],
            }
        )
    )
    with pytest.raises(ValueError, match="conflicts"):
        prepare_resource_bundle(tmp_path / "out", {"OMK_DJ2_RTP_PROFILE": str(profile)})
    assert not (tmp_path / "out").exists()


def test_partial_bundle_has_no_completion_marker(tmp_path, monkeypatch):
    def fail(*args, **kwargs):
        raise OSError("synthetic disk failure")

    monkeypatch.setattr(policy, "write_rtp_policy", fail)
    output = tmp_path / "out"
    with pytest.raises(OSError):
        prepare_resource_bundle(output, {})
    assert output.is_dir() and not (output / "bundle.json").exists()
    with pytest.raises(FileExistsError):
        prepare_resource_bundle(output, {})


def test_readonly_cli_plan_does_not_create_files(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["policy", "dj2-resource"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["writes"] is False and result["policy"]["dimension"] == -18000
    assert list(tmp_path.iterdir()) == []


def test_generator_patch_preserves_source_and_existing_settings(tmp_path):
    source = tmp_path / "source"
    source_fixture(source)
    raw = b"general {\r\n S:IncludedDimensions=0,7\r\n B:OreGeneration=true\r\n}\r\n"
    original = source / "undergroundbiomes.cfg"
    original.write_bytes(raw)
    out = tmp_path / "out"
    manifest = prepare_resource_bundle(out, {}, source_config=source)
    expected = raw.replace(b"IncludedDimensions=0,7", b"IncludedDimensions=0,7,-18000")
    assert original.read_bytes() == raw
    assert (out / "config/undergroundbiomes.cfg").read_bytes() == expected
    assert (
        manifest["plan"]["generator_patch"]["source_sha256"]
        == hashlib.sha256(raw).hexdigest()
    )
    plan, metadata = policy.resource_generator_patch(out / "config", -18000)
    assert plan.encode() == expected
    assert metadata["source_sha256"] == metadata["output_sha256"]


@pytest.mark.parametrize(
    "setting", ["*", "0,0", "0,secret-synthetic", "2147483648", ""]
)
def test_unknown_generator_config_rejected_without_writing(tmp_path, setting):
    source = tmp_path / "source"
    source.mkdir()
    path = source / "undergroundbiomes.cfg"
    path.write_text("S:IncludedDimensions=" + setting + "\n")
    before = path.read_bytes()
    with pytest.raises(ValueError):
        prepare_resource_bundle(tmp_path / "out", {}, source_config=source)
    assert path.read_bytes() == before and not (tmp_path / "out").exists()


def test_existing_backup_inventory_includes_resource_ownership_and_dimension(tmp_path):
    world = tmp_path / "lab-world"
    resource = world / "DIM-18000"
    resource.mkdir(parents=True)
    for path in [
        world / "level.dat",
        world / "omk-resource-world.properties",
        resource / ".omk-resource.properties",
        resource / "jed_level.dat",
    ]:
        path.write_bytes(b"synthetic snapshot control")
    files = inventory(world)
    assert set(files) == {
        "lab-world/level.dat",
        "lab-world/omk-resource-world.properties",
        "lab-world/DIM-18000/.omk-resource.properties",
        "lab-world/DIM-18000/jed_level.dat",
    }
