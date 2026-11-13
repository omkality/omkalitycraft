"""Check generated monitoring configuration with the pinned real tool binaries."""

import json
import os
import socket
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from omk.monitoring_config import render

ROOT = Path(__file__).resolve().parents[1]
PROMETHEUS = "prom/prometheus:v3.16.0@sha256:e04987641b57704f408e31f6373ba4138ecf27cb4a165d24aabb6c38fddd0f06"
TELEGRAF = "telegraf:1.40.3-alpine@sha256:10fe8c974752c8088858f012cb47b71f5bb67c5695829be56d87dfbf8e0092b8"
PYTHON = "python:3.14.2-slim@sha256:1a3c6dbfd2173971abba880c3cc2ec4643690901f6ad6742d0827bae6cefc925"


def execute(args, **kwargs):
    result = subprocess.run(
        args, capture_output=True, text=True, timeout=180, check=False, **kwargs
    )
    if result.returncode:
        raise RuntimeError((result.stdout + result.stderr)[-2000:])
    return result.stdout


@contextmanager
def mock_game(network, project, source):
    """Synthetic HTTP metrics, not a Minecraft/gameplay acceptance."""
    fixture = source.parent / "fake_exporter.py"
    fixture.write_text(
        "from http.server import BaseHTTPRequestHandler, HTTPServer\n"
        'body = b"""mc_player_list{id="fake-a",name="FakeA"} 1\n'
        'mc_player_list{id="fake-b",name="FakeB"} 1\n'
        'mc_dimension_tick_seconds_count{id="-11",name="spatial"} 10\n'
        'mc_dimension_tick_seconds_count{id="-27",name="orbit"} 20\n'
        'mc_dimension_chunks_loaded{id="-27",name="orbit"} 1\n'
        'mc_dimension_chunks_loaded{id="-27",name="orbit"} 2\n"""\n'
        "class Handler(BaseHTTPRequestHandler):\n"
        " def do_GET(self):\n"
        "  self.send_response(200)\n"
        '  self.send_header("Content-Type", "text/plain; version=0.0.4")\n'
        "  self.end_headers(); self.wfile.write(body)\n"
        " def log_message(self, *args): pass\n"
        'HTTPServer(("0.0.0.0",19565), Handler).serve_forever()\n',
        encoding="utf-8",
    )
    name = project + "-fake-game"
    execute(
        [
            "docker",
            "create",
            "--name",
            name,
            "--label",
            "omkality.monitoring.check=" + project,
            "--network",
            network,
            "--network-alias",
            "dj2",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--cpus",
            "0.25",
            "--memory",
            "64m",
            "--pids-limit",
            "32",
            "--log-driver",
            "local",
            "--log-opt",
            "max-size=1m",
            "--log-opt",
            "max-file=2",
            "--mount",
            f"type=bind,source={fixture},target=/fake_exporter.py,readonly",
            PYTHON,
            "python",
            "/fake_exporter.py",
        ]
    )
    try:
        execute(["docker", "start", name])
        yield
    finally:
        row = json.loads(execute(["docker", "inspect", name]))[0]
        assert row["Config"]["Labels"]["omkality.monitoring.check"] == project
        execute(["docker", "rm", "--force", name])


def exercise_runtime(compose, query, wait, target_is, start_game):
    compose("up", "-d", "--build", "--wait", "--wait-timeout", "90")
    print("Monitoring smoke: host metrics", flush=True)
    wait(lambda: bool(query("mem_total")))
    wait(lambda: bool(query('disk_free{path="/storage/project"}')))
    print("Monitoring smoke: unreachable game", flush=True)
    wait(lambda: target_is("dj2", "0"))
    assert query("omk_game_online") == []  # Unreachable game is not zero online.
    with start_game():
        print("Monitoring smoke: shared dimension types", flush=True)
        wait(lambda: target_is("dj2", "1"))
        wait(
            lambda: bool(
                query(
                    'mc_dimension_tick_seconds_count{dimension="2",dimension_type="-11"}'
                )
            )
        )
        unknown = query('mc_dimension_tick_seconds_count{dimension_type="-27"}')
        assert unknown and "dimension" not in unknown[0]["metric"]
        assert query("mc_dimension_chunks_loaded") == []
        wait(
            lambda: bool(rows := query("omk_game_online"))
            and rows[0]["value"][1] == "2"
        )
        at = time.time()
        before = query("mem_total", at)
        assert before and float(before[0]["value"][1]) > 0
        compose("restart", "prometheus")
        print("Monitoring smoke: historical sample after restart", flush=True)
        wait(lambda: query("mem_total", at) == before)
        compose("stop", "agent")
        print("Monitoring smoke: stopped source", flush=True)
        wait(lambda: target_is("host", "0"))
        # Raw/recording history can survive restart before the next good scrape.
        wait(lambda: query("mem_total and on(job,instance) (up == 1)") == [])
        compose("up", "-d", "--wait", "--wait-timeout", "90")
        print("Monitoring smoke: recovered source", flush=True)
        wait(lambda: bool(query("mem_total")))


