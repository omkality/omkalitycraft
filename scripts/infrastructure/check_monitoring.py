"""Check generated monitoring configuration with the pinned real tool binaries."""

import argparse
import json
import os
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request
from contextlib import contextmanager
from ipaddress import IPv4Network
from pathlib import Path
from uuid import uuid4

from omk.monitoring_config import render

ROOT = Path(__file__).resolve().parents[2]
IMAGES = json.loads(
    (ROOT / "deploy/metrics/artifacts.json").read_text(encoding="utf-8")
)["images"]
PROMETHEUS = IMAGES["prometheus"]["image"]
TELEGRAF = IMAGES["telegraf"]["image"]
PYTHON = next(
    line.split()[1]
    for line in (ROOT / "Dockerfile.api").read_text(encoding="utf-8").splitlines()
    if line.startswith("FROM python:")
)


def execute(args, **kwargs):
    result = subprocess.run(
        args, capture_output=True, text=True, timeout=180, check=False, **kwargs
    )
    if result.returncode:
        raise RuntimeError((result.stdout + result.stderr)[-2000:])
    return result.stdout


@contextmanager
def mock_game(network, project):
    """Synthetic HTTP metrics, not a Minecraft/gameplay acceptance."""
    fixture = ROOT / "tests/fixtures/monitoring_exporter.py"
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


def check_health_policy(compose):
    containers = compose("ps", "-q", "prometheus", "agent").split()
    assert len(containers) == 2
    for row in json.loads(execute(["docker", "inspect", *containers])):
        policy = row["Config"]["Healthcheck"]
        assert policy["Interval"] == 2_000_000_000
        assert policy["Timeout"] == 1_000_000_000
        assert policy["Retries"] == 1
        assert row["State"]["Health"]["Status"] == "healthy"


def exercise_runtime(compose, query, wait, target_is, start_game):
    compose("up", "-d", "--build", "--wait", "--wait-timeout", "90")
    check_health_policy(compose)
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
            lambda: (
                bool(rows := query("omk_game_online")) and rows[0]["value"][1] == "2"
            )
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
        check_health_policy(compose)
        print("Monitoring smoke: recovered source", flush=True)
        wait(lambda: bool(query("mem_total")))


def runtime_overlay(folder, metrics_subnet, admin_subnet):
    overlay = folder / "compose.smoke.yaml"
    overlay.write_text(
        "services:\n  prometheus:\n    ports: !override\n"
        "      - target: 9090\n        host_ip: 127.0.0.1\n"
        + (
            "networks:\n"
            f"  metrics:\n    ipam:\n      config:\n        - subnet: {metrics_subnet}\n"
            f"  admin:\n    ipam:\n      config:\n        - subnet: {admin_subnet}\n"
            if metrics_subnet and admin_subnet
            else ""
        ),
        encoding="utf-8",
    )
    return overlay


def runtime_error(error, compose, opener, origin):
    diagnostics = compose("logs", "--no-color", "--tail", "12")
    if origin:
        try:
            with opener.open(f"{origin}/api/v1/targets", timeout=5) as response:
                targets = json.load(response)["data"]["activeTargets"]
                diagnostics += json.dumps(
                    [
                        {"job": target["labels"]["job"], "error": target["lastError"]}
                        for target in targets
                    ]
                )
        except OSError:
            pass
    return str(error) + "\n" + diagnostics[-2500:]


def check_runtime(source, subnets):
    identity = uuid4().hex
    project = "omk-monitoring-check-" + identity
    network = project + "-game"
    game_subnet, metrics_subnet, admin_subnet = subnets or (None, None, None)
    overlay = runtime_overlay(source.parent, metrics_subnet, admin_subnet)
    origin = None
    environment = {
        **os.environ,
        "OMK_METRICS_CONFIG": str(source),
        "OMK_METRICS_GAME_NETWORK": network,
        "OMK_METRICS_INTERVAL_SECONDS": "5",
        "OMK_METRICS_HEALTH_SECONDS": "2",
        "OMK_METRICS_HEALTH_TIMEOUT_SECONDS": "1",
        "OMK_METRICS_HEALTH_RETRIES": "1",
    }
    command = [
        "docker",
        "compose",
        "--project-name",
        project,
        "-f",
        str(ROOT / "deploy/metrics/compose.yaml"),
        "-f",
        str(overlay),
    ]
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def compose(*args):
        nonlocal origin
        output = execute([*command, *args], env=environment)
        if args[0] == "up":
            bound = execute(
                [*command, "port", "prometheus", "9090"], env=environment
            ).strip()
            if not bound.startswith("127.0.0.1:"):
                raise RuntimeError("Unexpected monitoring smoke loopback bind")
            origin = "http://" + bound
        return output

    def query(expression, at=None):
        params = {"query": expression}
        if at is not None:
            params["time"] = str(at)
        url = f"{origin}/api/v1/query?" + urllib.parse.urlencode(params)
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
            *(["--subnet", str(game_subnet)] if game_subnet else []),
            "--internal",
            "--label",
            "omkality.monitoring.check=" + identity,
            network,
        ]
    )
    try:
        exercise_runtime(
            compose, query, wait, target_is, lambda: mock_game(network, project)
        )
    except Exception as error:
        raise RuntimeError(runtime_error(error, compose, opener, origin)) from error
    finally:
        compose("down", "--volumes", "--timeout", "10")
        row = json.loads(execute(["docker", "network", "inspect", network]))[0]
        assert row["Labels"]["omkality.monitoring.check"] == identity
        execute(["docker", "network", "rm", network])


def main():
    """Run pinned monitoring binaries and confirm scrape/retention via loopback."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--subnets",
        nargs=3,
        type=IPv4Network,
        metavar=("GAME", "METRICS", "ADMIN"),
        help="Free IPv4 subnets for the three isolated smoke-test bridges",
    )
    args = parser.parse_args()
    config = json.loads((ROOT / "deploy/metrics/config.example.json").read_bytes())
    with tempfile.TemporaryDirectory(prefix="omk-monitoring-check-") as directory:
        folder = Path(directory)
        # This contains only synthetic configuration, shared with unprivileged
        # container users. POSIX TemporaryDirectory otherwise uses mode 0700.
        folder.chmod(0o755)
        for name, value in render(config, {}).items():
            target = folder / name
            target.write_text(value, encoding="utf-8", newline="\n")
            target.chmod(0o644)
        source = folder / "source.json"
        source.write_text(json.dumps(config), encoding="utf-8")
        source.chmod(0o644)
        metrics = ROOT / "deploy/metrics"
        assert (metrics / "Dockerfile.agent").read_text(encoding="utf-8").split()[
            1
        ] == TELEGRAF
        assert (metrics / "Dockerfile.configure").read_text(encoding="utf-8").split()[
            1
        ] == PYTHON
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
            assert compose["services"]["prometheus"]["image"] == PROMETHEUS
        assert all("docker.sock" not in v.get("source", "") for v in service["volumes"])
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
        check_runtime(source, args.subnets)
    print(
        "Monitoring config/rules, healthy Docker start, history restart and unknown-source recovery passed"
    )


if __name__ == "__main__":
    main()
