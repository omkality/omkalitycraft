import copy
import os
from pathlib import Path

import pytest

from omk.deployment import (
    ingress_config as deployment,
    ingress_template as template,
)
from omk.owner.admin import AdminError
from tests.fixtures.unit.deployment.ingress_config import definitions, layout

__all__ = ["definitions", "layout"]


def test_exact_owned_deployment_is_fingerprinted(layout):
    proof = deployment.proxy_snapshot(*layout)
    assert proof["id"] == "proxy-id" and proof["source_id"] == "source-id"
    assert proof["started"] == "boot"


def test_example_env_matches_defaults_and_requires_explicit_owned_identities():
    path = Path(__file__).resolve().parents[3] / "deploy/ingress/example.env"
    env = dict(
        line.split("=", 1)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
    )
    assert template.settings(env) == template.settings({})
    assert not set(env) & {
        "OMK_INGRESS_CONTAINER",
        "OMK_INGRESS_OWNER",
        "OMK_INGRESS_CONTROL_VOLUME",
        "OMK_INGRESS_CONTROL_OWNER",
        "OMK_INGRESS_CONFIG_DIR",
        "OMK_INGRESS_NETWORK",
    }


@pytest.mark.parametrize("mib,files", [(1, 1), (64, 10)])
def test_docker_log_limits_accept_inclusive_bounds(mib, files):
    policy = template.settings(
        {
            "OMK_INGRESS_DOCKER_LOG_MIB": str(mib),
            "OMK_INGRESS_DOCKER_LOG_FILES": str(files),
        }
    )
    assert template.docker_log_config(policy) == {
        "Type": "local",
        "Config": {"max-size": str(mib) + "m", "max-file": str(files)},
    }


def test_configured_docker_log_limits_are_accepted(layout):
    args = copy.deepcopy(layout)
    args[3].update(
        template.settings(
            {"OMK_INGRESS_DOCKER_LOG_MIB": "1", "OMK_INGRESS_DOCKER_LOG_FILES": "2"}
        )
    )
    args[0]["HostConfig"]["LogConfig"]["Config"] = {"max-size": "1m", "max-file": "2"}
    assert args[3]["docker_log_mib"] == 1 and args[3]["docker_log_files"] == 2
    assert deployment.proxy_snapshot(*args)["id"] == "proxy-id"


@pytest.mark.parametrize(
    "logging",
    [
        {"Type": "json-file", "Config": {"max-size": "1m", "max-file": "2"}},
        {"Type": "local", "Config": {"max-size": "10m", "max-file": "2"}},
        {"Type": "local", "Config": {"max-size": "1m", "max-file": "3"}},
    ],
)
def test_configured_logging_drift_is_refused(layout, logging):
    args = copy.deepcopy(layout)
    args[3].update(
        template.settings(
            {"OMK_INGRESS_DOCKER_LOG_MIB": "1", "OMK_INGRESS_DOCKER_LOG_FILES": "2"}
        )
    )
    args[0]["HostConfig"]["LogConfig"] = logging
    with pytest.raises(AdminError, match="deployment"):
        deployment.proxy_snapshot(*args)


def test_legacy_policy_retains_logging_without_adopting_environment(
    layout, monkeypatch
):
    args = copy.deepcopy(layout)
    args[3].pop("docker_log_mib", None)
    args[3].pop("docker_log_files", None)
    original = dict(args[3])
    monkeypatch.setenv("OMK_INGRESS_DOCKER_LOG_MIB", "1")
    monkeypatch.setenv("OMK_INGRESS_DOCKER_LOG_FILES", "2")
    assert deployment.proxy_snapshot(*args)["id"] == "proxy-id"
    assert args[3] == original
    args[0]["HostConfig"]["LogConfig"]["Config"] = {"max-size": "1m", "max-file": "2"}
    with pytest.raises(AdminError, match="deployment"):
        deployment.proxy_snapshot(*args)


