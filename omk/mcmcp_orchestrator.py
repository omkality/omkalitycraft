"""Owner-only refresh of an idle, pinned local control app. Never stop a game."""

import hashlib
import json
import time
from pathlib import Path

import psutil

from omk.fs import resolved
from omk.mcmcp_client import McpError
from omk.mcmcp_stdio import OrchestratorClient
from omk.profiles import PROJECT_ROOT


def idle_process(args):
    expected = resolved(args.orchestrator_cli.parent / "mcmcp-orchestrator-app.exe")
    bom = json.loads(
        (PROJECT_ROOT / "profiles/lab/mcmcp.json").read_text(encoding="utf-8")
    )
    for path, pinned in [
        (expected, bom["desktop_installer"]["app"]),
        (args.orchestrator_cli, bom["artifacts"][1]["executable"]),
    ]:
        if (
            not path.is_file()
            or path.stat().st_size != pinned["size"]
            or hashlib.sha256(path.read_bytes()).hexdigest() != pinned["sha256"]
        ):
            raise RuntimeError(
                "Control installation does not match the pinned artifacts"
            )
    with OrchestratorClient(
        args.orchestrator_cli, args.orchestrator_state, args.link_port, args.bridge_port
    ) as client:
        if client.roster()["connected"]:
            raise RuntimeError(
                "An active game is connected; do not refresh its orchestrator"
            )
    connections = psutil.net_connections(kind="tcp")
    pids = {
        c.pid
        for c in connections
        if c.status == psutil.CONN_LISTEN
        and c.laddr.ip == "127.0.0.1"
        and c.laddr.port == args.bridge_port
    }
    link_pids = {
        c.pid
        for c in connections
        if c.status == psutil.CONN_LISTEN
        and c.laddr.ip == "127.0.0.1"
        and c.laddr.port == args.link_port
    }
    if len(pids) != 1 or None in pids or pids != link_pids:
        raise RuntimeError("Cannot identify owned Orchestrator listener")
    process = psutil.Process(pids.pop())
    if resolved(Path(process.exe())) != expected:
        raise RuntimeError("Control app does not match the pinned owned installation")
    env = process.environ()
    if (
        resolved(Path(env.get("MCMCP_ORCHESTRATOR_HOME", "")))
        != resolved(args.orchestrator_state)
        or env.get("MCMCP_LINK_PORT") != str(args.link_port)
        or env.get("MCMCP_MCP_PORT") != str(args.bridge_port)
    ):
        raise RuntimeError("Control app belongs to another state or port profile")
    return process


def refresh_idle(args):
    process = idle_process(args)
    # Recheck immediately before stopping only the control plane; fail if a game arrived.
    with OrchestratorClient(
        args.orchestrator_cli, args.orchestrator_state, args.link_port, args.bridge_port
    ) as client:
        if client.roster()["connected"]:
            raise RuntimeError("A game connected during idle refresh")
        process.terminate()
        process.wait(timeout=10)
        # The official shim starts the same pinned sibling with our explicit environment,
        # replays initialize, and reconnects existing MCP clients after an app restart.
        deadline = time.monotonic() + 35
        while time.monotonic() < deadline:
            try:
                roster = client.roster()
                if roster["connected"]:
                    raise RuntimeError("A game appeared during refresh")
                return
            except McpError, OSError, psutil.Error:
                time.sleep(0.1)
        raise RuntimeError("Control app did not return after idle refresh")
