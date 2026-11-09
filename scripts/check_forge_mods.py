"""Check the public Forge sources in a pinned, isolated compiler container."""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "mods/forge-1.12.2"
IMAGE = "omkalitycraft-mod-build:forge112-v1"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = (
        args.output or ROOT / ".local" / ("mod-build-" + uuid4().hex[:12])
    ).absolute()
    if output.exists() or output.is_symlink() or output.is_junction():
        raise ValueError("Mod verification output must be new")
    output.mkdir(parents=True)
    tools = SOURCE / "tools"
    subprocess.run([sys.executable, str(SOURCE / "fetch_inputs.py")], check=True)
    mountpoint = SOURCE / "build"
    if mountpoint.is_symlink() or mountpoint.is_junction():
        raise ValueError("Linked build mountpoint")
    mountpoint.mkdir(exist_ok=True)
    subprocess.run(
        [
            "docker",
            "build",
            "--tag",
            IMAGE,
            "--file",
            str(SOURCE / "Dockerfile.build"),
            str(SOURCE),
        ],
        check=True,
    )
    subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--pull",
            "never",
            "--network",
            "none",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges:true",
            "--memory",
            "1g",
            "--cpus",
            "2",
            "--pids-limit",
            "128",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=128m",
            "--label",
            "omkality.role=mod-build-check",
            "--mount",
            f"type=bind,source={SOURCE},target=/src,readonly",
            "--mount",
            f"type=bind,source={tools},target=/src/tools,readonly",
            "--mount",
            f"type=bind,source={output},target=/src/build",
            IMAGE,
        ],
        check=True,
    )
    result = json.loads((output / "verification.json").read_text())
    if not result["ok"]:
        raise RuntimeError("Mod verification failed")
    print("Verified mod artifacts: " + str(output))


if __name__ == "__main__":
    main()
