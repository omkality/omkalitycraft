import io
import json
from types import SimpleNamespace
from unittest.mock import Mock
from urllib.error import HTTPError

import pytest

from omk.drasl import _NoRedirect
from omk.mcmcp_client import McpClient, McpError, owned_connection

TOKEN = "a" * 64


def fixture(tmp_path, monkeypatch):
    run = "1" * 12
    lab = tmp_path / ".local" / ("mcmcp-client-" + run)
    folder = lab / "portable/instances/dj2"
    config = folder / "config/mcmcp.cfg"
    config.parent.mkdir(parents=True)
    config.write_text("endpoints {\n S:authToken=" + TOKEN + "\n}\n")
    (lab / ".omk-owned-mcmcp-client-lab").write_text(run)
    (tmp_path / ".local/mcmcp-client-latest.json").write_text(
        json.dumps({"lab": str(lab)})
    )
    (lab / "mcp-connection.json").write_text(
        json.dumps(
            {
                "schema": 1,
                "url": "http://127.0.0.1:25685/mcp",
                "config": str(config),
                "instance_name": "OmkalityCraft DJ2 isolated " + run,
            }
        )
    )
    (lab / "native-validation.json").write_text('{"game_pid":123,"phase":"loading"}')
    java = folder / "runtime/jre/bin/java.exe"
    monkeypatch.setattr(
        "omk.mcmcp_client.psutil.Process",
        lambda pid: SimpleNamespace(exe=lambda: str(java), is_running=lambda: True),
    )
    return lab, config


@pytest.mark.parametrize(
    "bad",
    [
        "marker",
        "dead",
        "pid-reused",
        "endpoint",
        "config-path",
        "duplicate-token",
        "large-metadata",
    ],
)
def test_header_source_refuses_unowned_or_ambiguous_game(tmp_path, monkeypatch, bad):
    lab, config = fixture(tmp_path, monkeypatch)
    if bad == "marker":
        (lab / ".omk-owned-mcmcp-client-lab").write_text("wrong")
    elif bad == "dead":
        (lab / "native-validation.json").write_text(
            '{"game_pid":123,"phase":"complete"}'
        )
    elif bad == "pid-reused":
        monkeypatch.setattr(
            "omk.mcmcp_client.psutil.Process",
            lambda pid: SimpleNamespace(
                exe=lambda: str(tmp_path / "other.exe"), is_running=lambda: True
            ),
        )
    elif bad in {"endpoint", "config-path"}:
        p = lab / "mcp-connection.json"
        d = json.loads(p.read_text())
        d["url" if bad == "endpoint" else "config"] = "https://unexpected.example/mcp"
        p.write_text(json.dumps(d))
    elif bad == "duplicate-token":
        config.write_text("S:authToken=" + TOKEN + "\nS:authToken=" + TOKEN + "\n")
    else:
        (lab / "mcp-connection.json").write_text(" " * 65537)
    with pytest.raises(McpError) as error:
        owned_connection(tmp_path)
    assert TOKEN not in str(error.value)


def test_owned_header_source_keeps_token_separate_from_metadata(tmp_path, monkeypatch):
    fixture(tmp_path, monkeypatch)
    metadata, token, pid = owned_connection(tmp_path)
    assert TOKEN not in json.dumps(metadata)
    assert token == TOKEN and pid == 123


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/mcp",
        "http://127.0.0.1:25685/mcp?x=1",
        "http://user:pass@127.0.0.1:25685/mcp",
    ],
)
def test_transport_cannot_send_credential_to_arbitrary_url(url):
    with pytest.raises(McpError):
        McpClient(url, TOKEN)


def test_http_error_never_echoes_headers_body_or_url(monkeypatch):
    client = McpClient("http://127.0.0.1:25685/mcp", TOKEN)
    client._opener.open = Mock(
        side_effect=HTTPError(
            "http://secret-sentinel", 403, "secret-sentinel", {}, None
        )
    )
    with pytest.raises(McpError, match="403") as error:
        client.request("tools/list")
    assert "secret-sentinel" not in str(error.value) and TOKEN not in str(error.value)


