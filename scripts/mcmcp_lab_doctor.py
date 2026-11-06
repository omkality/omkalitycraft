"""Read-only HTTP cross-check for the explicitly owned Windows MCMCP lab.

Codex itself uses the upstream stdio orchestrator, not this diagnostic script.
Run from the repository root: python scripts/mcmcp_lab_doctor.py
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from omk.mcmcp_client import McpClient, McpError, owned_connection  # noqa: E402


def main():
    connection, token, pid = owned_connection(ROOT)
    with McpClient(connection["url"], token) as client:
        info = client.data(client.call("mcmcp_endpoint_info"))
        if (
            info.get("side") != "client"
            or info.get("process", {}).get("pid") != pid
            or info.get("instance", {}).get("name") != connection["instance_name"]
        ):
            raise McpError("Endpoint does not match owned lab process")
        tools = client.request("tools/list")
        names = {t["name"] for t in tools["tools"]}
        required = {"client_player_state", "client_gui_state", "client_quit"}
        if not required <= names:
            raise McpError("Required game tools missing")
        print(json.dumps({"ok": True, "side": "client", "tool_count": len(names)}))


if __name__ == "__main__":
    try:
        main()
    except McpError as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from None
