"""Small bounded JSONL client for the pinned local Orchestrator shim."""

import contextlib
import json
import os
import queue
import subprocess
import threading

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
        self.messages = queue.Queue(maxsize=32)

    def _read(self):
        while line := self.process.stdout.readline(16 * 1024**2 + 1):
            try:
                if len(line) > 16 * 1024**2:
                    raise ValueError("large frame")
                message = json.loads(line)
                if isinstance(message, dict) and "id" in message:
                    self.messages.put(message, timeout=1)
            except ValueError, queue.Full:
                self.messages.put(None, timeout=1)
                return
        self.messages.put(None, timeout=1)

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
            reply = self.messages.get(timeout=30)
        except OSError, queue.Empty:
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
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()
        try:
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
        self.reader.join(timeout=2)
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
