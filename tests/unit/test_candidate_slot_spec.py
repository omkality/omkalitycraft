import json
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from omk import (
    candidate_slot_spec as spec,
    candidate_slots as slots,
)
from omk.admin import AdminError


@pytest.fixture
def configured(tmp_path):
    private = tmp_path / ".omk-admin"
    private.mkdir(mode=0o700)
    cfg = SimpleNamespace(
        private=private,
        servers={"dj2": tmp_path / "server"},
        recovery_consoles={"dj2": SimpleNamespace(port=25577)},
    )
    entry = {
        "container": "candidate",
        "network": "owned-net",
        "network_label": "omkality.network.id",
        "network_owner": "owned",
        "game_host_port": 25578,
        "rcon_host_port": 25579,
        "game_container_port": 25576,
        "rcon_container_port": 25575,
        "auth_url": "http://drasl:25585/authlib-injector",
        "metadata_file": "public.json",
    }
    return cfg, entry


def write(cfg, entry):
    p = cfg.private / "candidate-slots.toml"
    p.write_text(
        "schema=1\n[servers.dj2]\n"
        + "\n".join(k + "=" + json.dumps(v) for k, v in entry.items())
    )
    p.chmod(0o600)


def test_explicit_template_config_and_no_inherited_arguments(configured):
    cfg, entry = configured
    write(cfg, entry)
    assert spec.definition(cfg, "dj2") == entry
    public = {
        "meta": {},
        "skinDomains": [],
        "signaturePublickey": "public-test-metadata",
    }
    args = spec.command(entry, spec.settings({}), public)
    assert args[0] == "java" and args[-2:] == [
        "net.minecraftforge.fml.relauncher.ServerLaunchWrapper",
        "nogui",
    ]
    assert "-Domkality.lab.commandCatalog=true" not in args
    assert (
        "-Djava.io.tmpdir=/srv/.omk/tmp" in args
        and "-Duser.home=/srv/.omk/java-home" in args
    )
    assert all("password" not in s.lower() and "shell" not in s.lower() for s in args)


@pytest.mark.parametrize(
    "key,value",
    [
        ("game_host_port", True),
        ("rcon_host_port", 25578),
        ("game_container_port", 25575),
        ("rcon_host_port", 25577),
        ("network", "host"),
        ("network", "bridge"),
        ("container", "bad/name"),
        ("network_label", "unowned"),
        ("auth_url", "http://user:pass@drasl:25585/authlib-injector"),
        ("auth_url", "http://127.0.0.1:25585/authlib-injector"),
        ("auth_url", "http://drasl/authlib-injector?token=x"),
        ("auth_url", "http://drasl/not-auth"),
        ("metadata_file", "../outside.json"),
    ],
)
def test_invalid_definition_is_refused(configured, key, value):
    cfg, entry = configured
    entry[key] = value
    write(cfg, entry)
    with pytest.raises(AdminError):
        spec.definition(cfg, "dj2")


@pytest.mark.parametrize(
    "env",
    [
        {"OMK_SLOT_CPUS": "0"},
        {"OMK_SLOT_HEAP_MIB": "8192"},
        {"OMK_SLOT_INITIAL_HEAP_MIB": "9000"},
        {"OMK_SLOT_MEMORY_MIB": "-1"},
        {"OMK_SLOT_LOG_BYTES": "9e9"},
        {"OMK_SLOT_PIDS": "99999999999"},
    ],
)
def test_memory_cpu_log_limits_are_validated(env):
    with pytest.raises(AdminError):
        spec.settings(env)


def test_docker_log_policy_has_independent_validated_overrides():
    default = spec.settings({})
    assert spec.docker_log_config(default) == {
        "Type": "local",
        "Config": {"max-size": "10m", "max-file": "3"},
    }
    override = spec.settings(
        {"OMK_SLOT_DOCKER_LOG_MIB": "1", "OMK_SLOT_DOCKER_LOG_FILES": "2"}
    )
    assert spec.docker_log_config(override) == {
        "Type": "local",
        "Config": {"max-size": "1m", "max-file": "2"},
    }
    assert override["log_bytes"] == default["log_bytes"] == 4 * 1024**2


@pytest.mark.parametrize(
    "name,value",
    [
        ("OMK_SLOT_DOCKER_LOG_MIB", "0"),
        ("OMK_SLOT_DOCKER_LOG_MIB", "65"),
        ("OMK_SLOT_DOCKER_LOG_MIB", "1.5"),
        ("OMK_SLOT_DOCKER_LOG_MIB", "２"),
        ("OMK_SLOT_DOCKER_LOG_FILES", "0"),
        ("OMK_SLOT_DOCKER_LOG_FILES", "11"),
        ("OMK_SLOT_DOCKER_LOG_FILES", "secret-value"),
    ],
)
def test_invalid_docker_log_limits_do_not_echo_values(name, value):
    with pytest.raises(AdminError, match="Invalid " + name) as error:
        spec.settings({name: value})
    assert "secret-value" not in str(error.value)


@pytest.mark.parametrize(
    "policy",
    [
        {"docker_log_mib": 1},
        {"docker_log_files": 2},
        {"docker_log_mib": True, "docker_log_files": 2},
        {"docker_log_mib": 1, "docker_log_files": 11},
    ],
)
def test_partial_or_malformed_stored_log_policy_is_refused(policy):
    with pytest.raises(AdminError):
        spec.complete_policy(policy)


def test_candidate_env_example_matches_consumed_defaults():
    text = (spec.PROJECT_ROOT / "deploy/candidate-slots.example.env").read_text(
        encoding="utf-8"
    )
    values = dict(
        line.split("=", 1) for line in text.splitlines() if line.startswith("OMK_SLOT_")
    )
    assert len(values) == 8 and spec.settings(values) == spec.settings({})


def test_public_metadata_has_real_rsa_key_and_rejects_session_files(configured):
    cfg, entry = configured
    pem = (
        rsa.generate_private_key(public_exponent=65537, key_size=2048)
        .public_key()
        .public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
        .decode()
    )
    data = {
        "meta": {"serverName": "Test"},
        "skinDomains": ["drasl"],
        "signaturePublickey": pem,
    }
    p = cfg.private / "public.json"
    p.write_text(json.dumps(data))
    p.chmod(0o600)
    assert spec.metadata(cfg, entry) == data
    for change in [
        {"apiToken": "fixture-session"},
        {**data, "signaturePublickey": "invalid"},
        {**data, "password": "never-accept"},
    ]:
        p.write_text(json.dumps(change))
        with pytest.raises(AdminError):
            spec.metadata(cfg, entry)


def test_exact_container_lookup_does_not_treat_daemon_failure_as_absence(monkeypatch):
    def unavailable(*args, **kwargs):
        raise AdminError("Docker unavailable")

    monkeypatch.setattr(slots.backups, "docker", unavailable)
    with pytest.raises(AdminError):
        slots.raw_container("candidate")


def test_container_lookup_uses_full_id_and_escaped_exact_name(monkeypatch):
    calls = []

    def docker(*args, **kwargs):
        calls.append(args)
        if args[0] == "ps":
            return "a" * 64 + "\n"
        return json.dumps([{"Id": "a" * 64}])

    monkeypatch.setattr(slots.backups, "docker", docker)
    assert slots.raw_container("candidate.v1")["Id"] == "a" * 64
    assert calls[0][-1] == r"name=^/candidate\.v1$" and calls[1][-1] == "a" * 64
