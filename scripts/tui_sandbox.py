"""Prepare/start/inspect/stop the persistent local TUI fixture. Never deletes data."""

import argparse
import hashlib
import json
import os
import secrets
import shutil
import subprocess
import urllib.request
from pathlib import Path

from launcher.pack.log_policy import prepare_logging
from omk.admin import _write_private
from omk.logging_runtime import stage_logging_runtime
from omk.monitoring_config import render
from omk.owner_console import run as console
from omk.owner_overview import run as overview
from omk.project_moderation import initialize

ROOT = Path(__file__).resolve().parents[1]
PROJECT = "omk-tui-sandbox"


def stage_core(runtime, artifact):
    core = json.loads((ROOT / "mods/forge-1.12.2/versions.json").read_bytes())[
        "artifacts"
    ]["core"]
    if hashlib.sha256(artifact.read_bytes()).hexdigest() != core["sha256"]:
        raise ValueError("Core artifact differs from the repository pin")
    shutil.copy2(artifact, runtime / "mods" / core["file"])
    (runtime / ".omk/core-mods.properties").write_text(
        "minecraft=1.12.2\nmcp=9.42\nFML=8.0.99.99\nforge=14.23.5.2860\n",
        encoding="utf-8",
    )


def forge_source(source):
    source = source.resolve(strict=True)
    pin = json.loads((ROOT / "profiles/runtime/forge112-server.json").read_bytes())[
        "forge"
    ]
    if hashlib.sha256((source / pin["path"]).read_bytes()).hexdigest() != pin["sha256"]:
        raise ValueError("Forge source differs from the pinned server runtime")
    return source, pin


def prepare(root, source, core=None):
    root = root.resolve()
    if root.exists():
        raise ValueError(
            "Use the existing fixture config; prepare never overwrites a fixture"
        )
    source, pin = forge_source(source)
    root.mkdir(parents=True, mode=0o700)
    runtime = root / "runtime"
    runtime.mkdir()
    shutil.copytree(source / "libraries", runtime / "libraries")
    for name in (pin["path"], "minecraft_server.1.12.2.jar"):
        shutil.copy2(source / name, runtime / name)
    jars = stage_logging_runtime(runtime)
    (runtime / ".omk").mkdir()
    shutil.copy2(
        prepare_logging("1.12.2", root / "logging"), runtime / ".omk/log4j2.xml"
    )
    classpath = ":".join("/runtime/" + p.relative_to(runtime).as_posix() for p in jars)
    (runtime / ".omk/classpath").write_text(
        classpath + ":/runtime/" + pin["path"], encoding="utf-8"
    )
    (runtime / "mods").mkdir()
    exporter = json.loads((ROOT / "deploy/metrics/artifacts.json").read_bytes())[
        "game_exporter"
    ]
    with urllib.request.urlopen(exporter["url"], timeout=30) as response:
        payload = response.read(exporter["bytes"] + 1)
    if (
        len(payload) != exporter["bytes"]
        or hashlib.sha256(payload).hexdigest() != exporter["sha256"]
    ):
        raise ValueError("Exporter pin mismatch")
    (runtime / "mods" / exporter["filename"]).write_bytes(payload)
    if core is not None:
        stage_core(runtime, core)
    shutil.copy2(ROOT / "deploy/tui-lab/start.sh", runtime / "start.sh")
    generated = root / "metrics"
    generated.mkdir()
    services = {
        "lab-"
        + name: {
            "cgroup": "omk-tui-" + name,
            "target": name + ":19565",
            "release": "synthetic-work-forge112",
            "dimension_aliases": {},
        }
        for name in ("alpha", "beta")
    }
    monitoring = render(
        {"schema": 2, "host": "tui-sandbox", "services": services},
        {
            "OMK_METRICS_INTERVAL_SECONDS": "5",
            "OMK_METRICS_RETENTION_DAYS": "1",
            "OMK_METRICS_RETENTION_MIB": "256",
        },
    )
    for name, rendered in monitoring.items():
        value = rendered
        if name == "prometheus.json":
            document = json.loads(value)
            document["storage"]["tsdb"]["retention"]["time"] = "4h"
            value = json.dumps(document, indent=2) + "\n"
        (generated / name).write_text(value, encoding="utf-8", newline="\n")
    private = root / ".omk-admin"
    private.mkdir(mode=0o700)
    initialize(private)
    entries = ["schema=1"]
    for name, port in (("alpha", 25611), ("beta", 25621)):
        seed = root / name
        seed.mkdir()
        password = secrets.token_urlsafe(24)
        _write_private(
            private / ("rcon-" + name + ".json"), private, {"password": password}
        )
        (seed / "server.properties").write_text(
            f"motd=OMK TUI LAB {name.upper()} - synthetic work\n"
            f"online-mode=false\nserver-port=25565\nenable-rcon=true\nrcon.port=25575\nrcon.password={password}\n"
            "level-name=lab-world\nlevel-type=FLAT\ngenerator-settings=3;minecraft:bedrock,2*minecraft:dirt,minecraft:grass;1;\n"
            "view-distance=2\nmax-players=4\nspawn-protection=0\nmax-tick-time=60000\n",
            encoding="utf-8",
            newline="\n",
        )
        shutil.copy2(
            generated / ("lab-" + name + ".exporter.cfg"), seed / "exporter.cfg"
        )
        entries.extend(
            [
                f"[servers.lab-{name}]",
                f'root="../{name}"',
                f"[servers.lab-{name}.recovery]",
                f"port={port}",
                f'credential_file="rcon-{name}.json"',
            ]
        )
    (private / "operator.toml").write_text("\n".join(entries) + "\n", encoding="utf-8")
    _write_private(
        private / "tui.json",
        private,
        {
            "schema": 1,
            "host": "tui-sandbox",
            "prometheus_origin": "http://127.0.0.1:25690",
        },
    )
    manifest = {
        "schema": 1,
        "project": PROJECT,
        "runtime_forge_sha256": pin["sha256"],
        "servers": ["lab-alpha", "lab-beta"],
        "fixture": True,
    }
    (root / "fixture.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"prepared": str(root), "config": str(private / "operator.toml")}))


def compose(root, *arguments):
    manifest = json.loads((root / "fixture.json").read_bytes())
    if manifest.get("project") != PROJECT or manifest.get("fixture") is not True:
        raise ValueError("Not a recognized local TUI fixture")
    environment = {
        **os.environ,
        "OMK_TUI_LAB_ROOT": str(root.resolve()),
    }
    subprocess.run(
        [
            "docker",
            "compose",
            "--project-name",
            PROJECT,
            "-f",
            str(ROOT / "deploy/tui-lab/compose.yaml"),
            *arguments,
        ],
        env=environment,
        check=True,
        timeout=180,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["prepare", "up", "status", "stop"])
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--server-source", type=Path)
    parser.add_argument("--core", type=Path, help="Pinned OmkalityCore JAR for prepare")
    args = parser.parse_args()
    root = args.root.resolve()
    if args.action == "prepare":
        if args.server_source is None:
            parser.error("prepare requires --server-source")
        prepare(root, args.server_source, args.core)
    elif args.action == "up":
        compose(root, "up", "-d", "--build")
    elif args.action == "status":
        print(
            json.dumps(
                overview(root / ".omk-admin/operator.toml"),
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        for server in ("lab-alpha", "lab-beta"):
            result = console(
                root / ".omk-admin/operator.toml", server, "save", confirmed=True
            )
            if not result["ok"]:
                raise RuntimeError(
                    "Fixture save not confirmed; inspect before stopping"
                )
        compose(root, "stop", "-t", "30")


if __name__ == "__main__":
    main()
