"""Reviewed single-source TCP ingress template. Stdlib only for Docker helpers."""

import json
import os
import re
from decimal import Decimal
from pathlib import Path

CONFIG = "/usr/local/etc/haproxy/haproxy.cfg"
SOCKET = "/run/omk-ingress/admin.sock"
LABEL = "omkality.ingress.owner"


def profile():
    return json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "profiles/runtime/haproxy-ingress.json"
        ).read_text(encoding="utf-8")
    )


def settings(environment=None):
    env = os.environ if environment is None else environment
    result = {}
    for key, default, low, high in (
        ("MEMORY_MIB", 64, 32, 256),
        ("PIDS", 64, 32, 128),
        ("MAX_CONNECTIONS", 128, 20, 1024),
        ("CONNECT_SECONDS", 5, 1, 30),
        ("IDLE_SECONDS", 3600, 60, 86400),
        ("TIMEOUT_SECONDS", 30, 5, 120),
        ("DOCKER_LOG_MIB", 10, 1, 64),
        ("DOCKER_LOG_FILES", 3, 1, 10),
    ):
        raw = env.get("OMK_INGRESS_" + key, str(default))
        if (
            not isinstance(raw, str)
            or not raw.isascii()
            or not raw.isdecimal()
            or len(raw) > 8
            or not low <= int(raw) <= high
        ):
            raise ValueError("Invalid OMK_INGRESS_" + key)
        result[key.lower()] = int(raw)
    cpus = env.get("OMK_INGRESS_CPUS", "0.5")
    if not isinstance(cpus, str) or not re.fullmatch(r"[0-2](?:\.[0-9]{1,3})?", cpus):
        raise ValueError("Invalid OMK_INGRESS_CPUS")
    value = Decimal(cpus)
    if not Decimal("0.1") <= value <= 2:
        raise ValueError("Invalid OMK_INGRESS_CPUS")
    result["cpu_millis"] = int(value * 1000)
    return result


def docker_log_config(policy):
    # Schema-1 plans without both fields froze the original 10m / 3 policy.
    defaults = {"docker_log_mib": 10, "docker_log_files": 3}
    present = set(policy) & set(defaults)
    if present and present != set(defaults):
        raise ValueError("Incomplete ingress Docker logging policy")
    values = {**defaults, **policy}
    for key, maximum in (("docker_log_mib", 64), ("docker_log_files", 10)):
        if type(values[key]) is not int or not 1 <= values[key] <= maximum:
            raise ValueError("Invalid ingress Docker logging policy")
    return {
        "Type": "local",
        "Config": {
            "max-size": str(values["docker_log_mib"]) + "m",
            "max-file": str(values["docker_log_files"]),
        },
    }


def render(spec, policy, backend):
    # The backend name is validated by the controller, never arbitrary HAProxy text.
    route = f"server source {backend}:{spec['backend_port']} check inter 1s"
    return f"""global
    maxconn {policy['max_connections']}
    nbthread 1
    stats socket {SOCKET} mode 600 level admin
defaults
    mode tcp
    timeout connect {policy['connect_seconds']}s
    timeout client {policy['idle_seconds']}s
    timeout server {policy['idle_seconds']}s
resolvers docker
    nameserver dns 127.0.0.11:53
    hold valid 1s
    hold nx 1s
    timeout resolve 1s
    timeout retry 1s
frontend game
    bind 0.0.0.0:{spec['container_port']}
    default_backend minecraft
backend minecraft
    {route} resolvers docker resolve-prefer ipv4 init-addr none disabled
"""
