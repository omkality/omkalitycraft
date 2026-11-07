"""Networkless read-only inspection worker. No plan/apply or Docker socket."""

import json
import re
import sys
from pathlib import Path

from omk.resource_reset_inventory import inspect_resource


def execute(request, source=Path("/server")):
    if sys.platform != "linux":
        raise ValueError("Resource inspection worker requires Linux")
    if (
        not isinstance(request, dict)
        or set(request) != {"schema", "action", "world", "dimension", "world_max_bytes"}
        or type(request["schema"]) is not int
        or request["schema"] != 1
        or request["action"] != "inspect"
        or not isinstance(request["world"], str)
        or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", request["world"])
        or type(request["world_max_bytes"]) is not int
        or not 1 <= request["world_max_bytes"] <= 1024**4
    ):
        raise ValueError("Invalid read-only resource inspection request")
    return inspect_resource(
        source,
        request["world"],
        request["dimension"],
        world_max_bytes=request["world_max_bytes"],
    )


if __name__ == "__main__":
    try:
        raw = sys.stdin.buffer.read(65537)
        if len(raw) > 65536:
            raise ValueError("Inspection request exceeds limit")
        print(json.dumps({"ok": True, "result": execute(json.loads(raw))}))
    except Exception as error:
        print(json.dumps({"ok": False, "error_type": type(error).__name__}))
        raise SystemExit(1) from None
