"""Bounded client crash reports: no arbitrary files, chat history or native environment dumps."""

import contextlib
import json
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from omk.diagnostics import _excerpt, _files, event, redact, regular
from omk.drasl import DraslClient
from omk.fs import resolved

MAX_REPORT_BYTES = 96 * 1024
RETENTION_SECONDS = 14 * 86400


def validate_report(value: dict) -> dict:
    allowed = {
        "schema",
        "id",
        "player",
        "occurred_at",
        "pack",
        "pack_version",
        "minecraft",
        "platform",
        "launcher",
        "memory_mb",
        "exit_code",
        "kind",
        "detail",
    }
    if not isinstance(value, dict) or set(value) != allowed or value.get("schema") != 1:
        raise ValueError("Invalid client crash report schema")
    for field, pattern in [
        ("id", r"[a-f0-9]{32}"),
        ("player", r"[a-f0-9]{32}"),
        ("pack", r"[a-z0-9][a-z0-9_-]{0,47}"),
    ]:
        if (
            not isinstance(value[field], str)
            or re.fullmatch(pattern, value[field]) is None
        ):
            raise ValueError("Invalid client crash report identifier")
    for field in ["occurred_at", "pack_version", "minecraft", "platform", "launcher"]:
        if (
            not isinstance(value[field], str)
            or not 1 <= len(value[field]) <= 100
            or any(ord(c) < 32 for c in value[field])
        ):
            raise ValueError("Invalid client crash report metadata")
    if (
        type(value["memory_mb"]) is not int
        or not 1024 <= value["memory_mb"] <= 16384
        or type(value["exit_code"]) is not int
        or not -(2**31) <= value["exit_code"] < 2**32
        or not isinstance(value["kind"], str)
        or value["kind"] not in {"minecraft_crash", "jvm_crash", "abnormal_exit"}
        or not isinstance(value["detail"], str)
        or len(value["detail"]) > 32768
    ):
        raise ValueError("Invalid client crash report content")
    if len(json.dumps(value, ensure_ascii=False).encode()) > MAX_REPORT_BYTES:
        raise ValueError("Client crash report is too large")
    return value


def _queue(root):
    path = root / "userdata/client-incidents"
    if resolved(path) != path.absolute():
        raise OSError("Linked client crash queue")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    return path


def _prune(root, folder):
    files = _files(folder, root, lambda n: bool(re.fullmatch(r"[a-f0-9]{32}\.json", n)))
    used = 0
    for index, path in enumerate(files):
        used += path.stat().st_size
        if (
            index >= 20
            or used > 2 * 1024**2
            or path.stat().st_mtime < time.time() - RETENTION_SECONDS
        ):
            path.unlink()


def _native_summary(text):
    patterns = (
        "A fatal error",
        "SIGSEGV",
        "SIGBUS",
        "EXCEPTION_ACCESS",
        "Out of Memory Error",
        "Problematic frame",
        "JRE version",
        "Java VM",
        "Internal Error",
    )
    return "\n".join(
        line[:500]
        for line in text.splitlines()[:100]
        if any(p in line for p in patterns) or re.match(r"#\s+[CVjv]\s+", line)
    )


def _error_tail(log):
    if not log.is_file():
        return "No Java stack trace was available."
    raw, _ = _excerpt(log, 65536)
    lines = raw.decode("utf-8", errors="replace").splitlines()
    return "\n".join(
        line[:1000]
        for line in lines
        if "[CHAT]" not in line
        and "GuiNewChat" not in line
        and (
            re.match(r"\s*(at |Caused by: |Suppressed: )", line)
            or re.search(
                r"\b(?:[A-Za-z0-9_.]*(?:Exception|Error)|FATAL|OutOfMemory)\b", line
            )
        )
    )[-32768:]


def crash_fingerprints(root, folder):
    paths = _files(
        folder / "crash-reports",
        root,
        lambda n: bool(re.fullmatch(r"crash-[\w.-]+\.txt", n)),
    )
    paths += _files(
        folder, root, lambda n: bool(re.fullmatch(r"hs_err_pid\d+\.log", n))
    )
    return {
        str(path): (path.stat().st_mtime_ns, path.stat().st_size, path.stat().st_ino)
        for path in paths
    }