def check_runtime(source):
    identity = uuid4().hex
    project = "omk-monitoring-check-" + identity
    network = project + "-game"
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    environment = {
        **os.environ,
        "OMK_METRICS_CONFIG": str(source),
        "OMK_METRICS_GAME_NETWORK": network,
        "OMK_METRICS_PORT": str(port),
        "OMK_METRICS_INTERVAL_SECONDS": "5",
        "OMK_METRICS_HEALTH_SECONDS": "2",
    }
    command = [
        "docker",
        "compose",
        "--project-name",
        project,
        "-f",
        str(ROOT / "deploy/metrics/compose.yaml"),
    ]
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def compose(*args):
        return execute([*command, *args], env=environment)

    def query(expression, at=None):
        params = {"query": expression}
        if at is not None:
            params["time"] = str(at)
        url = f"http://127.0.0.1:{port}/api/v1/query?" + urllib.parse.urlencode(params)
        with opener.open(url, timeout=5) as response:
            value = json.load(response)
        assert value["status"] == "success"
        return value["data"]["result"]

    def wait(predicate):
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            try:
                if predicate():
                    return
            except OSError:
                pass
            time.sleep(1)
        raise RuntimeError("Monitoring runtime condition did not arrive")

    def target_is(job, value):
        rows = query(f'up{{job="{job}"}}')
        return bool(rows) and rows[0]["value"][1] == value

    execute(
        [
            "docker",
            "network",
            "create",
            "--internal",
            "--label",
            "omkality.monitoring.check=" + identity,
            network,
        ]
    )
    try:
        exercise_runtime(
            compose, query, wait, target_is, lambda: mock_game(network, project, source)
        )
    except Exception as error:
        diagnostics = compose("logs", "--no-color", "--tail", "12")
        try:
            with opener.open(
                f"http://127.0.0.1:{port}/api/v1/targets", timeout=5
            ) as response:
                targets = json.load(response)["data"]["activeTargets"]
            diagnostics += json.dumps(
                [{"job": t["labels"]["job"], "error": t["lastError"]} for t in targets]
            )
        except OSError:
            pass
        raise RuntimeError(str(error) + "\n" + diagnostics[-2500:]) from error
    finally:
        compose("down", "--volumes", "--timeout", "10")
        row = json.loads(execute(["docker", "network", "inspect", network]))[0]
        assert row["Labels"]["omkality.monitoring.check"] == identity
        execute(["docker", "network", "rm", network])


def main():
    config = json.loads((ROOT / "deploy/metrics/config.example.json").read_bytes())
    with tempfile.TemporaryDirectory(prefix="omk-monitoring-check-") as directory:
        folder = Path(directory)
        for name, value in render(config, {}).items():
            (folder / name).write_text(value, encoding="utf-8", newline="\n")
        source = folder / "source.json"
        source.write_text(json.dumps(config), encoding="utf-8")
        compose = json.loads(
            execute(
                [
                    "docker",
                    "compose",
                    "-f",
                    str(ROOT / "deploy/metrics/compose.yaml"),
                    "config",
                    "--format",
                    "json",
                ],
                env={
                    **os.environ,
                    "OMK_METRICS_CONFIG": str(source),
                    "OMK_METRICS_GAME_NETWORK": "omk-validation-only",
                },
            )
        )
        assert set(compose["services"]) == {"configure", "prometheus", "agent"}
        assert set(compose["services"]["agent"]["networks"]) == {"metrics"}
        probe = next(
            v
            for v in compose["services"]["agent"]["volumes"]
            if v["target"] == "/storage/project"
        )
        assert probe["type"] == "volume" and probe["source"] == "filesystem_probe"
        assert compose["networks"]["metrics"]["internal"]
        assert set(compose["services"]["prometheus"]["networks"]) == {
            "metrics",
            "game",
            "admin",
        }
        for service in compose["services"].values():
            assert service["read_only"] and service["cap_drop"] == ["ALL"]
            assert not service.get("privileged") and not service.get("pid")
            assert all(
                "docker.sock" not in v.get("source", "") for v in service["volumes"]
            )
        assert all(
            port["host_ip"] == "127.0.0.1"
            for service in compose["services"].values()
            for port in service.get("ports", [])
        )
        common = [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--cpus",
            "1",
            "--memory",
            "128m",
            "--tmpfs",
            "/tmp:rw,nosuid,size=32m,mode=1777",
            "--mount",
            f"type=bind,source={folder},target=/etc/omk-metrics,readonly",
        ]
        execute(
            [
                *common,
                "--entrypoint",
                "promtool",
                PROMETHEUS,
                "check",
                "config",
                "/etc/omk-metrics/prometheus.json",
            ]
        )
        execute(
            [
                *common,
                "--mount",
                f"type=bind,source={ROOT / 'tests/fixtures/monitoring-rules.json'},target=/rules.json,readonly",
                "--entrypoint",
                "promtool",
                PROMETHEUS,
                "test",
                "rules",
                "/rules.json",
            ]
        )
        execute(
            [
                *common,
                "--entrypoint",
                "telegraf",
                TELEGRAF,
                "--config",
                "/etc/omk-metrics/telegraf.conf",
                "--input-filter",
                "cpu",
                "--test",
            ]
        )
        check_runtime(source)
    print(
        "Monitoring config/rules, healthy Docker start, history restart and unknown-source recovery passed"
    )


if __name__ == "__main__":
    main()
