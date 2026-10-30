"""Hourly expiry of the private crash inbox; no alerting or remote filesystem access."""

import asyncio
import contextlib
import logging
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path

from api.settings.config import settings
from omk.report_store import ReportStore


def prune_reports():
    if not settings.client_reports_root or not settings.client_reports_auth_url:
        return
    root = Path(settings.client_reports_root).absolute()
    if root.resolve().is_relative_to(Path(settings.content_root).resolve()):
        return
    try:
        ReportStore(root).prune()
    except (OSError, ValueError, sqlite3.Error) as error:
        logging.getLogger(__name__).warning(
            "Incident retention deferred (%s)", type(error).__name__
        )


@asynccontextmanager
async def report_retention(_app):
    if not settings.client_reports_root or not settings.client_reports_auth_url:
        yield
        return

    async def maintain():
        while True:
            await asyncio.to_thread(prune_reports)
            await asyncio.sleep(3600)

    task = asyncio.create_task(maintain())
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
