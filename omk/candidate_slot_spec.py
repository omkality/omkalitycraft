"""Explicit loopback Forge trial template; never clone Docker Env/Args."""

import base64
import hashlib
import json
import os
import re
import tomllib
from urllib.parse import urlsplit

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey

from omk import admin_backups as backups
from omk.admin import AdminError, _private_path, _read_json
from omk.cold_backup_worker import digest
from omk.fs import regular
from omk.profiles import PROJECT_ROOT

# Schema-1 records before configurable Docker logging always meant 10m / 3.
_LEGACY_DOCKER_LOG_POLICY = {"docker_log_mib": 10, "docker_log_files": 3}


def settings(environment=None):
    env = os.environ if environment is None else environment
    result = {}
    for key, default, minimum, maximum in (
        ("MEMORY_MIB", 8192, 1024, 65536),
        ("HEAP_MIB", 6144, 512, 49152),
        ("INITIAL_HEAP_MIB", 1024, 256, 49152),
        ("CPUS", 4, 1, 32),
        ("PIDS", 512, 128, 4096),
        ("LOG_BYTES", 4 * 1024**2, 65536, 8 * 1024**2),
        ("DOCKER_LOG_MIB", 10, 1, 64),
        ("DOCKER_LOG_FILES", 3, 1, 10),
    ):
        raw = env.get("OMK_SLOT_" + key, str(default))
        if (
            not isinstance(raw, str)
            or not raw.isascii()
            or not raw.isdecimal()
            or len(raw) > 9
            or not minimum <= int(raw) <= maximum
        ):
            raise AdminError("Invalid OMK_SLOT_" + key)
        result[key.lower()] = int(raw)
    if (
        not result["initial_heap_mib"]
        <= result["heap_mib"]
        <= result["memory_mib"] - 512
    ):
        raise AdminError(
            "Candidate heap must leave at least 512 MiB outside the Java heap"
        )
    return result


def complete_policy(policy):
    """Read legacy plans without rewriting their frozen journal or adopting overrides."""
    if not isinstance(policy, dict):
        raise AdminError("Invalid candidate policy")
    present = set(policy) & set(_LEGACY_DOCKER_LOG_POLICY)
    if present and present != set(_LEGACY_DOCKER_LOG_POLICY):
        raise AdminError("Incomplete candidate Docker logging policy")
    result = {**_LEGACY_DOCKER_LOG_POLICY, **policy}
    for key, maximum in (("docker_log_mib", 64), ("docker_log_files", 10)):
        if type(result[key]) is not int or not 1 <= result[key] <= maximum:
            raise AdminError("Invalid candidate Docker logging policy")
    return result


def docker_log_config(policy):
    policy = complete_policy(policy)
    return {
        "Type": "local",
        "Config": {
            "max-size": str(policy["docker_log_mib"]) + "m",
            "max-file": str(policy["docker_log_files"]),
        },
    }


def definition(config, server):
    path = _private_path(config.private, "candidate-slots.toml")
    if not regular(path, config.private) or (
        os.name != "nt" and path.stat().st_mode & 0o077
    ):
        raise AdminError("Use a private mode-600 candidate-slots.toml")
    raw = path.read_bytes()
    if len(raw) > 65536:
        raise AdminError("Candidate definitions exceed limit")
    doc = tomllib.loads(raw.decode())
    if (
        set(doc) != {"schema", "servers"}
        or type(doc["schema"]) is not int
        or doc["schema"] != 1
        or not isinstance(doc["servers"], dict)
        or not doc["servers"]
        or set(doc["servers"]) - set(config.servers)
    ):
        raise AdminError("Invalid candidate slot definitions")
    ports = validate_entries(config, doc["servers"])
    if server not in doc["servers"]:
        raise AdminError("Server has no candidate slot definition")
    for name in config.servers:
        if name in doc["servers"]:
            console = config.recovery_consoles.get(name)
            if console and console.port in ports:
                raise AdminError(
                    "Candidate ports must not alias source recovery consoles"
                )
    return dict(doc["servers"][server])


