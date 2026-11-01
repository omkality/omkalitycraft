"""Bounded startup observations on a new Forge lab, optionally an owned evidence clone."""

import json
import re
import time
from pathlib import Path
from uuid import uuid4

from omk.dj2_lab import _accounts, _copy_server, _wait_server
from omk.dj2_linux_lab import (
    JAVA_IMAGE,
    LABEL,
    LinuxServer,
    container_outcome,
    docker,
    inspect_owned,
)
from omk.operator_lab import _cleanup
from omk.profiles import PROJECT_ROOT
from omk.startup_trace_fixture import build_startup_agent

HOOKS = ("launchclassloader", "mixin-legacy", "mixin-service", "reentry-lock")


def inspect_trace(path):
    if path.stat().st_size > 2 * 1024**2:
        raise ValueError("Unexpectedly large startup trace")
    text = path.read_text(encoding="utf-8")
    mode = (
        "console"
        if "trace-mode=console" in text
        else "exclusions" if "trace-mode=exclusions" in text else "full"
    )
    hooks = {"console": ("console",), "exclusions": ("mixin-service",), "full": HOOKS}[
        mode
    ]
    heap = re.search(
        r"^HEAP ([0-9]{1,20}) ([0-9]{1,20}) ([0-9]{1,20})$", text, re.MULTILINE
    )
    return {
        "hooks_armed": all(hook + "-hook-armed" in text for hook in hooks)
        and (mode != "console" or "console-game-log-observed" in text),
        "console_game_output_seen": "console-game-log-observed" in text,
        "heap_at_exclusion": (
            dict(
                zip(
                    ("free_bytes", "committed_bytes", "max_bytes"),
                    map(int, heap.groups()),
                    strict=True,
                )
            )
            if heap
            else None
        ),
        "mode": mode,
        "deobfuscator_excluded": "DEOBF-EXCLUDED" in text,
        "deobfuscator_reentry": "DEOBF-REENTRY" in text,
        "unmapped_metadata_holder": any(
            " IN " in line
            and "ItemBlockTransformer" in line
            and "fields=[a:Laow;]" in line
            for line in text.splitlines()
        ),
        "holder_failure_captured": any(
            " ERROR " in line
            and "ItemBlockTransformer" in line
            and "no holder field declared" in line
            for line in text.splitlines()
        ),
        "instrumentation_error": "instrumentation-failed" in text
        or "capture-failed" in text,
    }


def evidence_volume(run_id):
    if not re.fullmatch(r"[a-f0-9]{10}", run_id):
        raise ValueError("Expected an owned Linux lab run ID")
    volume = "omk-dj2-linux-" + run_id + "-data"
    if not inspect_owned("volume", volume, run_id):
        raise ValueError("Missing owned evidence volume")
    users = docker("ps", "-a", "--filter", "volume=" + volume, "--format", "{{.Names}}")
    for name in users.stdout.splitlines():
        data = inspect_owned("container", name, run_id)
        if not data or data["State"]["Running"]:
            raise ValueError("Evidence volume must not be in use by a running server")
    return volume


class TraceServer(LinuxServer):
    def new_trace(self, number):
        self.trace = self.lab / ("trace-" + str(number))
        self.trace.mkdir()
        (self.trace / "lab-trace-owner").write_text(self.run_id, encoding="utf-8")

    def command(self, *, snapshot_dir=None):
        if (
            not self.lab.name.startswith("startup-trace-lab-")
            or self.trace.is_symlink()
            or self.trace.parent.resolve() != self.lab.resolve()
        ):
            raise ValueError("Expected an isolated startup trace folder")
        command = super().command(snapshot_dir=snapshot_dir)
        index = command.index(JAVA_IMAGE)
        command[index:index] = [
            "--mount",
            f"type=bind,source={self.trace.resolve()},target=/trace",
        ]
        index = command.index("java") + 1
        command.insert(index, "-javaagent:/srv/.omk/startup-trace-agent.jar=/trace")
        if self.trace_mode == "exclusions":
            command.insert(index, "-Domkality.lab.traceMode=exclusions")
        return command