def capture_incident(
    root,
    folder,
    release,
    session,
    *,
    run_id,
    started_at,
    exit_code,
    memory_mb,
    launcher,
    stdout_current=True,
    baseline=None,
):
    crashes = _files(
        folder / "crash-reports",
        root,
        lambda n: bool(re.fullmatch(r"crash-[\w.-]+\.txt", n)),
    )
    native = _files(
        folder, root, lambda n: bool(re.fullmatch(r"hs_err_pid\d+\.log", n))
    )
    if baseline is None:
        crashes = [p for p in crashes if p.stat().st_mtime >= started_at]
        native = [p for p in native if p.stat().st_mtime >= started_at]
    else:
        current = crash_fingerprints(root, folder)
        crashes = [p for p in crashes if baseline.get(str(p)) != current.get(str(p))]
        native = [p for p in native if baseline.get(str(p)) != current.get(str(p))]
    if exit_code == 0 and not crashes and not native:
        return None
    kind = "abnormal_exit"
    if crashes:
        with crashes[0].open("rb") as file:
            detail = file.read(65536).decode("utf-8", errors="replace")
        detail = detail.split("-- System Details --", 1)[0][:32768]
        kind = "minecraft_crash"
    elif native:
        with native[0].open("rb") as file:
            detail = _native_summary(file.read(32768).decode("utf-8", errors="replace"))
        kind = "jvm_crash"
    else:
        log = root / "userdata/logs" / f"{release.pack_id}-game.log"
        detail = (
            _error_tail(log)
            if stdout_current and regular(log, root)
            else "No Java stack trace was available."
        )
    detail = redact(
        detail,
        (session.access_token, session.client_token),
        (folder, root, Path.home()),
    )
    detail = detail.encode("utf-8")[:32768].decode("utf-8", errors="ignore")
    report = validate_report(
        {
            "schema": 1,
            "id": run_id,
            "player": UUID(session.player_uuid).hex,
            "occurred_at": datetime.now(UTC).isoformat(),
            "pack": release.pack_id,
            "pack_version": release.version,
            "minecraft": release.minecraft,
            "platform": release.platform,
            "launcher": launcher,
            "memory_mb": memory_mb,
            "exit_code": exit_code,
            "kind": kind,
            "detail": detail,
        }
    )
    queue = _queue(root)
    path = queue / (run_id + ".json")
    with path.open("x", encoding="utf-8") as file:
        file.write(json.dumps(report, ensure_ascii=False))
    _prune(root, queue)
    event(
        root, "client_incident_saved", report_id=run_id, pack=release.pack_id, kind=kind
    )
    return path


def submit_pending(root: Path, origin: str | None, session):
    """One request per attempt, idempotent report ID; never renew or save account tokens here."""
    if origin is None:
        return
    try:
        folder = _queue(root)
        _prune(root, folder)
        client = DraslClient(origin, timeout=3)
        files = _files(
            folder, root, lambda n: bool(re.fullmatch(r"[a-f0-9]{32}\.json", n))
        )
        for path in files:
            with path.open("rb") as file:
                raw = file.read(MAX_REPORT_BYTES + 1)
            if len(raw) > MAX_REPORT_BYTES:
                continue
            with contextlib.suppress(ValueError, TypeError):
                report = validate_report(json.loads(raw))
                if report["player"] != UUID(session.player_uuid).hex:
                    continue
                response = client.request(
                    "POST", "/reports/client", report, session.access_token
                )
                if (
                    isinstance(response, dict)
                    and response.get("id") == report["id"]
                    and response.get("ok") is True
                ):
                    path.unlink()
                    event(root, "client_incident_delivered", report_id=report["id"])
                return
    except Exception as error:
        event(
            root, "client_incident_delivery_deferred", error_type=type(error).__name__
        )
