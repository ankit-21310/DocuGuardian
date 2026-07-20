"""Database-backed worker for the local/compose deployment."""

from __future__ import annotations

import os
import time

from app.db import connect, fetchone
from app.main import init_db, process_document


def run() -> None:
    init_db()
    poll_seconds = float(os.getenv("WORKER_POLL_SECONDS", "1"))
    while True:
        with connect() as db:
            row = fetchone(db.execute(
                "SELECT d.id, d.organization_id, m.user_id FROM documents d "
                "LEFT JOIN memberships m ON m.organization_id=d.organization_id AND m.role IN ('Owner','Admin') "
                "WHERE d.status='queued' ORDER BY d.created_at LIMIT 1"
            ))
        if not row:
            time.sleep(poll_seconds)
            continue
        user = {"id": row["user_id"], "organization_id": row["organization_id"], "role": "Admin"}
        process_document(row["id"], row["organization_id"], user)


if __name__ == "__main__":
    run()
