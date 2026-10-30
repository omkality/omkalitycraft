"""Private bounded incident inbox. Only the operator reads it via local filesystem access."""

import contextlib
import hashlib
import json
import os
import sqlite3
import time
from datetime import UTC, datetime
from pathlib import Path

from omk.diagnostics import redact
from omk.fs import resolved
from omk.incidents import MAX_REPORT_BYTES, RETENTION_SECONDS, validate_report


class ReportLimit(RuntimeError):
    pass


class ReportConflict(RuntimeError):
    pass


class ReportStore:
    def __init__(self, root: Path):
        self.root = root.absolute()
        self.path = self.root / "client-reports.sqlite3"
        if resolved(self.root) != self.root or resolved(self.path) != self.path:
            raise ValueError("Linked incident storage")

    def _connect(self, *, readonly=False):
        if readonly:
            return sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True, timeout=5)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if not self.path.exists():
            try:
                descriptor = os.open(
                    self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
                )
                os.close(descriptor)
            except FileExistsError:
                pass  # Another worker created the same private inbox.
        if resolved(self.path) != self.path:
            raise ValueError("Linked incident database")
        deadline = time.monotonic() + 5
        while True:
            db = sqlite3.connect(self.path, timeout=0.25)
            try:
                self._configure(db)
                db.execute("PRAGMA busy_timeout=5000")
                return db
            except sqlite3.Error as error:
                db.close()
                code = getattr(error, "sqlite_errorcode", 0) & 255
                if (
                    code not in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}
                    or time.monotonic() >= deadline
                ):
                    raise
                time.sleep(0.025)

    @staticmethod
    def _configure(db):
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA secure_delete=ON")
        db.execute("PRAGMA journal_size_limit=4194304")
        db.execute("PRAGMA wal_autocheckpoint=128")
        db.execute(
            "PRAGMA max_page_count=32768"
        )  # 128 MiB with the default 4 KiB pages.
        db.execute(
            "CREATE TABLE IF NOT EXISTS reports (id TEXT PRIMARY KEY, player TEXT NOT NULL, "
            "received INTEGER NOT NULL, digest TEXT NOT NULL, body TEXT NOT NULL)"
        )
        db.execute(
            "CREATE INDEX IF NOT EXISTS reports_player_time ON reports(player, received)"
        )
        db.execute(
            "CREATE TABLE IF NOT EXISTS report_rates (player TEXT NOT NULL, sent INTEGER NOT NULL)"
        )
        db.execute(
            "CREATE INDEX IF NOT EXISTS report_rates_player_time ON report_rates(player, sent)"
        )
        db.commit()

    @staticmethod
    def _prune(db, now):
        db.execute("DELETE FROM report_rates WHERE sent<=?", (now - 3600,))
        db.execute("DELETE FROM reports WHERE received < ?", (now - RETENTION_SECONDS,))
        db.execute(
            "DELETE FROM reports WHERE id NOT IN (SELECT id FROM reports ORDER BY received DESC, rowid DESC LIMIT 1000)"
        )

    def ingest(self, value: dict, *, player: str, token: str, now=None, name=None):
        report = dict(validate_report(value))
        if report["player"] != player:
            raise ReportConflict("Authenticated profile mismatch")
        report["detail"] = redact(report["detail"], (token,))
        body = json.dumps(report, ensure_ascii=False, sort_keys=True)
        if len(body.encode()) > MAX_REPORT_BYTES:
            raise ValueError("Incident exceeds storage budget")
        digest = hashlib.sha256(body.encode()).hexdigest()
        if isinstance(name, str) and len(name) <= 64:
            body = json.dumps(
                {**report, "verified_name": name}, ensure_ascii=False, sort_keys=True
            )
        now = int(time.time() if now is None else now)
        with contextlib.closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute(
                "SELECT player,digest FROM reports WHERE id=?", (report["id"],)
            ).fetchone()
            if existing:
                if existing != (player, digest):
                    raise ReportConflict("Incident identifier conflict")
                return {"ok": True, "id": report["id"]}
            count = db.execute(
                "SELECT count(*) FROM report_rates WHERE player=? AND sent>?",
                (player, now - 3600),
            ).fetchone()[0]
            if count >= 3:
                raise ReportLimit("Client incident rate limit")
            db.execute("INSERT INTO report_rates VALUES (?,?)", (player, now))
            db.execute(
                "INSERT INTO reports VALUES (?,?,?,?,?)",
                (report["id"], player, now, digest, body),
            )
            db.execute(
                "DELETE FROM reports WHERE player=? AND id NOT IN "
                "(SELECT id FROM reports WHERE player=? ORDER BY received DESC,rowid DESC LIMIT 20)",
                (player, player),
            )
            self._prune(db, now)
        return {"ok": True, "id": report["id"]}

    def list(self, *, limit=20, player=None):
        if not 1 <= limit <= 100:
            raise ValueError("Invalid report list limit")
        if not self.path.exists():
            return []
        with contextlib.closing(self._connect(readonly=True)) as db:
            rows = db.execute(
                "SELECT id,player,received,body FROM reports WHERE received>=? "
                "AND (? IS NULL OR player=?) ORDER BY received DESC,rowid DESC LIMIT ?",
                (int(time.time()) - RETENTION_SECONDS, player, player, limit),
            ).fetchall()
        return [
            {
                "id": row[0],
                "player": row[1],
                "received": row[2],
                "received_at": datetime.fromtimestamp(row[2], UTC).isoformat(),
                "name": json.loads(row[3]).get("verified_name"),
                **{
                    k: json.loads(row[3])[k]
                    for k in ("kind", "pack", "pack_version", "exit_code")
                },
            }
            for row in rows
        ]

    def get(self, report_id):
        with contextlib.closing(self._connect(readonly=True)) as db:
            row = db.execute(
                "SELECT body FROM reports WHERE id=? AND received>=?",
                (report_id, int(time.time()) - RETENTION_SECONDS),
            ).fetchone()
        if row is None:
            raise ValueError("Client incident not found or expired")
        return json.loads(row[0])

    def prune(self):
        if not self.path.exists():
            return
        with contextlib.closing(self._connect()) as db, db:
            self._prune(db, int(time.time()))
