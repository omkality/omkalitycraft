from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest

from omk.drasl import DraslClient, DraslError


@pytest.mark.parametrize(
    "origin",
    [
        "http://example.com",
        "http://localhost.example.com",
        "https://user:password@example.com",
        "https://example.com?token=secret",
        "https://example.com#fragment",
    ],
)
def test_unsafe_auth_origin_is_rejected(origin: str) -> None:
    with pytest.raises(ValueError):
        DraslClient(origin)


@pytest.fixture
def auth_origin() -> Iterator[tuple[str, list[str]]]:
    seen: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            seen.append(self.path)
            if self.path == "/redirect":
                self.send_response(302)
                self.send_header("Location", "/must-not-follow")
                self.end_headers()
                return
            self.send_response(403)
            self.end_headers()
            self.wfile.write(b'{"secret":"must-not-be-printed"}')

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", seen
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_auth_request_does_not_follow_redirect(
    auth_origin: tuple[str, list[str]],
) -> None:
    origin, seen = auth_origin
    with pytest.raises(DraslError) as error:
        DraslClient(origin).request("GET", "/redirect", token="test-token")
    assert error.value.status == 302
    assert seen == ["/redirect"]


def test_auth_error_does_not_expose_response_body(
    auth_origin: tuple[str, list[str]],
) -> None:
    origin, _ = auth_origin
    with pytest.raises(DraslError) as error:
        DraslClient(origin).request("GET", "/error")
    assert error.value.status == 403
    assert "must-not-be-printed" not in str(error.value)
