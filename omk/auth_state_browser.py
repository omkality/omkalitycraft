"""Offline Drasl 4.0 browser-session revocation for an isolated restore volume."""

import json
import sqlite3


def clear():
    with sqlite3.connect("/state/drasl.db") as db:
        columns = {row[1] for row in db.execute("PRAGMA table_info(users)")}
        if not {"uuid", "browser_token", "is_locked"} <= columns:
            raise ValueError("Unsupported Drasl schema; keep restore offline")
        count = db.execute("UPDATE users SET browser_token = NULL").rowcount
        if db.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise ValueError("Restore integrity failed")
    return {"browser_credentials_revoked": count}


if __name__ == "__main__":
    print(json.dumps(clear()))
