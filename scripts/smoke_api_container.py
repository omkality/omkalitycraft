"""Exercise the actual API image and Compose with fresh, loopback-only lab data."""

import argparse
import json
import os
import shutil
import subprocess
import time
from ipaddress import IPv4Network
from pathlib import Path
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


class DockerFailure(RuntimeError):
    def __init__(self, phase: str, exit_code: int, stderr: str):
        self.phase = phase
        self.exit_code = exit_code
        self.category = docker_failure_category(stderr)
        super().__init__(f"{phase}: {self.category} (exit {exit_code})")


def docker_failure_category(stderr: str) -> str:
    message = stderr.lower()
    if "all predefined address pools have been fully subnetted" in message:
        return "network_pool_exhausted"
    if "port is already allocated" in message or "address already in use" in message:
        return "address_in_use"
    if "cannot connect to the docker daemon" in message:
        return "daemon_unavailable"
    return "docker_error"


def main():  # noqa: PLR0915 -- ordered real-container scenario with one owned cleanup path
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--subnet", type=IPv4Network, help="Explicit free subnet for this lab only"
    )
    args = parser.parse_args()
    run = uuid4().hex[:12]
    lab = ROOT / ".local" / ("api-runtime-" + run)
    lab.mkdir(parents=True)
    content = lab / "content"
    (content / "instances" / "fixture").mkdir(parents=True)
    project = "omk-api-" + run
    image = project + ":lab"
    default_container = project + "-default"
    env_file, overlay = lab / "compose.env", lab / "compose.override.yaml"
    internal_port = 8107
    overlay.write_text(
        f"services:\n  api:\n    image: {image}\n    ports: !override\n"
        f"      - target: {internal_port}\n        host_ip: 127.0.0.1\n        protocol: tcp\n"
        + (
            f"networks:\n  default:\n    ipam:\n      config:\n        - subnet: {args.subnet}\n"
            if args.subnet
            else ""
        ),
        encoding="utf-8",
    )
    probe_source = (ROOT / "tests/fixtures/api_image_probe.py").read_text(
        encoding="utf-8"
    )
    environment = {
        key: value
        for key, value in os.environ.items()
        if key
        not in {
            "API_PORT",
            "WORKERS_NUM",
            "API_REQUESTS_PER_SECOND",
            "CLIENT_REPORTS_PRUNE_INTERVAL_SECONDS",
        }
        and not key.startswith(("OMK_API_", "SERVER_STATUS_", "COMPOSE_"))
    }
    compose = [
        "docker",
        "compose",
        "--project-name",
        project,
        "--env-file",
        str(env_file),
        "-f",
        str(ROOT / "deploy/api/compose.yaml"),
        "-f",
        str(overlay),
    ]
    checks = []
    report = {
        "ok": False,
        "checks": checks,
        "scope": "Disposable API image/Compose, not game readiness",
    }

    def call(args, *, check=True, timeout=60, phase=None, stdin=None):
        result = subprocess.run(
            args,
            cwd=ROOT,
            env=environment,
            input=stdin,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        if check and result.returncode:
            # Never echo supplied environment or arbitrary Docker diagnostics.
            raise DockerFailure(
                phase or f"docker {args[1]}", result.returncode, result.stderr
            )
        return result

    def expect(condition, name):
        if not condition:
            raise AssertionError(name)
        checks.append(name)

    def until(callback):
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            try:
                value = callback()
                if value:
                    return value
            except ValueError, OSError, URLError:
                pass
            time.sleep(0.5)
        raise TimeoutError("API lab startup timeout")

    def container_json(name, mode):
        result = call(
            ["docker", "exec", "-i", name, ".venv/bin/python", "-", mode],
            check=False,
            stdin=probe_source,
        )
        return json.loads(result.stdout) if result.returncode == 0 else None

    def stopped_evidence(name, phase, started):
        state = json.loads(call(["docker", "inspect", name]).stdout)[0]["State"]
        report.setdefault("stops", {})[phase] = {
            "running": state["Running"],
            "exit_code": state["ExitCode"],
            "oom_killed": state["OOMKilled"],
            "stop_seconds": round(time.monotonic() - started, 3),
        }
        # Only this disposable API's fixture logs; never inspect arbitrary services.
        logs = call(["docker", "logs", "--tail", "120", name], check=False)
        (lab / (phase + "-stopped.log")).write_text(
            (logs.stdout + logs.stderr)[-32768:], encoding="utf-8"
        )
        return state

    try:
        context = lab / "context"
        context.mkdir()
        for name in ("Dockerfile.api.dockerignore", "Dockerfile.api", "pyproject.toml", "uv.lock"):
            shutil.copyfile(ROOT / name, context / name)
        for package in ("api", "omk"):
            shutil.copytree(
                ROOT / package,
                context / package,
                ignore=shutil.ignore_patterns("__pycache__"),
            )
        for folder in (context, context / "api/settings"):
            for suffix in ("key", "pem", "db", "json"):
                (folder / f"test-marker.{suffix}").write_text(
                    "fixture marker", encoding="utf-8"
                )
        (context / ".env").write_text("API_PORT=9\n", encoding="utf-8")
        (context / ".omk-admin").mkdir()
        (context / ".omk-admin/fixture.txt").write_text(
            "fixture marker", encoding="utf-8"
        )
        built = call(
            [
                "docker",
                "build",
                "-f",
                str(context / "Dockerfile.api"),
                "-t",
                image,
                str(context),
            ],
            timeout=600,
            check=False,
        )
        (lab / "build.log").write_text(built.stdout + built.stderr, encoding="utf-8")
        expect(built.returncode == 0, "pinned_api_image_built")
        report["image_id"] = call(
            ["docker", "image", "inspect", image, "--format", "{{.Id}}"]
        ).stdout.strip()
        call(
            [
                "docker",
                "run",
                "-d",
                "--name",
                default_container,
                "--network",
                "none",
                "--memory",
                "1024m",
                "--cpus",
                "1",
                image,
            ]
        )
        health = until(lambda: container_json(default_container, "health"))
        expect(
            health["api_host"] == "127.0.0.1" and health["api_port"] == 8000,
            "native_defaults_serve_inside_unpublished_linux_container",
        )
        native = container_json(default_container, "pid1")
        expect(
            native[native.index("--workers") + 1] == "1", "default_worker_count_is_used"
        )
        started_stop = time.monotonic()
        call(["docker", "stop", "--time", "15", default_container])
        stopped = stopped_evidence(default_container, "default", started_stop)
        expect(
            stopped["ExitCode"] == 0 and not stopped["OOMKilled"],
            "default_pid1_handles_clean_stop_without_oom",
        )

        env_file.write_text(
            f"API_PORT={internal_port}\nWORKERS_NUM=2\nAPI_REQUESTS_PER_SECOND=17\n"
            "CLIENT_REPORTS_PRUNE_INTERVAL_SECONDS=120\nOMK_API_CPUS=0.75\n"
            "OMK_API_MEMORY_MIB=512\nOMK_API_LOG_MIB=4\nOMK_API_LOG_FILES=2\n"
            'SERVER_STATUS_TARGETS=\'{"synthetic":{"host":"fixture.invalid","port":25578}}\'\n'
            "SERVER_STATUS_CACHE_SECONDS=37\nSERVER_STATUS_TIMEOUT_SECONDS=3\n"
            f'OMK_API_CONTENT_SOURCE="{content.as_posix()}"\n',
            encoding="utf-8",
        )
        config = json.loads(call([*compose, "config", "--format", "json"]).stdout)[
            "services"
        ]["api"]
        expect(
            config["ports"][0]["host_ip"] == "127.0.0.1"
            and config["ports"][0]["target"] == internal_port
            and config["ports"][0].get("published") is None,
            "compose_port_override_stays_loopback",
        )
        call([*compose, "up", "-d", "--no-build"], phase="compose up")
        host, _, port = (
            call([*compose, "port", "api", str(internal_port)])
            .stdout.strip()
            .rpartition(":")
        )
        expect(
            host == "127.0.0.1" and 0 < int(port) <= 65535,
            "docker_assigned_loopback_port",
        )
        cid = call([*compose, "ps", "-q", "api"]).stdout.strip()
        opener = build_opener(ProxyHandler({}))

        def external_health():
            with opener.open(f"http://127.0.0.1:{port}/health", timeout=2) as response:
                return json.load(response)

        health = until(external_health)
        expect(
            health["api_host"] == "0.0.0.0"
            and health["api_port"] == internal_port
            and health["instances_count"] == 1,
            "compose_override_serves_only_fixture_content",
        )
        state = json.loads(call(["docker", "inspect", cid]).stdout)[0]
        host = state["HostConfig"]
        report["runtime_limits"] = {
            "memory_bytes": host["Memory"],
            "nano_cpus": host["NanoCpus"],
            "docker_logging": host["LogConfig"],
        }
        expect(
            host["Memory"] == 512 * 1024**2 and host["NanoCpus"] == 750000000,
            "compose_cpu_and_memory_limits_applied",
        )
        expect(
            host["Sysctls"].get("net.ipv4.tcp_migrate_req") == "1",
            "multi_worker_socket_migration_is_container_scoped",
        )
        expect(
            host["LogConfig"]
            == {"Type": "local", "Config": {"max-file": "2", "max-size": "4m"}},
            "docker_log_rotation_overrides_applied",
        )
        expect(
            any(
                m["Destination"] == "/data/content" and m["RW"] is False
                for m in state["Mounts"]
            ),
            "fixture_content_mount_is_read_only",
        )
        values = container_json(cid, "settings")
        expect(
            values == [2, 17, 120, 37, 3, 25578],
            "container_reads_worker_rate_retention_and_status_overrides",
        )
        log_result = call(["docker", "logs", cid])
        logs = log_result.stdout + log_result.stderr
        (lab / "server.log").write_text(logs, encoding="utf-8")
        expect(
            "Started worker-1" in logs and "Started worker-2" in logs,
            "two_real_granian_workers_started",
        )
        expect(
            container_json(cid, "private") is True,
            "image_excludes_private_markers_and_gui_test_dependencies",
        )
        for key in ["WORKERS_NUM", "SERVER_STATUS_TARGETS", "OMK_API_CPUS"]:
            sentinel = "fixture-invalid-value-must-not-be-logged"
            invalid = call(
                [
                    "docker",
                    "run",
                    "--rm",
                    "--network",
                    "none",
                    "--memory",
                    "512m",
                    "-e",
                    key + "=" + sentinel,
                    image,
                ],
                check=False,
            )
            expect(
                invalid.returncode == 2
                and sentinel not in invalid.stdout + invalid.stderr
                and "Traceback" not in invalid.stderr,
                "invalid_" + key.lower() + "_fails_without_value_or_traceback",
            )
        started_stop = time.monotonic()
        call([*compose, "stop", "-t", "15"])
        outcome = stopped_evidence(cid, "override", started_stop)
        expect(
            outcome["ExitCode"] == 0 and not outcome["OOMKilled"],
            "override_pid1_handles_clean_stop_without_oom",
        )
        report["ok"] = True
    except (
        OSError,
        ValueError,
        AssertionError,
        RuntimeError,
        TimeoutError,
        subprocess.SubprocessError,
    ) as error:
        report["error_type"] = type(error).__name__
        if isinstance(error, DockerFailure):
            report["docker_failure"] = {
                "phase": error.phase,
                "exit_code": error.exit_code,
                "category": error.category,
            }
        if isinstance(error, AssertionError):
            report["failed_check"] = str(error)
            if str(error).endswith("_pid1_handles_clean_stop_without_oom"):
                phase = "default" if str(error).startswith("default_") else "override"
                # The script creates both containers with fixture-only data and no auth.
                stop_log = lab / (phase + "-stopped.log")
                report["fixture_stop_log_tail"] = stop_log.read_text(encoding="utf-8")[
                    -16384:
                ]
    finally:
        # Only UUID-owned resources; no prune, shared services or real volumes.
        if env_file.exists():
            cleaned = call([*compose, "down"], check=False)
            report["owned_compose_removed"] = cleaned.returncode == 0
        removed = call(["docker", "rm", "-f", default_container], check=False)
        report["owned_default_removed"] = removed.returncode == 0
        report["owned_image_tag_removed"] = (
            call(["docker", "image", "rm", image], check=False).returncode == 0
        )
        report["ok"] = report["ok"] and all(
            report.get(key) is True
            for key in (
                "owned_compose_removed",
                "owned_default_removed",
                "owned_image_tag_removed",
            )
        )
        (lab / "report.json").write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8"
        )
    print(json.dumps({**report, "lab": str(lab.relative_to(ROOT))}))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
