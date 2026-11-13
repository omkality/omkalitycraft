"""Operator-only diagnostic export. Excluded from the player distribution."""

import contextlib
import json
import os
import platform
import re
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from omk.diagnostics import MIB, _excerpt, _files, environment_snapshot, redact, regular
from omk.fs import resolved


@dataclass(frozen=True)
class ExportLimits:
    file_bytes: int
    bundle_bytes: int
    keep_files: int
    storage_bytes: int


def export_limits(environment=None) -> ExportLimits:
    env = os.environ if environment is None else environment
    values = {}
    for key, default, low, high in (
        ("FILE_MIB", 2, 1, 8),
        ("BUNDLE_MIB", 16, 1, 64),
        ("KEEP_FILES", 5, 1, 20),
        ("STORAGE_MIB", 64, 2, 512),
    ):
        name = "OMK_DIAGNOSTIC_" + key
        raw = env.get(name, str(default))
        if (
            not isinstance(raw, str)
            or not raw.isascii()
            or not raw.isdecimal()
            or len(raw) > 3
            or not low <= int(raw) <= high
        ):
            raise ValueError("Invalid " + name)
        values[key] = int(raw)
    file, bundle, storage = (
        values[key] * MIB for key in ("FILE_MIB", "BUNDLE_MIB", "STORAGE_MIB")
    )
    if file > bundle or storage < bundle + MIB:
        raise ValueError(
            "Diagnostic storage must fit the bundle plus 1 MiB overhead; file must fit bundle"
        )
    return ExportLimits(file, bundle, values["KEEP_FILES"], storage)


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
        (source, source, "mods", lambda n: n == "crafttweaker.log"),
        (
            source / "logs",
            source,
            "mods",
            lambda n: n in {"groovy.log", "groovy_server.log"},
        ),
    ]:
        candidates.extend(
            (p, boundary, prefix) for p in _files(folder, boundary, predicate)[:3]
        )
    return sorted(
        candidates,
        key=lambda item: {"crashes": 0, "jvm": 1, "launcher": 2, "game": 3, "mods": 4}[
            item[2]
        ],
    )


def export_bundle(
    root: Path, pack: str, *, server_root: Path | None = None, environment=None
) -> dict:
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,47}", pack):
        raise ValueError("Invalid profile id")
    limits = export_limits(environment)
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
        "limits": {
            "file_bytes": limits.file_bytes,
            "bundle_bytes": limits.bundle_bytes,
            "keep_files": limits.keep_files,
            "storage_bytes": limits.storage_bytes,
        },
        "omitted_due_to_budget": 0,
        "notice": "Local redacted diagnostic tails; review before sharing. No automatic upload.",
    }
    remaining = limits.bundle_bytes
    try:
        with zipfile.ZipFile(
            temporary, "x", compression=zipfile.ZIP_DEFLATED
        ) as archive:
            for path, boundary, prefix in candidates:
                if remaining <= 0:
                    metadata["omitted_due_to_budget"] += 1
                    continue
                if not regular(path, boundary):
                    continue
                limit = min(limits.file_bytes, remaining)
                raw, truncated = _excerpt(
                    path, limit, head=prefix in {"crashes", "jvm"}
                )
                clean = redact(
                    raw.decode("utf-8", errors="replace"), secrets, paths
                ).encode()
                truncated = truncated or len(clean) > limit
                clean = clean[:limit].decode("utf-8", errors="ignore").encode()
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
        if index >= limits.keep_files or used > limits.storage_bytes:
            path.unlink()
    return {
        "ok": True,
        "archive": str(output),
        "files": len(metadata["files"]),
        "uploaded": False,
    }
