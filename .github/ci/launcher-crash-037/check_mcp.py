import json
import os
import re
import sys
from pathlib import Path
from time import monotonic, sleep

tools_root = Path(__file__).resolve().parent.parent
lab = Path(os.environ.get("OMK_CRASH_PROBE_ROOT", str(Path(__file__).resolve().parent)))
assert (lab / "OWNED_CRASH_PROBE").is_file()
sys.path.insert(0, os.environ.get("OMK_CRASH_TEST_REPO", str(tools_root / "full-dj2-crash-check")))

from omk.labs.mcp.mcmcp_client import McpClient, McpError

state = json.loads((lab / "probe-state.json").read_text(encoding="utf-8"))
assert state["mode"] == sys.argv[1] and state["phase"] == "java-started"
config = (lab / "client/instances/dj2/config/mcmcp.cfg").read_text()
token = re.search(r"^\s*S:authToken=([a-f0-9]{64})\s*$", config, re.M)[1]
deadline = monotonic() + 370
while monotonic() < deadline:
    try:
        with McpClient(state["mcp_endpoint"], token, timeout=7) as mcp:
            gui = mcp.data(mcp.call("client_gui_state"))
            if gui.get("screenClass") == "lumien.custommainmenu.gui.GuiCustom" and not gui.get("worldLoaded"):
                print("SIGNED_DJ2_MAIN_MENU_MCP", state["mode"], flush=True)
                if state["mode"] == "no-report":
                    (lab / "request-log-only-failure").write_text("controlled termination after menu\n")
                elif state["mode"] == "report" and "--trigger" in sys.argv:
                    (lab / "request-client-crash").write_text("controlled crash after menu\n")
                elif state["mode"] == "normal":
                    mcp.call("client_quit", {"leaveWorld": True})
                    print("MCP_REQUESTED_NORMAL_EXIT", flush=True)
                break
    except McpError:
        pass
    sleep(2)
else:
    raise SystemExit("Full graphical menu check timed out")
