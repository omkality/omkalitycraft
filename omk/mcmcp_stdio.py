"""Small bounded JSONL client for the pinned local Orchestrator shim."""

import contextlib
import json
import os
import subprocess
import time

from omk.mcmcp_client import McpError


class OrchestratorClient:
    def __init__(self, cli, state, link_port=25680, bridge_port=25681):
        self.command = [
            str(cli),
            "--state-dir",
            str(state),
            "shim",
            "--mcp-port",
            str(bridge_port),
        ]
        self.env = {
            **os.environ,
            "MCMCP_ORCHESTRATOR_HOME": str(state),
            "MCMCP_LINK_PORT": str(link_port),
            "MCMCP_MCP_PORT": str(bridge_port),
        }
        self.process = None
        self.counter = 0
        self.buffer = bytearray()

    def _receive(self):
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if b"\n" in self.buffer:
                line, _, rest = self.buffer.partition(b"\n")
                self.buffer = bytearray(rest)
                try:
                    message = json.loads(line)
                except ValueError:
                    raise McpError("Invalid Orchestrator JSON frame") from None
                if isinstance(message, dict) and "id" in message:
                    return message
                continue  # bounded protocol notifications, not responses
            try:
                chunk = os.read(self.process.stdout.fileno(), 65536)
            except BlockingIOError:
                time.sleep(0.01)
                continue
            if not chunk:
                raise McpError("Orchestrator closed its output")
            self.buffer.extend(chunk)
            if len(self.buffer) > 16 * 1024**2:
                raise McpError("Orchestrator frame too large")
        raise McpError("Orchestrator response timed out")

    def request(self, method, params=None, *, notification=False):
        self.counter += 1
        body = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            body["params"] = params
        if not notification:
            body["id"] = self.counter
        try:
            self.process.stdin.write((json.dumps(body) + "\n").encode())
            self.process.stdin.flush()
            if notification:
                return None
            reply = self._receive()
        except OSError:
            raise McpError("Orchestrator response unavailable") from None
        if (
            not isinstance(reply, dict)
            or reply.get("id") != self.counter
            or "error" in reply
        ):
            raise McpError("Invalid Orchestrator response")
        return reply.get("result")

    def __enter__(self):
        self.process = subprocess.Popen(
            self.command,
            env=self.env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        try:
            # Python 3.12+ supports nonblocking anonymous pipes on Windows too.
            # No blocked reader thread can keep close() stuck when an app restarts.
            os.set_blocking(self.process.stdout.fileno(), False)
            result = self.request(
                "initialize",
                {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "omk-orchestrator-owner", "version": "1"},
                },
            )
            if (
                not isinstance(result, dict)
                or result.get("protocolVersion") != "2025-06-18"
            ):
                raise McpError("Unsupported Orchestrator protocol")
            self.request("notifications/initialized", notification=True)
        except Exception:
            self.__exit__()
            raise
        return self

    def __exit__(self, *exc):
        with contextlib.suppress(OSError):
            self.process.stdin.close()
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            self.process.wait(timeout=5)
        self.process.stdout.close()

    def roster(self):
        result = self.request(
            "tools/call", {"name": "mcmcp_instances", "arguments": {}}
        )
        if not isinstance(result, dict) or result.get("isError"):
            raise McpError("Cannot read Orchestrator roster")
        roster = result.get("structuredContent")
        if not isinstance(roster, dict) or not isinstance(
            roster.get("connected"), list
        ):
            raise McpError("Invalid Orchestrator roster")
        return roster
