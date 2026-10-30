"""Public, read-only signed releases; no publishing or management endpoint."""

import re

from litestar import get
from litestar.exceptions import HTTPException
from litestar.response import File

from api.core.storage import content_root, ensure_exists, safe_resolve


def release_root(pack_id: str, platform: str):
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,47}", pack_id) or platform not in {
        "windows-x64",
        "linux-x64",
        "linux-arm64",
        "macos-x64",
        "macos-arm64",
    }:
        raise HTTPException(status_code=404, detail="Release not found")
    return safe_resolve(content_root() / "releases", f"{pack_id}/{platform}")


@get("/releases/{pack_id:str}/{platform:str}/manifest", sync_to_thread=True)
def get_release_manifest(pack_id: str, platform: str) -> File:
    path = ensure_exists(
        release_root(pack_id, platform) / "manifest.json", "Release not found"
    )
    return File(path=path, media_type="application/json")


@get(
    "/releases/{pack_id:str}/{platform:str}/files/{file_path:path}", sync_to_thread=True
)
def get_release_file(pack_id: str, platform: str, file_path: str) -> File:
    root = release_root(pack_id, platform) / "files"
    path = ensure_exists(safe_resolve(root, file_path), "File not found")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return File(path=path, media_type="application/octet-stream")