@pytest.mark.parametrize(
    "policy",
    [
        {"docker_log_mib": 1},
        {"docker_log_files": 2},
        {"docker_log_mib": True, "docker_log_files": 2},
        {"docker_log_mib": 1, "docker_log_files": False},
        {"docker_log_mib": 1.0, "docker_log_files": 2},
        {"docker_log_mib": 1, "docker_log_files": "2"},
        {"docker_log_mib": 0, "docker_log_files": 2},
        {"docker_log_mib": 65, "docker_log_files": 2},
        {"docker_log_mib": 1, "docker_log_files": 0},
        {"docker_log_mib": 1, "docker_log_files": 11},
    ],
)
def test_incomplete_or_invalid_saved_logging_policy_refuses(layout, policy):
    args = copy.deepcopy(layout)
    args[3].pop("docker_log_mib", None)
    args[3].pop("docker_log_files", None)
    args[3].update(policy)
    with pytest.raises(ValueError, match="logging policy"):
        deployment.proxy_snapshot(*args)


def test_compose_serialized_exact_readonly_bind_is_accepted(layout):
    args = copy.deepcopy(layout)
    args[0]["HostConfig"]["Binds"] = [str(args[-1]) + ":/usr/local/etc/haproxy:ro"]
    assert deployment.proxy_snapshot(*args)["id"] == "proxy-id"


def test_foreign_legacy_bind_is_refused(layout):
    args = copy.deepcopy(layout)
    args[0]["HostConfig"]["Binds"] = ["/foreign:/usr/local/etc/haproxy:ro"]
    with pytest.raises(AdminError, match="deployment"):
        deployment.proxy_snapshot(*args)


@pytest.mark.parametrize(
    "path,value",
    [
        (("Config", "Image"), "haproxy:latest"),
        (("Config", "Env"), ["EXTRA=value"]),
        (("Config", "Cmd"), ["haproxy", "-d"]),
        (("Config", "Labels", template.LABEL), "someone-else"),
        (("HostConfig", "PortBindings", "25565/tcp", 0, "HostIp"), "0.0.0.0"),
        (("NetworkSettings", "Networks", "foreign"), {"NetworkID": "foreign"}),
        (("HostConfig", "ReadonlyRootfs"), False),
        (("Mounts", 0, "RW"), True),
        (("HostConfig", "Memory"), 0),
        (("HostConfig", "NanoCpus"), 0),
        (("HostConfig", "Privileged"), True),
        (("HostConfig", "CapAdd"), ["SYS_ADMIN"]),
        (("RestartCount",), 1),
        (("State", "OOMKilled"), True),
    ],
)
def test_modified_deployment_is_refused(layout, path, value):
    args = copy.deepcopy(layout)
    target = args[0]
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(AdminError, match="deployment"):
        deployment.proxy_snapshot(*args)


def test_extra_mount_is_refused(layout):
    args = copy.deepcopy(layout)
    args[0]["Mounts"].append(
        {"Type": "bind", "Source": "/var/run/docker.sock", "Destination": "/docker"}
    )
    with pytest.raises(AdminError, match="deployment"):
        deployment.proxy_snapshot(*args)


@pytest.mark.parametrize(
    "key,value",
    [
        ("control_volume", "data"),
        ("control_volume", "store"),
        ("container", "source"),
        ("network", "bridge"),
        ("host_port", 1),
        ("backend_port", True),
        ("config_dir", "../escape"),
        ("container", "proxy\nmalicious"),
        ("unknown", "extra"),
    ],
)
def test_aliases_and_ambiguous_definitions_are_refused(definitions, key, value):
    cfg, spec, write = definitions
    write({**spec, key: value})
    with pytest.raises(AdminError):
        deployment.definition(cfg, "dj2")


