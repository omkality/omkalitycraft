"""Exercise the actual API image and Compose with fresh, loopback-only lab data."""

import json
import os
import socket
import subprocess
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def main():  # noqa: PLR0915 -- ordered real-container scenario with one owned cleanup path
    run = uuid4().hex[:12]
    lab = ROOT / ".local" / ("api-runtime-" + run)
    lab.mkdir(parents=True)
    content = lab / "content"
    (content / "instances" / "fixture").mkdir(parents=True)
    project = "omk-api-" + run
    image = project + ":lab"
    default_container = project + "-default"
    env_file, overlay = lab / "compose.env", lab / "image.json"
    overlay.write_text(json.dumps({"services": {"api": {"image": image}}}))
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
        and not key.startswith("OMK_API_")
    }
    compose = [
        "docker",
        "compose",
        "--project-name",
        project,
        "--env-file",
        str(env_file),
        "-f",
        str(ROOT / "docker-compose.yml"),
        "-f",
        str(overlay),
    ]
    checks = []
    report = {
        "ok": False,
        "checks": checks,
        "scope": "Disposable API image/Compose, not game readiness",
    }

    def call(args, *, check=True, timeout=60):
        result = subprocess.run(
            args,
            cwd=ROOT,
            env=environment,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        if check and result.returncode:
            # Never echo supplied environment or arbitrary Docker diagnostics.
            raise RuntimeError("API container lab command failed")
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

    def container_json(name, expression):
        result = call(
            ["docker", "exec", name, ".venv/bin/python", "-c", expression], check=False
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
        built = call(
            ["docker", "build", "-f", "Dockerfile.api", "-t", image, "."],
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
        health = until(
            lambda: container_json(
                default_container,
                "import json,urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=2).read().decode())",
            )
        )
        expect(
            health["api_host"] == "127.0.0.1" and health["api_port"] == 8000,
            "native_defaults_serve_inside_unpublished_linux_container",
        )
        native = container_json(
            default_container,
            "import json,pathlib; "
            "print(json.dumps(pathlib.Path('/proc/1/cmdline').read_bytes().decode().split(chr(0))))",
        )
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

        # Ask the OS for a free loopback port, then release it for Compose.
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        env_file.write_text(
            f"API_PORT={port}\nWORKERS_NUM=2\nAPI_REQUESTS_PER_SECOND=17\n"
            "CLIENT_REPORTS_PRUNE_INTERVAL_SECONDS=120\nOMK_API_CPUS=0.75\n"
            "OMK_API_MEMORY_MIB=512\nOMK_API_LOG_MIB=4\nOMK_API_LOG_FILES=2\n"
            f"OMK_API_CONTENT_SOURCE={content.as_posix()}\n",
            encoding="utf-8",
        )
        config = json.loads(call([*compose, "config", "--format", "json"]).stdout)[
            "services"
        ]["api"]
        expect(
            config["ports"][0]["host_ip"] == "127.0.0.1"
            and config["ports"][0]["target"] == port
            and int(config["ports"][0]["published"]) == port,
            "compose_port_override_stays_loopback",
        )
        call([*compose, "up", "-d", "--no-build"])
        cid = call([*compose, "ps", "-q", "api"]).stdout.strip()
        opener = build_opener(ProxyHandler({}))

        def external_health():
            with opener.open(f"http://127.0.0.1:{port}/health", timeout=2) as response:
                return json.load(response)

        health = until(external_health)
        expect(
            health["api_host"] == "0.0.0.0"
            and health["api_port"] == port
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
        values = container_json(
            cid,
            "import json; from api.settings.config import settings as s; "
            "print(json.dumps([s.workers_num,s.api_requests_per_second,s.client_reports_prune_interval_seconds]))",
        )
        expect(
            values == [2, 17, 120],
            "container_reads_worker_rate_and_retention_overrides",
        )
        log_result = call(["docker", "logs", cid])
        logs = log_result.stdout + log_result.stderr
        (lab / "server.log").write_text(logs, encoding="utf-8")
        expect(
            "Started worker-1" in logs and "Started worker-2" in logs,
            "two_real_granian_workers_started",
        )
        absent = container_json(
            cid,
            "import json,pathlib; print(json.dumps([not pathlib.Path(p).exists() for p in "
            "['/backend/.env','/backend/.omk-admin','/backend/.local','/backend/.git']]))",
        )
        expect(absent == [True] * 4, "private_host_paths_are_not_in_image")
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
