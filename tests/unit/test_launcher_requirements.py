import argparse
import base64
import hashlib
import json

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from launcher.game import GameRunner
from launcher.install import Installer, ReleaseClient, current_platform
from launcher.releases import ReleaseError, read_release, sign_release
from launcher.version import VERSION
from omk.publish import build_release
from omk.release_cli import add_release_commands, prepare_release
from tests.http_fixture import serve


@pytest.fixture
def requirements(tmp_path):
    key = Ed25519PrivateKey.generate()
    public = key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    keys = {hashlib.sha256(public).hexdigest()[:16]: base64.b64encode(public).decode()}
    cdn = tmp_path / "cdn"
    directory = cdn / "releases/test" / current_platform()
    files = directory / "files"
    files.mkdir(parents=True)
    for name in ["java", "agent.jar", "forge.jar"]:
        (files / name).write_bytes(b"non-executable fixture")
    launch = {
        "java": "java",
        "agent": "agent.jar",
        "classpath": ["forge.jar"],
        "main_class": "net.minecraft.launchwrapper.Launch",
        "assets": "assets",
        "natives": "natives",
        "game_args": [],
    }

    def create(minimum):
        envelope = build_release(
            files,
            pack_id="test",
            version="1.0",
            minecraft="1.12.2",
            platform=current_platform(),
            launch=launch,
            key=key,
            minimum_launcher_version=minimum,
        )
        (directory / "manifest.json").write_text(json.dumps(envelope), encoding="utf-8")
        return read_release(json.dumps(envelope).encode(), keys)

    return create, cdn, key, keys


@pytest.mark.parametrize(
    ("minimum", "running", "allowed"),
    [
        (None, "0.1", True),
        ("0.3.0.dev9", "0.3.0.dev9", True),
        ("0.3.0.dev9", "0.3.0.dev10", True),
        ("0.3.0.dev10", "0.3.0.dev9", False),
        ("0.3.0", "0.3.0.dev10", False),
        ("0.3.0rc1", "0.3.0", True),
    ],
)
def test_signed_minimum_handles_development_and_stable_versions(
    requirements, minimum, running, allowed
):
    create, _cdn, _key, _keys = requirements
    release = create(minimum)
    assert release.envelope["manifest"]["schema"] == (1 if minimum is None else 2)
    assert release.minimum_launcher_version == minimum
    if allowed:
        release.require_launcher(running)
    else:
        with pytest.raises(ReleaseError, match="обновление лаунчера"):
            release.require_launcher(running)


@pytest.mark.parametrize(
    "minimum", [None, True, 42, "", "latest", "0.3\n", "0.3/", "9" * 81]
)
def test_schema_two_rejects_missing_or_malformed_minimum(requirements, minimum):
    create, _cdn, key, _keys = requirements
    payload = create(None).envelope["manifest"]
    payload.update(schema=2, minimum_launcher_version=minimum)
    with pytest.raises(ReleaseError):
        sign_release(payload, key)


def test_minimum_cannot_hide_in_schema_one_or_be_removed_from_schema_two(requirements):
    create, _cdn, key, _keys = requirements
    payload = create("0.3.0.dev9").envelope["manifest"]
    payload["schema"] = 1
    with pytest.raises(ReleaseError):
        sign_release(payload, key)
    payload["schema"] = 2
    del payload["minimum_launcher_version"]
    with pytest.raises(ReleaseError):
        sign_release(payload, key)


def test_future_minimum_stops_http_preparation_install_and_java_before_side_effects(
    requirements, tmp_path
):
    create, cdn, _key, keys = requirements
    release = create("9999.0")
    with serve(cdn) as (origin, requests):
        client = ReleaseClient(origin, keys)
        with pytest.raises(ReleaseError, match="обновление лаунчера"):
            client.fetch("test")
        assert all(path.endswith("/manifest.json") for path, _offset in requests)
        root = tmp_path / "portable"
        with pytest.raises(ReleaseError, match="обновление лаунчера"):
            Installer(root, client).install(release, lambda _p: None)
        with pytest.raises(ReleaseError, match="обновление лаунчера"):
            GameRunner(root).start(release, root / "instances/test", None)
        assert not root.exists()


def test_policy_tampering_is_rejected_and_verified_requirement_is_immutable(
    requirements,
):
    create, _cdn, _key, keys = requirements
    release = create("9999.0")
    del release.envelope["manifest"]["minimum_launcher_version"]
    with pytest.raises(ReleaseError, match="подлинность"):
        read_release(json.dumps(release.envelope).encode(), keys)
    with pytest.raises(ReleaseError, match="обновление лаунчера"):
        release.require_launcher()


@pytest.mark.parametrize("override", [None, "0.3.0"])
def test_pack_cli_signs_current_or_explicit_minimum(requirements, tmp_path, override):
    create, cdn, _key, _keys = requirements
    release = create(None)
    profile = tmp_path / "launch.json"
    profile.write_text(json.dumps(release.launch), encoding="utf-8")
    manifest = tmp_path / "published.json"
    public = tmp_path / "public.json"
    parser = argparse.ArgumentParser()
    add_release_commands(parser.add_subparsers(required=True))
    arguments = [
        "release",
        "pack",
        "--files",
        str(cdn / "releases/test" / current_platform() / "files"),
        "--launch-profile",
        str(profile),
        "--private-key",
        str(tmp_path / "offline.pem"),
        "--public-keys",
        str(public),
        "--output",
        str(manifest),
        "--pack-id",
        "test",
        "--minecraft",
        "1.12.2",
        "--version",
        "1.1",
    ]
    if override is not None:
        arguments.extend(["--minimum-launcher-version", override])
    result = prepare_release(parser.parse_args(arguments))
    signed = read_release(
        manifest.read_bytes(), json.loads(public.read_text(encoding="utf-8"))
    )
    assert result["ok"] and result["deployed"] is False
    assert signed.envelope["manifest"]["schema"] == 2
    assert signed.minimum_launcher_version == (
        VERSION if override is None else override
    )
