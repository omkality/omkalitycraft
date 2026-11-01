"""Run bounded filesystem faults in a fresh container with no host data mounts."""

import json
import subprocess
import tempfile
from pathlib import Path
from uuid import uuid4

PYTHON_IMAGE = "python:3.14.2-slim@sha256:1a3c6dbfd2173971abba880c3cc2ec4643690901f6ad6742d0827bae6cefc925"
LABEL = "omkality.backup-safety-lab"


def run_backup_safety_lab():
    run_id = uuid4().hex
    name = "omk-backup-safety-" + run_id[:12]
    report = {
        "ok": False,
        "runtime_image": PYTHON_IMAGE,
        "scope": "synthetic-archive-filesystem-faults",
    }
    with tempfile.TemporaryDirectory(prefix="omk-backup-safety-") as temp:
        root = Path(temp)
        package = root / "omk"
        package.mkdir()
        for filename in (
            "__init__.py",
            "backup_archive.py",
            "backup_store.py",
            "backup_safety_probe.py",
        ):
            (package / filename).write_bytes(
                (Path(__file__).parent / filename).read_bytes()
            )
        try:
            result = subprocess.run(
                [
                    "docker",
                    "run",
                    "--pull",
                    "never",
                    "--name",
                    name,
                    "--label",
                    LABEL + "=" + run_id,
                    "--network",
                    "none",
                    "--read-only",
                    "--cap-drop",
                    "ALL",
                    "--security-opt",
                    "no-new-privileges",
                    "--memory",
                    "512m",
                    "--cpus",
                    "1",
                    "--pids-limit",
                    "32",
                    "--mount",
                    f"type=bind,source={root.resolve()},target=/code,readonly",
                    "--tmpfs",
                    "/lab:rw,nosuid,nodev,noexec,size=64m",
                    "--tmpfs",
                    "/small:rw,nosuid,nodev,noexec,size=16m",
                    "--tmpfs",
                    "/scratch:rw,nosuid,nodev,noexec,size=128m",
                    "--workdir",
                    "/code",
                    PYTHON_IMAGE,
                    "python",
                    "-B",
                    "-m",
                    "omk.backup_safety_probe",
                ],
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
            if result.returncode:
                report["error"] = "Изолированный backup-тест завершился с ошибкой."
                report["probe_output"] = (result.stderr or result.stdout)[-4000:]
            else:
                report["probe"] = json.loads(result.stdout)
                report["ok"] = report["probe"]["ok"]
        except OSError, subprocess.SubprocessError, ValueError, KeyError:
            report["error"] = (
                "Не удалось выполнить изолированный backup-тест; проверьте Docker и закреплённый образ."
            )
        finally:
            report["container_removed"] = _cleanup(name, run_id)
    report["ok"] = report["ok"] and report["container_removed"]
    return report


def _cleanup(name, run_id):
    try:
        result = subprocess.run(
            ["docker", "inspect", name],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if result.returncode:
            return (
                False  # Do not mistake a daemon/network error for successful cleanup.
            )
        data = json.loads(result.stdout)[0]
        if data.get("Config", {}).get("Labels", {}).get(LABEL) != run_id:
            return False
        removed = subprocess.run(
            ["docker", "rm", "--force", name],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        return removed.returncode == 0
    except OSError, subprocess.SubprocessError, ValueError, IndexError:
        return False
