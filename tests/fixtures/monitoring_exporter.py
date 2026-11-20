"""Synthetic game metrics for the real Compose scrape and PromQL checks."""

from http.server import BaseHTTPRequestHandler, HTTPServer

METRICS = b"""mc_player_list{id="fake-a",name="FakeA"} 1
mc_player_list{id="fake-b",name="FakeB"} 1
mc_dimension_tick_seconds_count{id="-11",name="spatial"} 10
mc_dimension_tick_seconds_count{id="-27",name="orbit"} 20
mc_dimension_chunks_loaded{id="-27",name="orbit"} 1
mc_dimension_chunks_loaded{id="-27",name="orbit"} 2
"""


class Exporter(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4")
        self.end_headers()
        self.wfile.write(METRICS)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    HTTPServer(("0.0.0.0", 19565), Exporter).serve_forever()
