from __future__ import annotations

import smtplib
import uuid
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from typing import Any
from urllib.parse import urlparse

from .config import NOTIFICATION_FROM, SMTP_URL
from .db import DB_LOCK, connect, fetchall, fetchone, is_postgres


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _scheduled_time(due_date: str, days_before: int) -> str:
    """Return a stable UTC delivery time for a date-only extracted deadline."""
    raw = str(due_date).replace("Z", "+00:00")
    try:
        due = datetime.fromisoformat(raw)
    except ValueError:
        due = datetime.strptime(str(due_date)[:10], "%Y-%m-%d")
    if due.tzinfo is None:
        due = due.replace(tzinfo=timezone.utc)
    scheduled = due.astimezone(timezone.utc).replace(hour=9, minute=0, second=0, microsecond=0)
    scheduled -= timedelta(days=days_before)
    return scheduled.isoformat()


def deliver_reminder(
    *,
    organization_id: str,
    user_id: str,
    deadline: dict[str, Any],
    reminder_id: str,
    channel: str,
) -> dict[str, Any]:
    title = f"Reminder: {deadline['title']}"
    body = f"{deadline['title']} is due on {deadline['due_date']} ({deadline.get('priority', 'medium')} priority)."
    notification = {
        "id": str(uuid.uuid4()),
        "organization_id": organization_id,
        "user_id": user_id,
        "title": title,
        "body": body,
        "channel": channel,
        "status": "delivered",
        "created_at": now(),
        "read_at": None,
        "related_deadline_id": deadline["id"],
        "related_document_id": deadline.get("document_id"),
    }
    with DB_LOCK, connect() as db:
        db.execute(
            "INSERT INTO notifications (id,organization_id,user_id,title,body,channel,status,created_at,read_at,related_deadline_id,related_document_id) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            tuple(notification.values()),
        )
        db.execute(
            "UPDATE reminders SET status='delivered', delivered_at=? WHERE id=?",
            (now(), reminder_id),
        )
    if channel == "email":
        _send_email(user_id=user_id, title=title, body=body)
    return notification


def process_due_reminders(limit: int = 50) -> int:
    """Claim and deliver reminders whose scheduled time has arrived.

    SQLite is protected by the process-wide lock. PostgreSQL uses row locks so
    multiple workers can safely share the same reminder queue.
    """
    current = now()
    claimed: list[dict[str, Any]] = []
    with DB_LOCK, connect() as db:
        if is_postgres():
            rows = fetchall(db.execute(
                "SELECT r.*, d.title, d.due_date, d.priority, d.document_id, d.source "
                ", doc.organization_id FROM reminders r JOIN deadlines d ON d.id=r.deadline_id "
                "JOIN documents doc ON doc.id=d.document_id "
                "WHERE r.status='scheduled' AND r.user_id IS NOT NULL AND r.scheduled_for IS NOT NULL AND r.scheduled_for <= ? "
                "ORDER BY r.scheduled_for LIMIT ? FOR UPDATE SKIP LOCKED",
                (current, limit),
            ))
        else:
            rows = fetchall(db.execute(
                "SELECT r.*, d.title, d.due_date, d.priority, d.document_id, d.source "
                ", doc.organization_id FROM reminders r JOIN deadlines d ON d.id=r.deadline_id "
                "JOIN documents doc ON doc.id=d.document_id "
                "WHERE r.status='scheduled' AND r.user_id IS NOT NULL AND r.scheduled_for IS NOT NULL AND r.scheduled_for <= ? "
                "ORDER BY r.scheduled_for LIMIT ?",
                (current, limit),
            ))
        for row in rows:
            db.execute("UPDATE reminders SET status='processing', error=NULL WHERE id=? AND status='scheduled'", (row["id"],))
            claimed.append(row)

    delivered = 0
    for reminder in claimed:
        try:
            deadline = dict(reminder)
            deadline["id"] = reminder["deadline_id"]
            deliver_reminder(
                organization_id=reminder["organization_id"],
                user_id=reminder["user_id"],
                deadline=deadline,
                reminder_id=reminder["id"],
                channel=reminder["channel"],
            )
            delivered += 1
        except Exception as error:
            with DB_LOCK, connect() as db:
                db.execute("UPDATE reminders SET status='failed', error=? WHERE id=?", (str(error)[:500], reminder["id"]))
    return delivered


def _send_email(*, user_id: str, title: str, body: str) -> None:
    if not SMTP_URL:
        return
    from .db import fetchone

    with connect() as db:
        user = fetchone(db.execute("SELECT email FROM users WHERE id=?", (user_id,)))
    if not user:
        return
    email = user["email"]
    parsed = urlparse(SMTP_URL)
    message = EmailMessage()
    message["From"] = NOTIFICATION_FROM
    message["To"] = email
    message["Subject"] = title
    message.set_content(body)
    host = parsed.hostname or "localhost"
    port = parsed.port or 25
    with smtplib.SMTP(host, port, timeout=10) as smtp:
        if parsed.username:
            smtp.login(parsed.username, parsed.password or "")
        smtp.send_message(message)
