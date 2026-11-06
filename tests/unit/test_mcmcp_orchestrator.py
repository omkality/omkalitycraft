import hashlib
import json
from argparse import Namespace
from unittest.mock import Mock

import pytest

from omk import mcmcp_orchestrator as module
from omk.mcmcp_client import McpError
from omk.mcmcp_stdio import OrchestratorClient


class Client:
    def __init__(self, roster):
        self.value = roster

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def roster(self):
        return self.value


def fixture(tmp_path, monkeypatch):
    app = tmp_path / "bin/mcmcp-orchestrator-app.exe"
    app.parent.mkdir()
    app.write_bytes(b"owned pinned app")
    args = Namespace(
        orchestrator_cli=app.with_name("mcmcp-orchestrator.exe"),
        orchestrator_state=tmp_path / "state",
        link_port=25680,
        bridge_port=25681,
    )
    args.orchestrator_cli.write_bytes(b"pinned shim")
    bom = tmp_path / "profiles/lab/mcmcp.json"
    bom.parent.mkdir(parents=True)
    bom.write_text(
        json.dumps(
            {
                "artifacts": [
                    {},
                    {
                        "executable": {
                            "size": args.orchestrator_cli.stat().st_size,
                            "sha256": hashlib.sha256(
                                args.orchestrator_cli.read_bytes()
                            ).hexdigest(),
                        }
                    },
                ],
                "desktop_installer": {
                    "app": {
                        "size": app.stat().st_size,
                        "sha256": hashlib.sha256(app.read_bytes()).hexdigest(),
                    }
                },
            }
        )
    )
    monkeypatch.setattr(module, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(
        module, "OrchestratorClient", lambda *a: Client({"connected": []})
    )
    monkeypatch.setattr(
        module.psutil,
        "net_connections",
        lambda **kw: [
            Namespace(
                pid=123,
                status=module.psutil.CONN_LISTEN,
                laddr=Namespace(ip="127.0.0.1", port=25681),
            ),
            Namespace(
                pid=123,
                status=module.psutil.CONN_LISTEN,
                laddr=Namespace(ip="127.0.0.1", port=25680),
            ),
        ],
    )
    proc = Mock()
    proc.exe.return_value = str(app)
    proc.environ.return_value = {
        "MCMCP_ORCHESTRATOR_HOME": str(args.orchestrator_state),
        "MCMCP_LINK_PORT": "25680",
        "MCMCP_MCP_PORT": "25681",
    }
    monkeypatch.setattr(module.psutil, "Process", lambda _: proc)
    return args, proc, app


def test_connected_game_prevents_even_process_lookup(tmp_path, monkeypatch):
    args, proc, _ = fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(
        module,
        "OrchestratorClient",
        lambda *a: Client({"connected": [{"id": "someone.client"}]}),
    )
    with pytest.raises(RuntimeError, match="active game"):
        module.refresh_idle(args)
    proc.terminate.assert_not_called()


@pytest.mark.parametrize("bad", ["path", "hash", "state", "port"])
def test_unowned_control_process_is_never_stopped(tmp_path, monkeypatch, bad):
    args, proc, app = fixture(tmp_path, monkeypatch)
    if bad == "path":
        proc.exe.return_value = str(app.with_name("someone.exe"))
    if bad == "hash":
        app.write_bytes(b"modified app")
    if bad == "state":
        proc.environ.return_value["MCMCP_ORCHESTRATOR_HOME"] = str(tmp_path / "someone")
    if bad == "port":
        proc.environ.return_value["MCMCP_LINK_PORT"] = "25580"
    with pytest.raises(RuntimeError):
        module.refresh_idle(args)
    proc.terminate.assert_not_called()


def test_second_roster_check_prevents_stopping_newly_connected_game(
    tmp_path, monkeypatch
):
    args, proc, _ = fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(module, "idle_process", lambda _: proc)
    monkeypatch.setattr(
        module, "OrchestratorClient", lambda *a: Client({"connected": [{}]})
    )
    with pytest.raises(RuntimeError, match="during idle"):
        module.refresh_idle(args)
    proc.terminate.assert_not_called()


def test_idle_refresh_only_stops_owned_control_app_and_reconnects(
    tmp_path, monkeypatch
):
    args, proc, _ = fixture(tmp_path, monkeypatch)
    module.refresh_idle(args)
    proc.terminate.assert_called_once_with()
    proc.wait.assert_called_once_with(timeout=10)


def test_stdio_rpc_error_does_not_expose_response_content():
    client = OrchestratorClient("owned.exe", "state")
    client.process = Mock()
    client.messages.put({"id": 1, "error": {"message": "secret-sentinel"}})
    with pytest.raises(McpError) as error:
        client.request("tools/list")
    assert "secret-sentinel" not in str(error.value)


def test_roster_requires_structured_connected_list(monkeypatch):
    client = OrchestratorClient("owned.exe", "state")
    monkeypatch.setattr(
        client, "request", lambda *a: {"structuredContent": {"connected": "wrong"}}
    )
    with pytest.raises(McpError):
        client.roster()