def validate_entries(config, entries):
    names, ports = set(), set()
    required = {
        "container",
        "network",
        "network_label",
        "network_owner",
        "game_host_port",
        "rcon_host_port",
        "game_container_port",
        "rcon_container_port",
        "auth_url",
        "metadata_file",
    }
    for entry in entries.values():
        if not isinstance(entry, dict) or set(entry) != required:
            raise AdminError("Invalid candidate slot entry")
        for key in required - {
            "game_host_port",
            "rcon_host_port",
            "game_container_port",
            "rcon_container_port",
        }:
            if not isinstance(entry[key], str):
                raise AdminError("Invalid candidate slot scalar")
        if (
            any(
                not backups.RESOURCE.fullmatch(entry[k])
                for k in ["container", "network", "network_owner"]
            )
            or entry["network"] in {"host", "bridge", "none"}
            or not (
                re.fullmatch(r"omkality\.[a-z0-9_.-]{1,64}", entry["network_label"])
                or entry["network_label"] == "com.docker.compose.project"
            )
        ):
            raise AdminError("Invalid explicit candidate resources")
        for key in [
            "game_host_port",
            "rcon_host_port",
            "game_container_port",
            "rcon_container_port",
        ]:
            if type(entry[key]) is not int or not 1024 <= entry[key] <= 65535:
                raise AdminError("Invalid candidate port")
        if (
            entry["game_container_port"] == entry["rcon_container_port"]
            or entry["container"] in names
            or ports & {entry["game_host_port"], entry["rcon_host_port"]}
            or entry["game_host_port"] == entry["rcon_host_port"]
        ):
            raise AdminError("Candidate names and host ports must be distinct")
        names.add(entry["container"])
        ports.update([entry["game_host_port"], entry["rcon_host_port"]])
        url = urlsplit(entry["auth_url"])
        if (
            url.scheme not in {"http", "https"}
            or not url.hostname
            or url.hostname in {"localhost", "127.0.0.1", "0.0.0.0", "::1"}
            or url.username
            or url.password
            or url.query
            or url.fragment
            or not url.path.endswith("/authlib-injector")
            or any(c.isspace() for c in entry["auth_url"])
        ):
            raise AdminError(
                "Use an explicit credential-free authlib URL reachable inside the private network"
            )
        _private_path(config.private, entry["metadata_file"])
    return ports


def metadata(config, spec):
    value = _read_json(
        _private_path(config.private, spec["metadata_file"]), config.private
    )
    if (
        set(value) != {"meta", "skinDomains", "signaturePublickey"}
        or not isinstance(value["meta"], dict)
        or not isinstance(value["skinDomains"], list)
        or len(value["skinDomains"]) > 64
        or any(
            not isinstance(s, str) or not 1 <= len(s) <= 253
            for s in value["skinDomains"]
        )
        or not isinstance(value["signaturePublickey"], str)
    ):
        raise AdminError(
            "Use only public Drasl authlib metadata, never account/session files"
        )
    try:
        key = serialization.load_pem_public_key(value["signaturePublickey"].encode())
        if not isinstance(key, RSAPublicKey) or not 2048 <= key.key_size <= 8192:
            raise ValueError("key")
    except ValueError, TypeError, UnicodeError:
        raise AdminError("Invalid authlib public verification key") from None
    return value


def profile():
    raw = (PROJECT_ROOT / "profiles/runtime/forge112-server.json").read_bytes()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def command(spec, policy, public_metadata):
    from omk.logging_runtime import logging_pins  # noqa: PLC0415

    data, _ = profile()
    cp = [p["path"] for p in logging_pins()["artifacts"]] + [data["forge"]["path"]]
    return [
        "java",
        f"-Xms{policy['initial_heap_mib']}M",
        f"-Xmx{policy['heap_mib']}M",
        "-Dfile.encoding=UTF-8",
        "-Dfml.queryResult=cancel",
        "-Djava.io.tmpdir=/srv/.omk/tmp",
        "-Duser.home=/srv/.omk/java-home",
        "-javaagent:/srv/.omk/authlib-injector.jar=" + spec["auth_url"],
        "-Dauthlibinjector.side=server",
        "-Dauthlibinjector.yggdrasil.prefetched="
        + base64.b64encode(json.dumps(public_metadata).encode()).decode(),
        "-Dauthlibinjector.noLogFile",
        "-Dlog4j.configurationFile=file:/srv/.omk/log4j2.xml",
        "-cp",
        ":".join("/srv/" + p for p in cp),
        data["main"],
        "nogui",
    ]


def network(spec):
    rows = json.loads(backups.docker("network", "inspect", spec["network"]))
    if len(rows) != 1:
        raise AdminError("Ambiguous candidate network")
    r = rows[0]
    if (
        r["Name"] != spec["network"]
        or r["Driver"] != "bridge"
        or r["Scope"] != "local"
        or (r.get("Labels") or {}).get(spec["network_label"]) != spec["network_owner"]
    ):
        raise AdminError("Candidate requires an explicitly owned local bridge network")
    return {"id": r["Id"], "created": r["Created"], "name": r["Name"]}


def image(pin):
    rows = json.loads(backups.docker("image", "inspect", pin))
    if len(rows) != 1 or rows[0].get("Os") != "linux":
        raise AdminError("Pinned Linux runtime image unavailable")
    r = rows[0]
    return {
        "id": r["Id"],
        "env_sha256": digest(r["Config"].get("Env")),
        "entrypoint_sha256": digest(r["Config"].get("Entrypoint")),
    }
