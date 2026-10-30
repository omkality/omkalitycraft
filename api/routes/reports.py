"""Upload-only crash inbox. There is deliberately no remote list/download/admin route."""

import re
import sqlite3
from pathlib import Path
from urllib.error import URLError
from uuid import UUID

from litestar import Request, post
from litestar.exceptions import HTTPException
from litestar.middleware.rate_limit import RateLimitConfig, get_remote_address

from api.settings.config import settings
from omk.drasl import DraslClient, DraslError
from omk.report_store import ReportConflict, ReportLimit, ReportStore


@post(
    "/reports/client",
    status_code=201,
    request_max_body_size=128 * 1024,
    sync_to_thread=True,
    middleware=[
        RateLimitConfig(
            rate_limit=("minute", 20),
            identifier_for_request=lambda request: "client-reports:"
            + get_remote_address(request),
        ).middleware
    ],
)
def upload_client_report(request: Request, data: dict) -> dict:
    if not settings.client_reports_root or not settings.client_reports_auth_url:
        raise HTTPException(status_code=404, detail="Client reports are not configured")
    root = Path(settings.client_reports_root).absolute()
    if root.resolve().is_relative_to(Path(settings.content_root).resolve()):
        raise HTTPException(
            status_code=503, detail="Private incident storage is not configured"
        )
    authorization = request.headers.get("authorization", "")
    if (
        not authorization.startswith("Bearer ")
        or re.fullmatch(r"[A-Za-z0-9_.~-]{16,8192}", authorization[7:]) is None
    ):
        raise HTTPException(status_code=401, detail="Game authentication required")
    token = authorization[7:]
    try:
        profile = DraslClient(settings.client_reports_auth_url).request(
            "GET", "/minecraft/profile", token=token
        )
        player = UUID(profile["id"]).hex
    except DraslError as error:
        raise HTTPException(
            status_code=401 if error.status in {400, 401, 403} else 503,
            detail="Cannot verify game session",
        ) from None
    except URLError, OSError, ValueError, KeyError, TypeError:
        raise HTTPException(
            status_code=503, detail="Cannot verify game session"
        ) from None
    try:
        return ReportStore(root).ingest(
            data, player=player, token=token, name=profile.get("name")
        )
    except ReportLimit:
        raise HTTPException(
            status_code=429, detail="Client incident limit reached"
        ) from None
    except ReportConflict:
        raise HTTPException(
            status_code=409, detail="Client incident identity conflict"
        ) from None
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid client incident") from None
    except OSError, sqlite3.Error:
        raise HTTPException(
            status_code=503, detail="Client incident storage unavailable"
        ) from None
