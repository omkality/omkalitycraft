"""Runtime account data is never a publishable launcher/modpack artifact."""

import re
from pathlib import PurePosixPath


def is_private_path(path: str) -> bool:
    parts = [part.casefold() for part in PurePosixPath(path.replace("\\", "/")).parts]
    return any(
        part
        in {
            "userdata",
            ".local",
            ".git",
            "auth_token.json",
            "session.json",
            ".env",
            ".omk-admin",
            "logs",
            "crash-reports",
            "diagnostics",
            "server.properties",
            "client-reports.sqlite3",
            "client-reports.sqlite3-wal",
            "client-reports.sqlite3-shm",
        }
        or part.startswith(".env.")
        or re.fullmatch(r"hs_err_pid\d+\.log|java_pid\d+\.hprof", part) is not None
        for part in parts
    )
