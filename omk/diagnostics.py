"""Bounded local diagnostics. No network uploads, credentials or arbitrary file walks."""

import codecs
import contextlib
import json
import os
import platform
import re
import shutil
import threading
import traceback
import zipfile
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path
from uuid import uuid4

import psutil

from omk.fs import resolved

MIB = 1024 * 1024
LINE_LIMIT = 32768
_EVENT_LOCK = threading.Lock()
_CREDENTIAL = re.compile(
    r"(?i)([\"']?(?:access[_-]?token|client[_-]?token|api[_-]?token|password|"
    r"passwd|authorization|refresh[_-]?token|invite|secret)[\"']?\s*[:=]\s*)"
    r"(?:\"(?:\\.|[^\"\\\r\n])*\"|'(?:\\.|[^'\\\r\n])*'|[^\s,;}&]+)"
)
_ARGUMENT = re.compile(
    r"(?i)(--(?:accessToken|clientToken|password)\s+)(?:\"[^\"\r\n]*\"|\S+)"
)


def redact(text: str, secrets=(), paths=()) -> str:
    text = re.sub(r"§[0-9A-FK-ORa-fk-or]", "", text)
    for secret in sorted((s for s in secrets if s), key=len, reverse=True):
        text = text.replace(secret, "[redacted]")
    text = re.sub(r"(?i)\b(?:Bearer|Basic)\s+[A-Za-z0-9._~+/=-]+", "[redacted]", text)
    text = _ARGUMENT.sub(r"\1[redacted]", text)
    text = _CREDENTIAL.sub(r"\1[redacted]", text)
    text = re.sub(r"(?i)(Session ID is\s+)[^\r\n]+", r"\1[redacted]", text)
    text = re.sub(
        r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", "[redacted]", text
    )
    for path in sorted((str(p) for p in paths if p), key=len, reverse=True):
        text = text.replace(path, "[local-path]").replace(
            path.replace("\\", "/"), "[local-path]"
        )
    # Neutralize terminal escape sequences and control characters in exported text.
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)


def regular(path: Path, root: Path) -> bool:
    """Do not follow any symlink/junction, including parents, even inside root."""
    try:
        relative = path.relative_to(root)
        current = root
        for part in ("", *relative.parts):
            current = current / part
            if current.is_symlink() or current.is_junction():
                return False
        return path.is_file() and resolved(path).is_relative_to(resolved(root))
    except OSError, ValueError:
        return False


class BoundedLog:
    """Byte-bounded rotating UTF-8 file, without a queue or an in-memory history."""

    def __init__(self, path: Path, *, limit=8 * MIB, copies=3):
        if limit < 256 or not 1 <= copies <= 10:
            raise ValueError("Invalid log budget")
        self.path, self.limit, self.copies = path, limit, copies
        self.lock = threading.Lock()
        if resolved(path.parent) != path.parent.absolute():
            raise OSError("Linked diagnostic directory")
        path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, text: str):
        data = text.encode("utf-8", errors="replace")
        if len(data) > self.limit:
            data = b"[oversized record omitted]\n"
        with self.lock:
            paths = [
                self.path,
                *(Path(str(self.path) + f".{i}") for i in range(1, self.copies)),
            ]
            for path in paths:
                # A linked log file must never cause an external write or rename.
                if path.is_symlink() or path.is_junction():
                    raise OSError("Linked diagnostic path")
            if resolved(self.path.parent) != self.path.parent.absolute():
                raise OSError("Linked diagnostic directory")
            for path in paths:
                if path.exists() and path.stat().st_size > self.limit:
                    with path.open("rb") as file:
                        file.seek(-self.limit, 2)
                        tail = file.read(self.limit).partition(b"\n")[2]
                    path.write_bytes(tail)
            size = self.path.stat().st_size if self.path.exists() else 0
            if size + len(data) > self.limit:
                paths[-1].unlink(missing_ok=True)
                for old, new in reversed(list(pairwise(paths))):
                    if old.exists():
                        old.replace(new)
            with self.path.open("ab") as output:
                output.write(data)


