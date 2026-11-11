"""Readonly candidate runtime/template binding, with no socket or lifecycle."""

import hashlib
import json
import re
import sys
from pathlib import Path

from omk import resource_reset_runtime
from omk.cold_backup_worker import digest
from omk.linux_restore_policy import _read

PROFILE_ROOT = Path("/src/profiles/runtime")


def execute(
    request, source=Path("/server"), storage=Path("/backup"), target=Path("/target")
):
    if not isinstance(request, dict) or set(request) != {"runtime", "binding"}:
        raise ValueError("Invalid slot proof request")
    receipt = resource_reset_runtime.execute(
        request["runtime"], source, storage, target
    )
    binding = request["binding"]
    if set(binding) != {
        "game_container_port",
        "rcon_container_port",
        "template_sha256",
        "logging_sha256",
    }:
        raise ValueError("Invalid slot binding")
    props = _read(target, "server.properties", limit=65536)
    for key, wanted in {
        "server-port": str(binding["game_container_port"]),
        "rcon.port": str(binding["rcon_container_port"]),
        "enable-rcon": "true",
        "online-mode": "true",
        "server-ip": "",
    }.items():
        values = re.findall(
            rb"^" + re.escape(key.encode()) + rb"=([^\r\n]*)\r?$", props, re.M
        )
        if values != [wanted.encode()]:
            raise ValueError(
                "Candidate properties do not match the explicit slot binding"
            )
    root = PROFILE_ROOT
    raw = (root / "forge112-server.json").read_bytes()
    logging = (root / "log4j-java8.json").read_bytes()
    if (
        hashlib.sha256(raw).hexdigest() != binding["template_sha256"]
        or hashlib.sha256(logging).hexdigest() != binding["logging_sha256"]
    ):
        raise ValueError("Runtime template changed")
    profile = json.loads(raw)
    for pin in [profile["forge"], profile["agent"], *json.loads(logging)["artifacts"]]:
        with (target / pin["path"]).open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != pin["sha256"]:
                raise ValueError("Candidate launch artifact pin mismatch")
    return {
        "runtime_receipt_sha256": digest(receipt),
        "binding_sha256": digest(binding),
        "properties_sha256": hashlib.sha256(props).hexdigest(),
    }


if __name__ == "__main__":
    try:
        raw = sys.stdin.buffer.read(65537)
        if len(raw) > 65536:
            raise ValueError("Oversized slot proof")
        print(json.dumps({"ok": True, "proof": execute(json.loads(raw))}))
    except Exception as error:
        print(json.dumps({"ok": False, "error_type": type(error).__name__}))
        raise SystemExit(1) from None