def add_startup_trace_lab(parser):
    for name in ("server-source", "agent", "core", "mods-json", "java", "compiler"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--boots", type=int, choices=range(1, 13), default=3)
    parser.add_argument(
        "--trace-mode", choices=("console", "full", "exclusions"), default="console"
    )
    parser.add_argument(
        "--evidence-run",
        help="Optional stopped, owned Linux lab run ID; mounted read-only",
    )


def _clone_evidence(server, volume):
    docker(
        "run",
        "--rm",
        "--pull",
        "never",
        "--network",
        "none",
        "--read-only",
        "--label",
        LABEL + "=" + server.run_id,
        "--mount",
        f"type=volume,source={volume},target=/evidence,readonly",
        "--mount",
        f"type=volume,source={server.volume},target=/srv",
        "--entrypoint",
        "/bin/sh",
        JAVA_IMAGE,
        "-c",
        "set -eu; cp -a /evidence/. /srv/",
        timeout=180,
    )


def _boot(server, number, state):
    server.new_trace(number)
    started = time.monotonic()
    process = server.start()
    failure = None
    try:
        _wait_server(process, server.log, lambda phase: state(f"boot-{number}-{phase}"))
        process.stdin.write(b"stop\n")
        process.stdin.flush()
        process.wait(timeout=90)
        server.collector.close()
        if process.returncode != 0:
            raise RuntimeError("Owned boot did not stop cleanly")
    except Exception as error:
        failure = type(error).__name__
    trace = inspect_trace(server.trace / "trace.txt")
    log = server.log.read_text(encoding="utf-8", errors="replace")
    result = {
        "number": number,
        "seconds": round(time.monotonic() - started, 1),
        "clean_exit": failure is None,
        "trace": trace,
        "java_oom_logged": "java.lang.OutOfMemoryError" in log,
        "native_allocation_failure_logged": "Native memory allocation" in log
        or "Cannot allocate memory" in log,
    }
    data = inspect_owned("container", server.name, server.run_id)
    if data:
        result["container"] = container_outcome(data)
    if failure is not None:
        result["error_type"] = failure
        result["server_no_holder_failure"] = "no holder field declared" in log
    if not trace["hooks_armed"] or trace["instrumentation_error"]:
        raise RuntimeError("Startup instrumentation was incomplete")
    (server.lab / f"boot-{number}.log").write_bytes(server.log.read_bytes())
    return result


def run_startup_trace_lab(args):
    if type(args.boots) is not int or not 1 <= args.boots <= 12:
        raise ValueError("Expected 1..12 lab boots")
    if args.trace_mode not in {"full", "exclusions", "console"}:
        raise ValueError("Unknown startup trace mode")
    volume = evidence_volume(args.evidence_run) if args.evidence_run else None
    lab = PROJECT_ROOT / ".local" / ("startup-trace-lab-" + uuid4().hex[:10])
    lab.mkdir()
    project = "omk-startup-trace-" + uuid4().hex[:10]
    compose = [
        "docker",
        "compose",
        "--project-name",
        project,
        "-f",
        str(PROJECT_ROOT / "deploy/auth-lab/compose.yaml"),
    ]
    server = TraceServer(lab, uuid4().hex[:10], project + "_default")
    server.trace_mode = args.trace_mode
    report = {
        "ok": False,
        "lab": lab.relative_to(PROJECT_ROOT).as_posix(),
        "boots": [],
        "root_cause_fixed": False,
        "trace_only": True,
        "runtime_image": JAVA_IMAGE,
    }

    def state(phase):
        (lab / "progress.json").write_text(
            json.dumps({"phase": phase, "report": report}, indent=2), encoding="utf-8"
        )

    try:
        jar, report["fixture"] = build_startup_agent(
            args.java, args.compiler, args.server_source, lab, mode=args.trace_mode
        )
        state("preparing-owned-runtime")
        client, _, _, _ = _accounts(compose, lab)
        dest, _ = _copy_server(args, lab)
        server.prepare(dest, args, client)
        if volume:
            # Recheck immediately before the read-only copy; never stop or alter
            # the evidence server in order to obtain this clone.
            _clone_evidence(server, evidence_volume(args.evidence_run))
            report["source_volume_cloned_read_only"] = volume
        server.helper(
            "set -eu; cp /seed/startup-trace-agent.jar /srv/.omk/startup-trace-agent.jar",
            source=jar.parent,
        )
        for number in range(1, args.boots + 1):
            result = _boot(server, number, state)
            report["boots"].append(result)
            state("boot-complete")
            if not result["clean_exit"]:
                report["same_failure_reproduced"] = (
                    result.get("server_no_holder_failure", False)
                    and result["trace"]["deobfuscator_excluded"]
                )
                break
            if number < args.boots:
                if not inspect_owned("container", server.name, server.run_id):
                    raise ValueError("Missing owned boot container")
                docker("rm", server.name)
                server.process = server.collector = None
        report["all_boots_clean"] = len(report["boots"]) == args.boots and all(
            b["clean_exit"] for b in report["boots"]
        )
        report["ok"] = report["all_boots_clean"] or report.get(
            "same_failure_reproduced", False
        )
    except Exception as error:
        report["error_type"] = type(error).__name__
    finally:
        server.close(report)
        report["auth_removed"] = _cleanup(None, None, compose)
        report["ok"] = report["ok"] and report["auth_removed"]
        state("complete")
        (lab / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
