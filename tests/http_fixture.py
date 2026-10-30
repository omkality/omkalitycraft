"""A real loopback HTTP server serving only a temporary test repository."""

import contextlib
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit


@contextlib.contextmanager
def serve(folder: Path) -> Iterator[tuple[str, list]]:
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            relative = unquote(urlsplit(self.path).path).lstrip("/")
            if relative.startswith("releases/") and relative.endswith("/manifest"):
                relative += ".json"
            path = (folder / relative).resolve()
            if not path.is_relative_to(folder.resolve()) or not path.is_file():
                self.send_error(404)
                return
            data = path.read_bytes()
            offset = int(
                self.headers.get("Range", "bytes=0-").split("=")[1].split("-")[0]
            )
            requests.append((relative, offset))
            self.send_response(206 if offset else 200)
            self.send_header("Content-Length", str(len(data) - offset))
            if offset:
                self.send_header(
                    "Content-Range", f"bytes {offset}-{len(data)-1}/{len(data)}"
                )
            self.end_headers()
            self.wfile.write(data[offset:])

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
