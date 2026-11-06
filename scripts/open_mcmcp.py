"""Open the pinned Windows desktop app with the same profile as Codex's shim."""

import argparse
import hashlib
import json
import os
import subprocess
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def launch_plan(root: Path):
    config = tomllib.loads((root / ".codex/config.toml").read_text(encoding="utf-8"))[
        "mcp_servers"
    ]["omk_dj2_lab"]
    cli = Path(config["command"])
    app = cli.with_name("mcmcp-orchestrator-app.exe")
    bom = json.loads((root / "profiles/lab/mcmcp.json").read_text(encoding="utf-8"))
    for path, pinned in [
        (cli, bom["artifacts"][1]["executable"]),
        (app, bom["desktop_installer"]["app"]),
    ]:
        if (
            path.stat().st_size != pinned["size"]
            or hashlib.sha256(path.read_bytes()).hexdigest() != pinned["sha256"]
        ):
            raise ValueError("MCMCP installation differs from pinned artifacts")
    names = ["MCMCP_ORCHESTRATOR_HOME", "MCMCP_LINK_PORT", "MCMCP_MCP_PORT"]
    env = {name: config["env"][name] for name in names}
    if (
        not Path(env[names[0]]).resolve().is_relative_to((root / ".local").resolve())
        or not all(1024 <= int(env[n]) <= 65535 for n in names[1:])
        or int(env[names[1]]) == int(env[names[2]])
    ):
        raise ValueError("Invalid project MCP state or ports")
    return app, env


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="Verify without opening a window"
    )
    args = parser.parse_args()
    app, env = launch_plan(ROOT)
    if args.check:
        print(
            json.dumps(
                {"ok": True, "pinned_installation": True, "project_profile": True}
            )
        )
        return
    if os.name != "nt":
        raise ValueError("This desktop installation is Windows-only")
    # Explicit manual open: show the existing app through its single-instance handler.
    subprocess.Popen(
        [str(app)],
        env={**os.environ, **env},
        cwd=app.parent,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
    )


if __name__ == "__main__":
    main()
