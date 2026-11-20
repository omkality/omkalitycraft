"""Explicit report delivery for the operator's isolated test fixtures."""

import contextlib
import json
import re
from pathlib import Path
from uuid import UUID

from launcher.session import Session
from omk.diagnostics import _files, event
from omk.drasl import DraslClient
from omk.incidents import MAX_REPORT_BYTES, _prune, _queue, validate_report


def submit_pending(root: Path, origin: str | None, session: Session) -> None:
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
