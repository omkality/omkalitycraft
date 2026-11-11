"""Private single-source ingress definitions and exact Docker deployment identity."""

import hashlib
import json
import os
import re
import tomllib
from pathlib import Path

from omk import (
    admin_backups as backups,
    ingress_template as template,
    owner_volumes,
)
from omk.admin import AdminError, _private_path
from omk.cold_backup_worker import digest
from omk.fs import regular


def configured(config):
    p = config.private / "ingress.toml"
    return p.exists() or p.is_symlink() or p.is_junction()


def validate_entries(config, entries):
    required = {
        "container",
        "owner",
        "network",
        "network_label",
        "network_owner",
        "control_volume",
        "control_owner",
        "config_dir",
        "host_port",
        "container_port",
        "backend_port",
    }
    containers, controls, folders, ports = set(), set(), set(), set()
    for item in entries.values():
        if not isinstance(item, dict) or set(item) != required:
            raise AdminError("Invalid ingress entry")
        for k in required - {"host_port", "container_port", "backend_port"}:
            if not isinstance(item[k], str):
                raise AdminError("Invalid ingress string")
        if any(
            not backups.RESOURCE.fullmatch(item[k])
            for k in (
                "container",
                "owner",
                "network",
                "network_owner",
                "control_volume",
                "control_owner",
            )
        ):
            raise AdminError("Invalid explicit ingress resource")
        if item["network"] in {"host", "bridge", "none"} or not (
            re.fullmatch(r"omkality\.[a-z0-9_.-]{1,64}", item["network_label"])
            or item["network_label"] == "com.docker.compose.project"
        ):
            raise AdminError("Ingress requires an owned private bridge")
        if any(
            type(item[k]) is not int or not 1024 <= item[k] <= 65535
            for k in ("host_port", "container_port", "backend_port")
        ):
            raise AdminError("Invalid ingress port")
        folder = _private_path(config.private, item["config_dir"])
        if not item["config_dir"].startswith("ingress-config/"):
            raise AdminError("Use a dedicated private ingress-config subdirectory")
        if (
            item["container"] in containers
            or item["control_volume"] in controls
            or folder in folders
            or item["host_port"] in ports
        ):
            raise AdminError("Ingress resources must be distinct")
        containers.add(item["container"])
        controls.add(item["control_volume"])
        folders.add(folder)
        ports.add(item["host_port"])
    return containers, controls, ports


def definition(config, server):
    path = _private_path(config.private, "ingress.toml")
    if not regular(path, config.private) or (
        os.name != "nt" and path.stat().st_mode & 0o077
    ):
        raise AdminError("Use a private mode-600 ingress.toml")
    raw = path.read_bytes()
    if len(raw) > 65536:
        raise AdminError("Ingress definitions exceed bound")
    doc = tomllib.loads(raw.decode())
    if (
        set(doc) != {"schema", "servers"}
        or type(doc["schema"]) is not int
        or doc["schema"] != 1
        or not isinstance(doc["servers"], dict)
        or not doc["servers"]
        or set(doc["servers"]) - set(config.servers)
    ):
        raise AdminError("Invalid ingress definitions")
    containers, controls, ports = validate_entries(config, doc["servers"])
    forbidden = set()
    source_names = set()
    for name in owner_volumes.document(config, "backups.toml"):
        t = backups.target_for(config, name)
        forbidden.update((t["data_volume"], t["store_volume"]))
        source_names.add(t["container"])
    for filename in owner_volumes.FILES:
        if (config.private / filename).exists() or (
            config.private / filename
        ).is_symlink():
            for entry in owner_volumes.document(config, filename).values():
                owner_volumes.validate_entry(entry, filename)
                forbidden.add(entry["data_volume"])
    if (
        controls & forbidden
        or containers & source_names
        or any(c.port in ports for c in config.recovery_consoles.values())
    ):
        raise AdminError("Ingress resources alias source/store/staging or console")
    if server not in doc["servers"]:
        raise AdminError("Server has no explicit ingress definition")
    return dict(doc["servers"][server])


def preparation(config, server, environment=None):
    spec = definition(config, server)
    target = backups.target_for(config, server)
    policy = template.settings(environment)
    folder = _private_path(config.private, spec["config_dir"])
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = folder / "haproxy.cfg"
    expected = template.render(spec, policy, target["container"]).encode()
    if path.exists():
        if not regular(path, config.private) or path.read_bytes() != expected:
            raise AdminError(
                "Existing ingress config differs; never overwrite deployment"
            )
    else:
        if any(folder.iterdir()):
            raise AdminError("Ingress config directory must start empty")
        with path.open("xb") as stream:
            path.chmod(0o600)
            stream.write(expected)
            stream.flush()
            os.fsync(stream.fileno())
    return {
        "ok": True,
        "config_dir": str(folder),
        "config_sha256": hashlib.sha256(expected).hexdigest(),
        "closed_on_boot": True,
        "deployed": False,
    }


