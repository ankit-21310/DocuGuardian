from __future__ import annotations

import json
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

import httpx

from .config import (
    FEATURE_EXTERNAL_CALENDAR,
    FRONTEND_URL,
    GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET,
    GOOGLE_REDIRECT_URI,
    MICROSOFT_CLIENT_ID,
    MICROSOFT_CLIENT_SECRET,
    MICROSOFT_REDIRECT_URI,
    MICROSOFT_TENANT_ID,
)
from .db import DB_LOCK, connect, fetchall, fetchone

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar.events"
MICROSOFT_AUTH_URL = f"https://login.microsoftonline.com/{MICROSOFT_TENANT_ID}/oauth2/v2.0/authorize"
MICROSOFT_TOKEN_URL = f"https://login.microsoftonline.com/{MICROSOFT_TENANT_ID}/oauth2/v2.0/token"
MICROSOFT_SCOPE = "Calendars.ReadWrite offline_access"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_oauth_state(organization_id: str, user_id: str, provider: str) -> str:
    """Create a short-lived, single-use state bound to the initiating user."""
    state = secrets.token_urlsafe(32)
    state_hash = hashlib.sha256(state.encode()).hexdigest()
    created = datetime.now(timezone.utc)
    expires = (created + timedelta(minutes=10)).isoformat()
    with DB_LOCK, connect() as db:
        db.execute(
            "INSERT INTO calendar_oauth_states (state_hash,organization_id,user_id,provider,expires_at,created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (state_hash, organization_id, user_id, provider, expires, created.isoformat()),
        )
    return state


def consume_oauth_state(state: str, provider: str) -> dict[str, str] | None:
    """Atomically validate and consume an OAuth state value."""
    state_hash = hashlib.sha256(state.encode()).hexdigest()
    with DB_LOCK, connect() as db:
        row = fetchone(db.execute(
            "SELECT organization_id,user_id,provider,expires_at FROM calendar_oauth_states WHERE state_hash=?",
            (state_hash,),
        ))
        if not row or row["provider"] != provider:
            return None
        try:
            expired = datetime.fromisoformat(str(row["expires_at"]).replace("Z", "+00:00")) <= datetime.now(timezone.utc)
        except ValueError:
            expired = True
        db.execute("DELETE FROM calendar_oauth_states WHERE state_hash=?", (state_hash,))
        if expired:
            return None
        return {"organization_id": row["organization_id"], "user_id": row["user_id"], "provider": row["provider"]}


def is_configured() -> bool:
    google = bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)
    outlook = bool(MICROSOFT_CLIENT_ID and MICROSOFT_CLIENT_SECRET)
    return FEATURE_EXTERNAL_CALENDAR and (google or outlook)


def list_integrations(organization_id: str, user_id: str) -> list[dict[str, Any]]:
    with connect() as db:
        rows = fetchall(db.execute(
            "SELECT id,provider,calendar_id,auto_sync,last_sync_at,created_at FROM calendar_integrations "
            "WHERE organization_id=? AND user_id=? ORDER BY created_at DESC",
            (organization_id, user_id),
        ))
    return [
        {
            "id": row["id"],
            "provider": row["provider"],
            "calendar_id": row.get("calendar_id"),
            "auto_sync": bool(row.get("auto_sync", 1)),
            "last_sync_at": row.get("last_sync_at"),
            "connected": True,
        }
        for row in rows
    ]


def google_authorize_url(state: str) -> str:
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": GOOGLE_CALENDAR_SCOPE,
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


def outlook_authorize_url(state: str) -> str:
    params = {
        "client_id": MICROSOFT_CLIENT_ID,
        "redirect_uri": MICROSOFT_REDIRECT_URI,
        "response_type": "code",
        "scope": MICROSOFT_SCOPE,
        "state": state,
    }
    return f"{MICROSOFT_AUTH_URL}?{urlencode(params)}"


