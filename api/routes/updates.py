"""Read-only update repository. Signing and publishing happen offline."""

import re

from litestar import get
from litestar.exceptions import HTTPException
from litestar.response import File

from api.core.storage import content_root, ensure_exists, safe_resolve


@get("/updates/metadata/{name:str}", sync_to_thread=True)
def update_metadata(name: str) -> File:
    if not re.fullmatch(
        r"(?:[1-9][0-9]{0,9}\.)?(?:root|timestamp|snapshot|targets)\.json", name
    ):
        raise HTTPException(status_code=404, detail="Metadata not found")
    path = ensure_exists(
        safe_resolve(content_root() / "updates/metadata", name), "Metadata not found"
    )
    return File(
        path=path, media_type="application/json", headers={"Cache-Control": "no-cache"}
    )


@get("/updates/targets/{file_path:path}", sync_to_thread=True)
def update_target(file_path: str) -> File:
    file_path = file_path.lstrip("/")
    if not re.fullmatch(
        r"(?:windows-x64|linux-(?:x64|arm64)|macos-(?:x64|arm64))/(?:[a-f0-9]{64}\.)?launcher\.zip",
        file_path,
    ):
        raise HTTPException(status_code=404, detail="Update not found")
    path = ensure_exists(
        safe_resolve(content_root() / "updates/targets", file_path), "Update not found"
    )
    return File(
        path=path, media_type="application/zip", headers={"Cache-Control": "no-cache"}
    )
