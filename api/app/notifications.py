from __future__ import annotations

import smtplib
import uuid
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Any
from urllib.parse import urlparse

from .config import NOTIFICATION_FROM, SMTP_URL
from .db import DB_LOCK, connect


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


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