def _store_integration(
    *,
    organization_id: str,
    user_id: str,
    provider: str,
    access_token: str,
    refresh_token: str | None,
    expires_at: str | None,
    calendar_id: str | None = None,
) -> str:
    integration_id = str(uuid.uuid4())
    with DB_LOCK, connect() as db:
        existing = fetchone(db.execute(
            "SELECT id FROM calendar_integrations WHERE organization_id=? AND user_id=? AND provider=?",
            (organization_id, user_id, provider),
        ))
        if existing:
            db.execute(
                "UPDATE calendar_integrations SET access_token=?, refresh_token=?, expires_at=?, calendar_id=?, created_at=? WHERE id=?",
                (access_token, refresh_token, expires_at, calendar_id, now(), existing["id"]),
            )
            return existing["id"]
        db.execute(
            "INSERT INTO calendar_integrations (id,organization_id,user_id,provider,access_token,refresh_token,expires_at,calendar_id,auto_sync,last_sync_at,created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, NULL, ?)",
            (integration_id, organization_id, user_id, provider, access_token, refresh_token, expires_at, calendar_id, now()),
        )
    return integration_id


def complete_google_oauth(code: str, organization_id: str, user_id: str) -> str:
    response = httpx.post(
        GOOGLE_TOKEN_URL,
        data={
            "code": code,
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uri": GOOGLE_REDIRECT_URI,
            "grant_type": "authorization_code",
        },
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    expires_at = None
    if payload.get("expires_in"):
        expires_at = (datetime.now(timezone.utc) + timedelta(seconds=int(payload["expires_in"]))).isoformat()
    return _store_integration(
        organization_id=organization_id,
        user_id=user_id,
        provider="google",
        access_token=payload["access_token"],
        refresh_token=payload.get("refresh_token"),
        expires_at=expires_at,
        calendar_id="primary",
    )


def complete_outlook_oauth(code: str, organization_id: str, user_id: str) -> str:
    response = httpx.post(
        MICROSOFT_TOKEN_URL,
        data={
            "code": code,
            "client_id": MICROSOFT_CLIENT_ID,
            "client_secret": MICROSOFT_CLIENT_SECRET,
            "redirect_uri": MICROSOFT_REDIRECT_URI,
            "grant_type": "authorization_code",
            "scope": MICROSOFT_SCOPE,
        },
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    expires_at = None
    if payload.get("expires_in"):
        expires_at = (datetime.now(timezone.utc) + timedelta(seconds=int(payload["expires_in"]))).isoformat()
    return _store_integration(
        organization_id=organization_id,
        user_id=user_id,
        provider="outlook",
        access_token=payload["access_token"],
        refresh_token=payload.get("refresh_token"),
        expires_at=expires_at,
        calendar_id=None,
    )


def disconnect(organization_id: str, user_id: str, provider: str) -> None:
    with DB_LOCK, connect() as db:
        db.execute(
            "DELETE FROM calendar_integrations WHERE organization_id=? AND user_id=? AND provider=?",
            (organization_id, user_id, provider),
        )


def set_auto_sync(integration_id: str, organization_id: str, user_id: str, enabled: bool) -> None:
    with DB_LOCK, connect() as db:
        db.execute(
            "UPDATE calendar_integrations SET auto_sync=? WHERE id=? AND organization_id=? AND user_id=?",
            (1 if enabled else 0, integration_id, organization_id, user_id),
        )


def _refresh_google_token(integration: dict[str, Any]) -> str:
    if not integration.get("refresh_token"):
        return integration["access_token"]
    response = httpx.post(
        GOOGLE_TOKEN_URL,
        data={
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "refresh_token": integration["refresh_token"],
            "grant_type": "refresh_token",
        },
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    access_token = payload["access_token"]
    expires_at = None
    if payload.get("expires_in"):
        expires_at = (datetime.now(timezone.utc) + timedelta(seconds=int(payload["expires_in"]))).isoformat()
    with DB_LOCK, connect() as db:
        db.execute(
            "UPDATE calendar_integrations SET access_token=?, expires_at=? WHERE id=?",
            (access_token, expires_at, integration["id"]),
        )
    return access_token


def _refresh_outlook_token(integration: dict[str, Any]) -> str:
    if not integration.get("refresh_token"):
        return integration["access_token"]
    response = httpx.post(
        MICROSOFT_TOKEN_URL,
        data={
            "client_id": MICROSOFT_CLIENT_ID,
            "client_secret": MICROSOFT_CLIENT_SECRET,
            "refresh_token": integration["refresh_token"],
            "grant_type": "refresh_token",
            "scope": MICROSOFT_SCOPE,
        },
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    access_token = payload["access_token"]
    expires_at = None
    if payload.get("expires_in"):
        expires_at = (datetime.now(timezone.utc) + timedelta(seconds=int(payload["expires_in"]))).isoformat()
    with DB_LOCK, connect() as db:
        db.execute(
            "UPDATE calendar_integrations SET access_token=?, expires_at=?, refresh_token=COALESCE(?, refresh_token) WHERE id=?",
            (access_token, expires_at, payload.get("refresh_token"), integration["id"]),
        )
    return access_token


def _access_token(integration: dict[str, Any]) -> str:
    expires_at = integration.get("expires_at")
    if expires_at:
        try:
            expiry = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
            if expiry <= datetime.now(timezone.utc) + timedelta(minutes=2):
                if integration["provider"] == "google":
                    return _refresh_google_token(integration)
                return _refresh_outlook_token(integration)
        except ValueError:
            pass
    return integration["access_token"]


def _event_body(deadline: dict[str, Any], document_name: str | None = None) -> dict[str, Any]:
    title = deadline["title"]
    if document_name:
        title = f"{title} ({document_name})"
    due_date = str(deadline["due_date"])[:10]
    return {
        "summary": title,
        "description": f"DocuGuardian deadline from {document_name or 'document'} · {deadline.get('source', 'Document evidence')}",
        "start": {"date": due_date},
        "end": {"date": (datetime.strptime(due_date, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")},
    }


def _upsert_google_event(integration: dict[str, Any], deadline: dict[str, Any], external_event_id: str | None, document_name: str | None) -> str:
    token = _access_token(integration)
    calendar_id = integration.get("calendar_id") or "primary"
    body = _event_body(deadline, document_name)
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    if external_event_id:
        response = httpx.put(
            f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events/{external_event_id}",
            headers=headers,
            content=json.dumps(body),
            timeout=20,
        )
        response.raise_for_status()
        return external_event_id
    response = httpx.post(
        f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events",
        headers=headers,
        content=json.dumps(body),
        timeout=20,
    )
    response.raise_for_status()
    return response.json()["id"]


def _upsert_outlook_event(integration: dict[str, Any], deadline: dict[str, Any], external_event_id: str | None, document_name: str | None) -> str:
    token = _access_token(integration)
    due_date = str(deadline["due_date"])[:10]
    title = deadline["title"]
    if document_name:
        title = f"{title} ({document_name})"
    body = {
        "subject": title,
        "body": {"contentType": "Text", "content": f"DocuGuardian deadline · {deadline.get('source', 'Document evidence')}"},
        "start": {"dateTime": f"{due_date}T09:00:00", "timeZone": deadline.get("timezone") or "UTC"},
        "end": {"dateTime": f"{due_date}T10:00:00", "timeZone": deadline.get("timezone") or "UTC"},
    }
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    if external_event_id:
        response = httpx.patch(
            f"https://graph.microsoft.com/v1.0/me/events/{external_event_id}",
            headers=headers,
            content=json.dumps(body),
            timeout=20,
        )
        response.raise_for_status()
        return external_event_id
    response = httpx.post(
        "https://graph.microsoft.com/v1.0/me/events",
        headers=headers,
        content=json.dumps(body),
        timeout=20,
    )
    response.raise_for_status()
    return response.json()["id"]


def sync_deadline_for_org(deadline_id: str, organization_id: str, user_id: str | None = None) -> int:
    if not is_configured():
        return 0
    with connect() as db:
        deadline = fetchone(db.execute(
            "SELECT d.*, doc.name AS document_name, doc.organization_id FROM deadlines d "
            "JOIN documents doc ON doc.id=d.document_id WHERE d.id=? AND doc.organization_id=?",
            (deadline_id, organization_id),
        ))
        if not deadline:
            return 0
        integration_sql = "SELECT * FROM calendar_integrations WHERE organization_id=? AND auto_sync=1"
        integration_params: tuple[Any, ...] = (organization_id,)
        if user_id:
            integration_sql += " AND user_id=?"
            integration_params += (user_id,)
        integrations = fetchall(db.execute(integration_sql, integration_params))
    synced = 0
    for integration in integrations:
        try:
            mapping = None
            with connect() as db:
                mapping = fetchone(db.execute(
                    "SELECT id, external_event_id FROM calendar_sync_map WHERE deadline_id=? AND integration_id=?",
                    (deadline_id, integration["id"]),
                ))
            external_id = mapping["external_event_id"] if mapping else None
            if integration["provider"] == "google":
                event_id = _upsert_google_event(integration, deadline, external_id, deadline.get("document_name"))
            else:
                event_id = _upsert_outlook_event(integration, deadline, external_id, deadline.get("document_name"))
            with DB_LOCK, connect() as db:
                if mapping:
                    db.execute("UPDATE calendar_sync_map SET external_event_id=? WHERE id=?", (event_id, mapping["id"]))
                else:
                    db.execute(
                        "INSERT INTO calendar_sync_map (id,deadline_id,integration_id,external_event_id) VALUES (?, ?, ?, ?)",
                        (str(uuid.uuid4()), deadline_id, integration["id"], event_id),
                    )
                db.execute("UPDATE calendar_integrations SET last_sync_at=? WHERE id=?", (now(), integration["id"]))
            synced += 1
        except Exception:
            continue
    return synced


def sync_organization_deadlines(organization_id: str, user_id: str) -> dict[str, Any]:
    if not is_configured():
        return {"synced": 0, "message": "External calendar integration is not configured"}
    with connect() as db:
        deadlines = fetchall(db.execute(
            "SELECT d.id FROM deadlines d JOIN documents doc ON doc.id=d.document_id WHERE doc.organization_id=?",
            (organization_id,),
        ))
        integration = fetchone(db.execute(
            "SELECT id FROM calendar_integrations WHERE organization_id=? AND user_id=? LIMIT 1",
            (organization_id, user_id),
        ))
    if not integration:
        return {"synced": 0, "message": "Connect Google or Outlook first"}
    total = 0
    for row in deadlines:
        total += sync_deadline_for_org(row["id"], organization_id, user_id)
    return {"synced": total, "message": f"Synced {total} deadline event(s)"}


def sync_document_deadlines(document_id: str, organization_id: str) -> int:
    if not is_configured():
        return 0
    with connect() as db:
        rows = fetchall(db.execute("SELECT id FROM deadlines WHERE document_id=?", (document_id,)))
    total = 0
    for row in rows:
        total += sync_deadline_for_org(row["id"], organization_id)
    return total


def _delete_google_event(integration: dict[str, Any], external_event_id: str) -> None:
    token = _access_token(integration)
    calendar_id = integration.get("calendar_id") or "primary"
    response = httpx.delete(
        f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events/{external_event_id}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=20,
    )
    if response.status_code not in {200, 204, 404}:
        response.raise_for_status()


def _delete_outlook_event(integration: dict[str, Any], external_event_id: str) -> None:
    token = _access_token(integration)
    response = httpx.delete(
        f"https://graph.microsoft.com/v1.0/me/events/{external_event_id}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=20,
    )
    if response.status_code not in {200, 204, 404}:
        response.raise_for_status()


def delete_document_events(document_id: str, organization_id: str) -> int:
    """Remove provider events before their deadline rows are regenerated."""
    with connect() as db:
        mappings = fetchall(db.execute(
            "SELECT m.id,m.external_event_id,i.*,d.id AS deadline_id FROM calendar_sync_map m "
            "JOIN calendar_integrations i ON i.id=m.integration_id "
            "JOIN deadlines d ON d.id=m.deadline_id "
            "WHERE d.document_id=? AND i.organization_id=?",
            (document_id, organization_id),
        ))
    deleted = 0
    for mapping in mappings:
        try:
            if mapping["provider"] == "google":
                _delete_google_event(mapping, mapping["external_event_id"])
            else:
                _delete_outlook_event(mapping, mapping["external_event_id"])
            deleted += 1
        except Exception:
            continue
    with DB_LOCK, connect() as db:
        db.execute(
            "DELETE FROM calendar_sync_map WHERE deadline_id IN (SELECT id FROM deadlines WHERE document_id=?)",
            (document_id,),
        )
    return deleted


def settings_redirect(status: str, provider: str) -> str:
    return f"{FRONTEND_URL}?calendar={status}&provider={provider}"
