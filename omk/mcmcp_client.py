"""Owner lab tooling only: bounded, authenticated MCP HTTP to one local game.

This is deliberately independent of the player launcher and its authentication.
"""

import contextlib
import json
import re
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener

import psutil

from omk.drasl import _NoRedirect
from omk.fs import resolved

MAX_RESPONSE = 16 * 1024**2


class McpError(RuntimeError):
    """No response bodies, headers or credentials in exception messages."""


def owned_connection(root: Path):
    try:
        return _owned_connection(root)
    except OSError, ValueError, KeyError, TypeError:
        raise McpError("Cannot read owned lab connection") from None


def _owned_connection(root: Path):
    root = resolved(root)
    pointer = root / ".local/mcmcp-client-latest.json"
    if resolved(pointer) != pointer or pointer.stat().st_size > 4096:
        raise McpError("Invalid lab pointer")
    lab = Path(json.loads(pointer.read_text(encoding="utf-8"))["lab"])
    if (
        resolved(lab) != lab.absolute()
        or lab.parent != root / ".local"
        or not re.fullmatch(r"mcmcp-client-[a-f0-9]{12}", lab.name)
    ):
        raise McpError("Connection is outside the owned lab")
    run = lab.name.removeprefix("mcmcp-client-")
    marker = lab / ".omk-owned-mcmcp-client-lab"
    if (
        resolved(marker) != marker
        or marker.stat().st_size > 64
        or marker.read_text(encoding="utf-8") != run
    ):
        raise McpError("Lab ownership marker mismatch")
    paths = [lab / "mcp-connection.json", lab / "native-validation.json"]
    if any(p.stat().st_size > 65536 or resolved(p) != p for p in paths):
        raise McpError("Invalid lab metadata")
    connection, report = [json.loads(p.read_text(encoding="utf-8")) for p in paths]
    config = lab / "portable/instances/dj2/config/mcmcp.cfg"
    if (
        connection.get("schema") != 1
        or connection.get("url") != "http://127.0.0.1:25685/mcp"
        or Path(connection.get("config", "")) != config
        or connection.get("instance_name") != "OmkalityCraft DJ2 isolated " + run
        or resolved(config) != config
        or config.stat().st_size > 65536
    ):
        raise McpError("Invalid lab endpoint configuration")
    java = resolved(lab / "portable/instances/dj2/runtime/jre/bin/java.exe")
    if type(report.get("game_pid")) is not int or report.get("phase") in {
        "complete",
        "failed",
    }:
        raise McpError("The owned game is not running")
    try:
        process = psutil.Process(report["game_pid"])
        if resolved(Path(process.exe())) != java or not process.is_running():
            raise McpError("Game process ownership mismatch")
    except psutil.Error:
        raise McpError("The owned game is unavailable") from None
    matches = re.findall(
        r"^\s*S:authToken=([a-f0-9]{64})\s*$",
        config.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    if len(matches) != 1:
        raise McpError("Invalid lab credential")
    return connection, matches[0], report["game_pid"]


class McpClient:
    def __init__(self, url: str, token: str, *, timeout=40):
        if url != "http://127.0.0.1:25685/mcp" or not re.fullmatch(
            r"[a-f0-9]{64}", token
        ):
            raise McpError("Only the explicit local lab endpoint is supported")
        self.url, self._token, self.timeout = url, token, timeout
        self._session = None
        self._next_id = 0
        self._opener = build_opener(ProxyHandler({}), _NoRedirect())

    def _send(self, method, payload=None):
        headers = {
            "Authorization": "Bearer " + self._token,
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": "2025-06-18",
        }
        if self._session:
            headers["Mcp-Session-Id"] = self._session
        request = Request(
            self.url,
            data=None if payload is None else json.dumps(payload).encode(),
            headers=headers,
            method=method,
        )
        try:
            with self._opener.open(request, timeout=self.timeout) as response:
                body = response.read(MAX_RESPONSE + 1)
                if len(body) > MAX_RESPONSE:
                    raise McpError("MCP response too large")
                session = response.headers.get("Mcp-Session-Id")
                if session:
                    if not re.fullmatch(r"[A-Za-z0-9_-]{1,256}", session):
                        raise McpError("Invalid MCP session header")
                    self._session = session
                return json.loads(body) if body else None
        except HTTPError as error:
            status = error.code
            error.close()
            raise McpError("MCP HTTP status " + str(status)) from None
        except OSError, ValueError:
            raise McpError("MCP transport response unavailable or invalid") from None

    def request(self, method, params=None, *, notification=False):
        payload = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            payload["params"] = params
        if not notification:
            self._next_id += 1
            payload["id"] = self._next_id
        result = self._send("POST", payload)
        if notification:
            return None
        if (
            not isinstance(result, dict)
            or result.get("id") != self._next_id
            or "error" in result
        ):
            raise McpError("MCP request failed")
        return result.get("result")

    def __enter__(self):
        try:
            result = self.request(
                "initialize",
                {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "omkality-lab", "version": "1"},
                },
            )
            if (
                not isinstance(result, dict)
                or result.get("protocolVersion") != "2025-06-18"
            ):
                raise McpError("Unsupported MCP protocol")
            self.request("notifications/initialized", notification=True)
        except Exception:
            self.__exit__()
            raise
        return self

    def __exit__(self, *exc):
        if self._session:
            with contextlib.suppress(OSError, McpError):
                self._send("DELETE")

    def call(self, name, arguments=None):
        result = self.request(
            "tools/call", {"name": name, "arguments": arguments or {}}
        )
        if not isinstance(result, dict) or result.get("isError"):
            raise McpError("MCP tool failed: " + name)
        return result

    @staticmethod
    def data(result):
        if "structuredContent" in result:
            return result["structuredContent"]
        for item in result.get("content", []):
            if item.get("type") == "text":
                try:
                    return json.loads(item["text"])
                except ValueError, TypeError:
                    return item["text"]
        return None
