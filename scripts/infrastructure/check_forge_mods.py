"""Check the public Forge sources in a pinned, isolated compiler container."""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "mods/forge-1.12.2"


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
    tools = output / "tools"
    run_checked(
        "compile inputs",
        [sys.executable, str(SOURCE / "fetch_inputs.py"), "--cache", str(tools)],
        timeout=180,
    )
    for name in ("build", "tools"):
        mountpoint = SOURCE / name
        if mountpoint.is_symlink() or mountpoint.is_junction():
            raise ValueError("Linked build mountpoint")
        mountpoint.mkdir(exist_ok=True)
    build_in_container(output, tools)


def run_checked(phase: str, args: list[str], *, timeout: int) -> None:
    """Run one bounded compiler phase and preserve useful phase information."""
    try:
        subprocess.run(args, timeout=timeout, check=True)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Forge {phase} exceeded {timeout}s") from None
    except subprocess.CalledProcessError as error:
        raise RuntimeError(f"Forge {phase} exited {error.returncode}") from error


def build_in_container(output: Path, tools: Path) -> None:
    """Compile using the image ID and container owned by this invocation."""
    name = "omk-forge-check-" + uuid4().hex[:12]
    tag = name + ":compiler"
    iidfile = output / "compiler.iid"
    try:
        run_checked(
            "image build",
            [
                "docker",
                "build",
                "--iidfile",
                str(iidfile),
                "--tag",
                tag,
                "--file",
                str(SOURCE / "Dockerfile.build"),
                str(SOURCE),
            ],
            timeout=300,
        )
        image = iidfile.read_text(encoding="ascii").strip()
        run_checked(
            "compilation",
            [
                "docker",
                "run",
                "--rm",
                "--name",
                name,
                "--pull",
                "never",
                "--network",
                "none",
                "--read-only",
                "--user",
                f"{os.getuid()}:{os.getgid()}" if os.name == "posix" else "0:0",
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
                image,
            ],
            timeout=180,
        )
    finally:
        for resource in (["rm", "-f", name], ["image", "rm", tag]):
            subprocess.run(
                ["docker", *resource], capture_output=True, timeout=30, check=False
            )
    result = json.loads((output / "verification.json").read_text())
    if not result["ok"]:
        raise RuntimeError("Mod verification failed")
    print("Verified mod artifacts: " + str(output))


if __name__ == "__main__":
    main()
