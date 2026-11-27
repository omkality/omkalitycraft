"""Deliver a queued client report to the configured incident API."""

import json
import re
from pathlib import Path
from uuid import UUID

from launcher.session import Session
from omk.accounts.drasl import DraslClient
from omk.observability.diagnostics import _files, event
from omk.observability.incidents import (
    MAX_REPORT_BYTES,
    _prune,
    _queue,
    validate_report,
)


def submit_pending(
    root: Path, origin: str | None, session: Session, *, report_id: str | None = None
) -> bool:
    """Return whether the API acknowledged the requested report or one pending report."""
    if origin is None:
        return False
    try:
        folder = _queue(root)
        _prune(root, folder)
        client = DraslClient(origin, timeout=3)
        player = UUID(session.player_uuid).hex
        files = _files(
            folder, root, lambda n: bool(re.fullmatch(r"[a-f0-9]{32}\.json", n))
        )
        for path in files:
            if report_id is not None and path.stem != report_id:
                continue
            with path.open("rb") as file:
                raw = file.read(MAX_REPORT_BYTES + 1)
            if len(raw) > MAX_REPORT_BYTES:
                continue
            try:
                report = validate_report(json.loads(raw))
            except ValueError, TypeError:
                continue
            if report["id"] != path.stem or report["player"] != player:
                continue
            response = client.request(
                "POST", "/reports/client", report, session.access_token
            )
            if not (
                isinstance(response, dict)
                and response.get("id") == report["id"]
                and response.get("ok") is True
            ):
                return False
            event(root, "client_incident_delivered", report_id=report["id"])
            try:
                path.unlink()
            except OSError as error:
                event(
                    root,
                    "client_incident_queue_cleanup_failed",
                    error_type=type(error).__name__,
                )
            return True
    except Exception as error:
        event(
            root, "client_incident_delivery_deferred", error_type=type(error).__name__
        )
    return False