def test_prepare_is_repeatable_without_overwriting_changed_config(definitions):
    cfg, spec, _ = definitions
    first = deployment.preparation(cfg, "dj2", {})
    path = cfg.private / spec["config_dir"] / "haproxy.cfg"
    assert first == deployment.preparation(cfg, "dj2", {})
    assert first["closed_on_boot"] and not first["deployed"]
    assert b"disabled\n" in path.read_bytes() and b"\r" not in path.read_bytes()
    path.write_bytes(b"do not overwrite")
    with pytest.raises(AdminError, match="never overwrite"):
        deployment.preparation(cfg, "dj2", {})
    assert path.read_bytes() == b"do not overwrite"


@pytest.mark.parametrize("name", ["DOCKER_LOG_MIB", "DOCKER_LOG_FILES"])
@pytest.mark.parametrize(
    "raw", ["0", "-1", "+1", "1_0", "١", " 1 ", "", "private-marker"]
)
def test_invalid_log_environment_refuses_before_preparing(definitions, name, raw):
    cfg, spec, _ = definitions
    with pytest.raises(ValueError, match="^Invalid OMK_INGRESS_" + name + "$"):
        deployment.preparation(cfg, "dj2", {"OMK_INGRESS_" + name: raw})
    assert not (cfg.private / spec["config_dir"]).exists()


@pytest.mark.parametrize(
    "name,raw", [("DOCKER_LOG_MIB", "65"), ("DOCKER_LOG_FILES", "11")]
)
def test_invalid_log_upper_bound_refuses_before_preparing(definitions, name, raw):
    cfg, spec, _ = definitions
    with pytest.raises(ValueError, match="^Invalid OMK_INGRESS_" + name + "$"):
        deployment.preparation(cfg, "dj2", {"OMK_INGRESS_" + name: raw})
    assert not (cfg.private / spec["config_dir"]).exists()


def test_docker_log_override_preserves_prepared_haproxy_bytes(definitions):
    cfg, spec, _ = definitions
    baseline = deployment.preparation(cfg, "dj2", {})
    path = cfg.private / spec["config_dir"] / "haproxy.cfg"
    raw = path.read_bytes()
    assert (
        deployment.preparation(
            cfg,
            "dj2",
            {"OMK_INGRESS_DOCKER_LOG_MIB": "1", "OMK_INGRESS_DOCKER_LOG_FILES": "2"},
        )
        == baseline
    )
    assert path.read_bytes() == raw


def test_prepared_nonsecret_leaf_is_readable_without_exposing_private_host_parent(
    definitions,
):
    cfg, spec, _ = definitions
    deployment.preparation(cfg, "dj2", {})
    folder = cfg.private / spec["config_dir"]
    path = folder / "haproxy.cfg"
    original = path.read_bytes()
    if os.name != "nt":
        assert path.stat().st_mode & 0o777 == 0o644
        assert folder.stat().st_mode & 0o777 == 0o755
        assert cfg.private.stat().st_mode & 0o077 == 0
    # Explicit prepare repairs a legacy leaf only after exact content validation.
    path.chmod(0o600)
    folder.chmod(0o700)
    deployment.preparation(cfg, "dj2", {})
    assert path.read_bytes() == original
    if os.name != "nt":
        assert path.stat().st_mode & 0o777 == 0o644
        assert folder.stat().st_mode & 0o777 == 0o755


def test_prepare_does_not_relax_permissions_when_leaf_contains_unknown_files(
    definitions,
):
    cfg, spec, _ = definitions
    deployment.preparation(cfg, "dj2", {})
    folder = cfg.private / spec["config_dir"]
    path = folder / "haproxy.cfg"
    path.chmod(0o600)
    folder.chmod(0o700)
    (folder / "private-file").write_text("fixture")
    previous_mode = path.stat().st_mode
    with pytest.raises(AdminError, match="unknown"):
        deployment.preparation(cfg, "dj2", {})
    assert path.stat().st_mode == previous_mode