def collect_output(stream, log: BoundedLog, secrets=(), *, on_error=None):
    """Drain even after disk failure. Omit overlong lines rather than leaking fragments."""
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    pending = ""
    dropping = False
    writable = True

    def emit(text):
        nonlocal writable
        if writable:
            try:
                log.write(redact(text, secrets))
            except OSError:
                writable = False
                if on_error is not None:
                    on_error()

    read = getattr(stream, "read1", stream.read)
    try:
        while True:
            raw = read(8192)
            text = decoder.decode(raw, final=not raw)
            parts = text.splitlines(keepends=True)
            for part in parts:
                end = part.endswith(("\n", "\r"))
                if not dropping:
                    if len(pending) + len(part) > LINE_LIMIT:
                        pending = ""
                        dropping = True
                        emit("[overlong output line omitted]\n")
                    else:
                        pending += part
                if end:
                    if not dropping:
                        emit(pending)
                    pending, dropping = "", False
            if not raw:
                if pending and not dropping:
                    emit(pending + "\n")
                break
    finally:
        stream.close()


class PipeLog:
    """One collector thread per owned process, with bounded memory and close/join."""

    def __init__(self, stream, log: BoundedLog):
        self.failed = threading.Event()
        self.thread = threading.Thread(
            target=self._run, args=(stream, log), daemon=True
        )
        self.thread.start()

    def _run(self, stream, log):
        try:
            collect_output(stream, log, on_error=self.failed.set)
        except OSError:
            self.failed.set()

    def close(self):
        self.thread.join(timeout=5)
        if self.thread.is_alive() or self.failed.is_set():
            raise OSError("Process log collector failed")


def event(root: Path, name: str, **fields):
    """Callers pass selected non-secret metadata, never request bodies or arguments."""
    record = {"time": datetime.now(UTC).isoformat(), "event": name, **fields}
    with _EVENT_LOCK, contextlib.suppress(OSError):
        BoundedLog(root / "userdata/logs/launcher.jsonl", limit=MIB).write(
            json.dumps(record, ensure_ascii=False) + "\n"
        )


def environment_snapshot(root: Path):
    memory = psutil.virtual_memory()
    with contextlib.suppress(OSError):
        return {
            "ram_total_mb": memory.total // MIB,
            "ram_available_mb": memory.available // MIB,
            "disk_free_mb": shutil.disk_usage(root).free // MIB,
            "cpu_count": os.cpu_count(),
        }
    return {
        "ram_total_mb": memory.total // MIB,
        "ram_available_mb": memory.available // MIB,
    }


def failure(root: Path, context: str, error: Exception):
    # Frame locations without source lines, exception messages, local values or bodies.
    frames = [
        {"file": Path(f.filename).name, "function": f.name, "line": f.lineno}
        for f in traceback.extract_tb(error.__traceback__)
    ]
    event(
        root,
        "operation_failed",
        context=context,
        error_type=type(error).__name__,
        errno=error.errno if isinstance(error, OSError) else None,
        frames=frames,
    )


def _files(folder: Path, root: Path, predicate):
    if resolved(folder) != folder.absolute():
        return []
    if folder.is_symlink() or folder.is_junction() or not folder.is_dir():
        return []
    result = []
    with os.scandir(folder) as entries:
        for index, entry in enumerate(entries):
            if index >= 1000:
                break
            path = Path(entry.path)
            if predicate(path.name) and regular(path, root):
                result.append(path)
    return sorted(result, key=lambda p: p.stat().st_mtime, reverse=True)


def prune_reports(root: Path, folder: Path, *, count=10, budget=32 * MIB):
    """Only old crash reports; caller must have stopped the owned game first.

    Preserve the newest report even if a third-party writer exceeds the budget.
    """
    used = 0
    reports = _files(
        folder, root, lambda n: bool(re.fullmatch(r"crash-[\w.-]+\.txt", n))
    )
    for index, path in enumerate(reports):
        size = path.stat().st_size
        if index and (index >= count or used + size > budget):
            path.unlink()
        else:
            used += size


def prune_native_archives(root: Path, folder: Path):
    """Only inactive native archives, after stopping the game, never third-party logs."""
    archives = _files(
        folder,
        root,
        lambda n: bool(
            re.fullmatch(r"(?:\d{4}-\d{2}-\d{2}-\d+|latest-\d+|debug-\d+)\.log\.gz", n)
        ),
    )
    used = 0
    for index, path in enumerate(archives):
        used += path.stat().st_size
        if index >= 12 or used > 32 * MIB:
            path.unlink()


