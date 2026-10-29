"""Runtime account data is never a publishable launcher/modpack artifact."""

from pathlib import PurePosixPath


def is_private_path(path: str) -> bool:
    parts = [part.casefold() for part in PurePosixPath(path.replace("\\", "/")).parts]
    return any(
        part
        in {"userdata", ".local", ".git", "auth_token.json", "session.json", ".env"}
        or part.startswith(".env.")
        for part in parts
    )