def proxy_snapshot(data, spec, target, policy, image, network, control, folder):
    c, h, s = data["Config"], data["HostConfig"], data["State"]
    mounts = data.get("Mounts", [])
    entries = {m.get("Destination"): m for m in mounts}
    cfg, ctl = entries.get("/usr/local/etc/haproxy", {}), entries.get(
        "/run/omk-ingress", {}
    )
    if (
        data["Name"] != "/" + spec["container"]
        or (c.get("Labels") or {}).get(template.LABEL) != spec["owner"]
        or c["Image"] != template.profile()["image"]
        or data["Image"] != image["id"]
        or c.get("Cmd") != template.profile()["command"]
        or digest(c.get("Env")) != image["env_sha256"]
        or digest(c.get("Entrypoint")) != image["entrypoint_sha256"]
        or c.get("User") != "0:0"
        or h.get("Memory") != policy["memory_mib"] * 1024**2
        or h.get("NanoCpus") != policy["cpu_millis"] * 10**6
        or h.get("PidsLimit") != policy["pids"]
        or h.get("ReadonlyRootfs") is not True
        or h.get("Privileged") is not False
        or h.get("AutoRemove") is not False
        or h.get("RestartPolicy", {}).get("Name") not in {"no", ""}
        or h.get("CapDrop") != ["ALL"]
        or h.get("SecurityOpt") != ["no-new-privileges:true"]
        or h.get("NetworkMode") != spec["network"]
        or set(data.get("NetworkSettings", {}).get("Networks", {})) != {spec["network"]}
        or data["NetworkSettings"]["Networks"][spec["network"]].get("NetworkID")
        != network["id"]
        or h.get("PortBindings")
        != {
            str(spec["container_port"])
            + "/tcp": [{"HostIp": "127.0.0.1", "HostPort": str(spec["host_port"])}]
        }
        or data["NetworkSettings"]
        .get("Ports", {})
        .get(str(spec["container_port"]) + "/tcp")
        != h["PortBindings"][str(spec["container_port"]) + "/tcp"]
        or h.get("LogConfig")
        != {"Type": "local", "Config": {"max-size": "10m", "max-file": "3"}}
        or h.get("Binds")
        not in (None, [], [str(folder) + ":/usr/local/etc/haproxy:ro"])
        or any(
            h.get(k)
            for k in (
                "VolumesFrom",
                "Devices",
                "DeviceRequests",
                "CapAdd",
                "ExtraHosts",
                "Links",
                "Tmpfs",
                "PidMode",
                "UTSMode",
            )
        )
        or len(mounts) != 2
        or len(entries) != 2
        or cfg.get("Type") != "bind"
        or cfg.get("Source") != str(folder)
        or cfg.get("RW") is not False
        or ctl.get("Type") != "volume"
        or ctl.get("Name") != spec["control_volume"]
        or ctl.get("RW") is not True
        or s.get("Status") != "running"
        or s.get("Running") is not True
        or s.get("OOMKilled") is not False
        or s.get("Paused")
        or s.get("Restarting")
        or data.get("RestartCount") != 0
    ):
        raise AdminError("Ingress differs from the owned immutable loopback deployment")
    return {
        "id": data["Id"],
        "created": data["Created"],
        "started": s["StartedAt"],
        "image": data["Image"],
        "network": network,
        "control": control,
        "source_id": target["id"],
    }


def capture(config, server, policy=None):
    from omk import (  # noqa: PLC0415
        admin_maintenance as maintenance,
        candidate_slot_spec,
    )

    backups.local_engine()
    spec = definition(config, server)
    target = backups.target_for(config, server)
    binding = maintenance.binding(config, server)
    policy = template.settings() if policy is None else policy
    if spec["backend_port"] == binding["rcon_container_port"]:
        raise AdminError("Ingress must never target the RCON port")
    source = json.loads(
        backups.docker("inspect", "--type", "container", target["container"])
    )[0]
    maintenance.snapshot(target, binding)
    if set(source["NetworkSettings"]["Networks"]) != {spec["network"]} or any(
        b.get("HostIp") not in {"127.0.0.1", "::1"}
        for bindings in (source["HostConfig"].get("PortBindings") or {}).values()
        for b in bindings or []
    ):
        raise AdminError(
            "The game source must have private networking and loopback-only published ports"
        )
    folder = _private_path(config.private, spec["config_dir"])
    path = folder / "haproxy.cfg"
    expected = template.render(spec, policy, target["container"]).encode()
    if (
        not regular(path, config.private)
        or path.read_bytes() != expected
        or {p.name for p in folder.iterdir()} != {"haproxy.cfg"}
    ):
        raise AdminError(
            "Ingress config is missing, linked, changed or has unknown files"
        )
    nspec = {
        "network": spec["network"],
        "network_label": spec["network_label"],
        "network_owner": spec["network_owner"],
    }
    network = candidate_slot_spec.network(nspec)
    if (
        source["NetworkSettings"]["Networks"][spec["network"]].get("NetworkID")
        != network["id"]
    ):
        raise AdminError("Source private bridge identity changed")
    volumes = json.loads(backups.docker("volume", "inspect", spec["control_volume"]))
    if (
        len(volumes) != 1
        or (volumes[0].get("Labels") or {}).get(template.LABEL) != spec["control_owner"]
    ):
        raise AdminError("Ingress control volume is not explicitly owned")
    control = {
        "name": spec["control_volume"],
        "created": volumes[0]["CreatedAt"],
        "owner": spec["control_owner"],
    }
    data = json.loads(
        backups.docker("inspect", "--type", "container", spec["container"])
    )[0]
    image = candidate_slot_spec.image(template.profile()["image"])
    proxy = proxy_snapshot(
        data, spec, {"id": source["Id"]}, policy, image, network, control, folder
    )
    if set(
        backups.docker(
            "ps", "-aq", "--no-trunc", "--filter", "volume=" + spec["control_volume"]
        ).split()
    ) != {proxy["id"]}:
        raise AdminError(
            "Ingress control volume has a foreign container/helper reference"
        )
    return {
        "spec": spec,
        "target": target,
        "policy": policy,
        "proxy": proxy,
        "config_sha256": hashlib.sha256(expected).hexdigest(),
        "rcon_port": binding["rcon_container_port"],
        "profile_sha256": hashlib.sha256(
            (
                Path(__file__).resolve().parents[1]
                / "profiles/runtime/haproxy-ingress.json"
            ).read_bytes()
        ).hexdigest(),
    }
