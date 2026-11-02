"""Fixture-only Linux shutdown reproduction with bounded Python stack evidence."""

import argparse
import json
import subprocess
import time
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
LABEL = "omk.api-stop-probe"
SIGNAL_PROCESSES = """import os,signal
for item in os.listdir('/proc'):
    if not item.isdigit() or int(item) == os.getpid(): continue
    try:
        if 'python' in os.readlink('/proc/' + item + '/exe'):
            os.kill(int(item), signal.SIGUSR1)
    except OSError:
        pass
"""


def docker(*args, check=True, timeout=60):
    result = subprocess.run(
        ["docker", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=ROOT,
        check=False,
    )
    if check and result.returncode:
        raise RuntimeError("Owned shutdown probe command failed")
    return result


def checked_state(data, run):
    if (data.get("Config", {}).get("Labels") or {}).get(LABEL) != run:
        raise ValueError("Refusing access to an unowned container")
    return data["State"]


def state(name, run):
    result = docker("inspect", name, check=False)
    return (
        checked_state(json.loads(result.stdout)[0], run)
        if result.returncode == 0
        else None
    )


def prepare(lab, image, run):
    probe, content = lab / "probe", lab / "content"
    probe.mkdir()
    (content / "instances/fixture").mkdir(parents=True)
    (probe / "sitecustomize.py").write_text(
        "import faulthandler,signal\n"
        "faulthandler.register(signal.SIGUSR1,all_threads=True)\n",
        encoding="utf-8",
    )
    if docker("info", "--format", "{{.OSType}}").stdout.strip() != "linux":
        raise RuntimeError("The shutdown probe requires Linux containers")
    if docker("image", "inspect", image, check=False).returncode == 0:
        raise ValueError("A new probe image tag is required")
    built = docker(
        "build",
        "--label",
        LABEL + "=" + run,
        "-f",
        "Dockerfile.api",
        "-t",
        image,
        ".",
        check=False,
        timeout=600,
    )
    (lab / "build.log").write_text(built.stdout + built.stderr, encoding="utf-8")
    if built.returncode:
        raise RuntimeError("Probe image build failed")


def start(name, run, image, lab):
    docker(
        "run",
        "-d",
        "--name",
        name,
        "--label",
        LABEL + "=" + run,
        "--network",
        "none",
        "--memory",
        "512m",
        "--cpus",
        "0.75",
        "--mount",
        f"type=bind,source={lab / 'probe'},target=/probe,readonly",
        "--mount",
        f"type=bind,source={lab / 'content'},target=/data/content,readonly",
        "-e",
        "PYTHONPATH=/probe",
        "-e",
        "WORKERS_NUM=2",
        "-e",
        "API_HOST=0.0.0.0",
        image,
    )
    deadline = time.monotonic() + 40
    while time.monotonic() < deadline:
        ready = docker(
            "exec",
            name,
            ".venv/bin/python",
            "-c",
            "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=1).read()",
            check=False,
        )
        if ready.returncode == 0:
            return
        time.sleep(0.25)
    raise TimeoutError("Fixture API readiness timeout")


def stop_with_stacks(name, run):
    checked = state(name, run)
    if checked is None or not checked["Running"]:
        raise RuntimeError("Probe container is not running")
    started = time.monotonic()
    stopping = subprocess.Popen(
        ["docker", "stop", "--time", "15", name],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    requested = False
    try:
        # Give the ordinary clean stop a chance; dump stacks before Docker's kill.
        try:
            stopping.communicate(timeout=1)
        except subprocess.TimeoutExpired:
            current = state(name, run)
            if current is not None and current["Running"]:
                docker(
                    "exec",
                    name,
                    ".venv/bin/python",
                    "-c",
                    SIGNAL_PROCESSES,
                    check=False,
                    timeout=8,
                )
                requested = True
            stopping.communicate(timeout=22)
    finally:
        if stopping.poll() is None:
            stopping.kill()  # Only the host Docker CLI; container cleanup below still checks ownership.
            stopping.communicate(timeout=5)
    outcome = state(name, run)
    if outcome is None:
        raise RuntimeError("Probe container disappeared")
    return {
        "exit_code": outcome["ExitCode"],
        "oom_killed": outcome["OOMKilled"],
        "seconds": round(time.monotonic() - started, 3),
        "stacks_requested": requested,
    }


def exercise_cycle(name, run, image, lab, cycle, names):
    start(name, run, image, lab)
    # Match the startup CPU activity preceding the original smoke stop.
    for key in ("WORKERS_NUM", "SERVER_STATUS_TARGETS", "OMK_API_CPUS"):
        invalid_name = name + "-invalid-" + key.lower()
        names.append(invalid_name)
        result = docker(
            "run",
            "--name",
            invalid_name,
            "--rm",
            "--network",
            "none",
            "--memory",
            "512m",
            "-e",
            key + "=fixture-invalid",
            image,
            check=False,
        )
        if result.returncode != 2:
            raise RuntimeError("Invalid-settings fixture behaved unexpectedly")
        names.remove(invalid_name)
    result = {"cycle": cycle, **stop_with_stacks(name, run)}
    logs = docker("logs", "--tail", "500", name)
    tail = (logs.stdout + logs.stderr)[-131072:]
    (lab / f"cycle-{cycle}.log").write_text(tail, encoding="utf-8")
    if result["exit_code"] != 0 or result["oom_killed"] or result["stacks_requested"]:
        result["fixture_log_tail"] = tail[-16384:]
    return result


def cleanup(names, run, image):
    complete = True
    for name in names:
        try:
            current = state(name, run)
            if current is None:
                continue
            if current["Running"]:
                docker("stop", "--time", "15", name)
            docker("rm", name)
        except OSError, ValueError, RuntimeError, subprocess.SubprocessError:
            complete = False
    try:
        inspected = docker("image", "inspect", image, check=False)
        if inspected.returncode:
            return complete
        data = json.loads(inspected.stdout)[0]
        if (data.get("Config", {}).get("Labels") or {}).get(LABEL) != run:
            return False
        removed = docker("image", "rm", image, check=False)
        return complete and removed.returncode == 0
    except OSError, ValueError, RuntimeError, subprocess.SubprocessError:
        return False


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cycles", type=int, choices=range(1, 25), default=12)
    args = parser.parse_args(argv)
    run = uuid4().hex[:12]
    lab = ROOT / ".local" / ("api-stop-probe-" + run)
    lab.mkdir(parents=True)
    image, names = "omk-api-stop-probe-" + run + ":lab", []
    report = {
        "cycles": [],
        "scope": "Instrumented fixture-only API shutdown; no auth/game data",
    }
    try:
        prepare(lab, image, run)
        report["image_id"] = json.loads(docker("image", "inspect", image).stdout)[0][
            "Id"
        ]
        for cycle in range(1, args.cycles + 1):
            name = "omk-api-stop-probe-" + run + "-" + str(cycle)
            names.append(name)
            result = exercise_cycle(name, run, image, lab, cycle, names)
            report["cycles"].append(result)
            if result["exit_code"] != 0 or result["oom_killed"]:
                break
            # Verify the label immediately before deleting this completed fixture.
            state(name, run)
            docker("rm", name)
            names.remove(name)
    except (
        OSError,
        ValueError,
        RuntimeError,
        TimeoutError,
        subprocess.SubprocessError,
    ) as error:
        report["error_type"] = type(error).__name__
    finally:
        report["cleanup"] = cleanup(names, run, image)
        report["ok"] = (
            len(report["cycles"]) == args.cycles
            and "error_type" not in report
            and report["cleanup"]
            and all(
                c["exit_code"] == 0 and not c["oom_killed"] for c in report["cycles"]
            )
        )
        (lab / "report.json").write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8"
        )
    print(json.dumps({**report, "lab": str(lab.relative_to(ROOT))}))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