@pytest.mark.parametrize(
    "response",
    [{"id": 999, "result": {}}, {"id": 1, "error": {"message": "secret-sentinel"}}, []],
)
def test_wrong_reply_id_or_rpc_error_is_not_success(monkeypatch, response):
    client = McpClient("http://127.0.0.1:25685/mcp", TOKEN)
    monkeypatch.setattr(client, "_send", lambda *a: response)
    with pytest.raises(McpError) as error:
        client.request("tools/list")
    assert "secret-sentinel" not in str(error.value)


def test_tool_is_error_is_not_accepted_as_a_game_action(monkeypatch):
    client = McpClient("http://127.0.0.1:25685/mcp", TOKEN)
    monkeypatch.setattr(
        client,
        "request",
        lambda *a: {"isError": True, "content": [{"text": "secret-sentinel"}]},
    )
    with pytest.raises(McpError) as error:
        client.call("client_quit")
    assert "secret-sentinel" not in str(error.value)


def response(body, headers=None):
    stream = io.BytesIO(body)
    stream.headers = headers or {}
    return stream


def test_session_initialize_notification_call_and_delete(monkeypatch):
    client = McpClient("http://127.0.0.1:25685/mcp", TOKEN)
    replies = iter(
        [
            response(
                b'{"id":1,"result":{"protocolVersion":"2025-06-18"}}',
                {"Mcp-Session-Id": "owned-session"},
            ),
            response(b""),
            response(b'{"id":2,"result":{"tools":[]}}'),
            response(b""),
        ]
    )
    sent = []

    def send(request, **kwargs):
        sent.append(request)
        return next(replies)

    monkeypatch.setattr(client._opener, "open", send)
    with client:
        assert client.request("tools/list") == {"tools": []}
    assert [r.method for r in sent] == ["POST", "POST", "POST", "DELETE"]
    assert sent[0].get_header("Mcp-session-id") is None
    assert all(r.get_header("Mcp-session-id") == "owned-session" for r in sent[1:])
    assert "id" not in json.loads(sent[1].data)
    assert all(r.get_header("Authorization") == "Bearer " + TOKEN for r in sent)


@pytest.mark.parametrize("kind", ["oversize", "invalid-json", "bad-session"])
def test_untrusted_wire_response_is_bounded_and_redacted(monkeypatch, kind):
    monkeypatch.setattr("omk.mcmcp_client.MAX_RESPONSE", 64)
    client = McpClient("http://127.0.0.1:25685/mcp", TOKEN)
    body = b"secret-sentinel" if kind == "invalid-json" else b"x" * 65
    headers = {}
    if kind == "bad-session":
        body = b"{}"
        headers = {"Mcp-Session-Id": "secret-sentinel\r\nInjected: true"}
    monkeypatch.setattr(
        client._opener, "open", lambda *a, **kw: response(body, headers)
    )
    with pytest.raises(McpError) as error:
        client.request("tools/list")
    assert "secret-sentinel" not in str(error.value)


def test_initialize_failure_releases_already_created_session(monkeypatch):
    client = McpClient("http://127.0.0.1:25685/mcp", TOKEN)
    replies = iter(
        [
            response(
                b'{"id":1,"result":{"protocolVersion":"unsupported"}}',
                {"Mcp-Session-Id": "owned"},
            ),
            response(b""),
        ]
    )
    sent = []

    def send(request, **kw):
        sent.append(request.method)
        return next(replies)

    monkeypatch.setattr(client._opener, "open", send)
    with pytest.raises(McpError, match="protocol"), client:
        pytest.fail("Unsupported version accepted")
    assert sent == ["POST", "DELETE"]


def test_plain_text_tool_result_is_not_mistaken_for_invalid_json():
    assert McpClient.data({"content": [{"type": "text", "text": "Held K"}]}) == "Held K"
    assert McpClient.data({"content": [{"type": "text", "text": '{"ok":true}'}]}) == {
        "ok": True
    }


def test_redirect_handler_will_not_forward_bearer_to_another_origin():
    assert (
        _NoRedirect().redirect_request(None, None, 302, "", {}, "http://other/") is None
    )