def _session_secrets(root):
    secrets = []
    # Current session is read only for redaction, never added to the archive.
    session = root / "userdata/session.json"
    if regular(session, root) and session.stat().st_size <= 32768:
        with contextlib.suppress(OSError, ValueError, TypeError):
            value = json.loads(session.read_text(encoding="utf-8"))
            secrets = (
                [value.get(k, "") for k in ("access_token", "client_token")]
                if isinstance(value, dict)
                else []
            )
            secrets = [s for s in secrets if isinstance(s, str)]
    return secrets


def _candidates(root, source, pack):
    candidates = []
    for folder, boundary, prefix, predicate in [
        (
            root / "userdata/logs",
            root,
            "launcher",
            lambda n: bool(
                re.fullmatch(
                    r"(?:launcher\.jsonl|"
                    + re.escape(pack)
                    + r"-game\.log)(?:\.[12])?",
                    n,
                )
            ),
        ),
        (
            source / "logs",
            source,
            "game",
            lambda n: n in {"latest.log", "debug.log"},
        ),
        (
            source / "crash-reports",
            source,
            "crashes",
            lambda n: bool(re.fullmatch(r"crash-[\w.-]+\.txt", n)),
        ),
        (source, source, "jvm", lambda n: bool(re.fullmatch(r"hs_err_pid\d+\.log", n))),
    ]:
        candidates.extend(
            (p, boundary, prefix) for p in _files(folder, boundary, predicate)[:3]
        )
    return sorted(
        candidates,
        key=lambda item: {"crashes": 0, "jvm": 1, "launcher": 2, "game": 3}[item[2]],
    )


def _excerpt(path, limit, head=False):
    with path.open("rb") as file:
        size = file.seek(0, 2)
        if size <= limit:
            file.seek(0)
            return file.read(limit), False
        leading = b""
        if head:
            file.seek(0)
            leading = (
                file.read(limit // 2).rpartition(b"\n")[0] + b"\n[... truncated ...]\n"
            )
        file.seek(max(0, size - (limit - len(leading))))
        trailing = file.read(limit - len(leading)).partition(b"\n")[2]
        return leading + trailing, True


def export_bundle(root: Path, pack: str, *, server_root: Path | None = None) -> dict:
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,47}", pack):
        raise ValueError("Invalid profile id")
    root = resolved(root)
    source = resolved(server_root) if server_root else root / "instances" / pack
    paths = [root, Path.home(), source]
    secrets = _session_secrets(root)
    candidates = _candidates(root, source, pack)
    folder = root / "userdata/diagnostics"
    if resolved(folder) != folder:
        raise OSError("Linked diagnostics directory")
    folder.mkdir(parents=True, exist_ok=True)
    name = "diag-" + uuid4().hex + ".zip"
    output = folder / name
    temporary = folder / (name + ".tmp")
    metadata = {
        "schema": 1,
        "created": datetime.now(UTC).isoformat(),
        "pack": pack,
        "system": platform.system(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "resources": environment_snapshot(root),
        "server": server_root is not None,
        "files": [],
        "notice": "Local redacted diagnostic tails; review before sharing. No automatic upload.",
    }
    remaining = 16 * MIB
    try:
        with zipfile.ZipFile(
            temporary, "x", compression=zipfile.ZIP_DEFLATED
        ) as archive:
            for path, boundary, prefix in candidates:
                if remaining <= 0 or not regular(path, boundary):
                    continue
                limit = min(2 * MIB, remaining)
                raw, truncated = _excerpt(
                    path, limit, head=prefix in {"crashes", "jvm"}
                )
                clean = redact(
                    raw.decode("utf-8", errors="replace"), secrets, paths
                ).encode()
                clean = clean[:remaining].decode("utf-8", errors="ignore").encode()
                target = prefix + "/" + path.name
                archive.writestr(target, clean)
                remaining -= len(clean)
                metadata["files"].append(
                    {"path": target, "truncated": truncated, "bytes": len(clean)}
                )
            archive.writestr(
                "diagnostic.json", json.dumps(metadata, ensure_ascii=False, indent=2)
            )
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    used = 0
    previous = _files(
        folder, root, lambda n: bool(re.fullmatch(r"diag-[a-f0-9]{32}\.zip", n))
    )
    for index, path in enumerate(previous):
        used += path.stat().st_size
        if index >= 5 or used > 64 * MIB:
            path.unlink()
    return {
        "ok": True,
        "archive": str(output),
        "files": len(metadata["files"]),
        "uploaded": False,
    }
