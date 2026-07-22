from __future__ import annotations

import base64
import difflib
import hashlib
import hmac
import json
import mimetypes
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from . import ai
from .report_pdf import render_report_pdf
from .ai import retrieve_chunks, speech_text_for_language, synthesize_speech, translate_report, translate_text
from .config import (
    CORS_ORIGINS,
    ENABLE_DEMO_AUTH,
    ENVIRONMENT,
    FEATURE_EXTERNAL_CALENDAR,
    FEATURE_FRAUD,
    FEATURE_TRANSLATION,
    FEATURE_VOICE,
    GOOGLE_CLIENT_ID,
    LANGUAGE_CODES,
    MICROSOFT_CLIENT_ID,
    SUPPORTED_LANGUAGES,
    MAX_UPLOAD_BYTES,
    PIPELINE_STAGES,
    PROCESSING_MODE,
    SUPPORTED_SUFFIXES,
    SUPPORTED_TYPES,
    UPLOAD_DIR,
    resolve_auth_secret,
)
from . import calendar_sync
from .db import DB_LOCK, IntegrityError, SCHEMA_SQL, connect, fetchall, fetchone, is_postgres
from .notifications import _scheduled_time, deliver_reminder, process_due_reminders
from .pipeline_runner import run_pipeline
from .storage import delete_object, store_object


AUTH_SECRET = resolve_auth_secret()
ROLES = {"Owner", "Admin", "Member", "Viewer"}
BEARER = HTTPBearer(auto_error=False)

app = FastAPI(title="DocuGuardian API", version="0.3.0", openapi_url="/api/v1/openapi.json")
_cors_options: dict[str, Any] = {
    "allow_origins": CORS_ORIGINS,
    "allow_credentials": True,
    "allow_methods": ["*"],
    "allow_headers": ["*"],
}
if ENVIRONMENT == "development":
    _cors_options["allow_origin_regex"] = r"https?://(localhost|127\.0\.0\.1)(:\d+)?"
app.add_middleware(CORSMiddleware, **_cors_options)

_reminder_stop = threading.Event()
_reminder_thread: threading.Thread | None = None


def answer_question(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Indirection keeps provider monkeypatches and test adapters effective."""
    return ai.answer_question(*args, **kwargs)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def password_hash(password: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), AUTH_SECRET, 120_000).hex()


def make_token(user_id: str) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {"sub": user_id, "exp": int((datetime.now(timezone.utc) + timedelta(hours=8)).timestamp())}

    def encode(value: dict[str, Any]) -> str:
        return base64.urlsafe_b64encode(json.dumps(value, separators=(",", ":")).encode()).decode().rstrip("=")

    encoded_header, encoded_payload = encode(header), encode(payload)
    message = f"{encoded_header}.{encoded_payload}"
    signature = hmac.new(AUTH_SECRET, message.encode(), hashlib.sha256).digest()
    return f"{message}.{base64.urlsafe_b64encode(signature).decode().rstrip('=')}"


def decode_token(token: str) -> str:
    try:
        header, payload, signature = token.split(".", 2)
        message = f"{header}.{payload}"
        expected = base64.urlsafe_b64encode(hmac.new(AUTH_SECRET, message.encode(), hashlib.sha256).digest()).decode().rstrip("=")
        if not hmac.compare_digest(signature, expected):
            raise ValueError
        padded = payload + "=" * (-len(payload) % 4)
        claims = json.loads(base64.urlsafe_b64decode(padded).decode())
        if int(claims.get("exp", 0)) <= int(datetime.now(timezone.utc).timestamp()):
            raise ValueError
        return str(claims["sub"])
    except (ValueError, KeyError, TypeError, json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(status_code=401, detail="Invalid or expired authentication token")


def init_db() -> None:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    with connect() as db:
        db.executescript(SCHEMA_SQL)
        _migrate_columns(db)
        _backfill_legacy_data(db)
        db.execute(
            "UPDATE documents SET status='completed', updated_at=? WHERE status='processing' AND stage='Complete' AND report_json IS NOT NULL",
            (now(),),
        )
        if ENABLE_DEMO_AUTH:
            if is_postgres():
                db.execute(
                    "INSERT INTO organizations VALUES (?, ?, ?) ON CONFLICT (id) DO NOTHING",
                    ("demo-org", "Personal workspace", now()),
                )
                db.execute(
                    "INSERT INTO users VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT (id) DO NOTHING",
                    ("demo-user", "alex@example.com", "Alex Morgan", password_hash("demo-password"), "Owner", now()),
                )
                db.execute(
                    "INSERT INTO memberships VALUES (?, ?, ?) ON CONFLICT (user_id, organization_id) DO NOTHING",
                    ("demo-user", "demo-org", "Owner"),
                )
            else:
                db.execute("INSERT OR IGNORE INTO organizations VALUES (?, ?, ?)", ("demo-org", "Personal workspace", now()))
                db.execute(
                    "INSERT OR IGNORE INTO users VALUES (?, ?, ?, ?, ?, ?)",
                    ("demo-user", "alex@example.com", "Alex Morgan", password_hash("demo-password"), "Owner", now()),
                )
                db.execute("INSERT OR IGNORE INTO memberships VALUES (?, ?, ?)", ("demo-user", "demo-org", "Owner"))


def _migrate_columns(db) -> None:
    if is_postgres():
        migrations = [
            "ALTER TABLE documents ADD COLUMN IF NOT EXISTS extracted_text TEXT",
            "ALTER TABLE reminders ADD COLUMN IF NOT EXISTS delivered_at TEXT",
            "ALTER TABLE reminders ADD COLUMN IF NOT EXISTS user_id TEXT",
            "ALTER TABLE reminders ADD COLUMN IF NOT EXISTS scheduled_for TEXT",
            "ALTER TABLE reminders ADD COLUMN IF NOT EXISTS error TEXT",
            "ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS session_id TEXT",
        ]
        for statement in migrations:
            try:
                db.execute(statement)
            except Exception:
                pass
        return
    columns = {row[1] for row in db.execute("PRAGMA table_info(documents)").fetchall()}
    if "organization_id" not in columns:
        db.execute("ALTER TABLE documents ADD COLUMN organization_id TEXT NOT NULL DEFAULT 'demo-org'")
    if "extracted_text" not in columns:
        db.execute("ALTER TABLE documents ADD COLUMN extracted_text TEXT")
    audit_columns = {row[1] for row in db.execute("PRAGMA table_info(audit_logs)").fetchall()}
    if "organization_id" not in audit_columns:
        db.execute("ALTER TABLE audit_logs ADD COLUMN organization_id TEXT")
    if "user_id" not in audit_columns:
        db.execute("ALTER TABLE audit_logs ADD COLUMN user_id TEXT")
    deadline_columns = {row[1] for row in db.execute("PRAGMA table_info(deadlines)").fetchall()}
    if deadline_columns and "timezone" not in deadline_columns:
        db.execute("ALTER TABLE deadlines ADD COLUMN timezone TEXT NOT NULL DEFAULT 'UTC'")
    reminder_columns = {row[1] for row in db.execute("PRAGMA table_info(reminders)").fetchall()}
    if reminder_columns and "delivered_at" not in reminder_columns:
        db.execute("ALTER TABLE reminders ADD COLUMN delivered_at TEXT")
    if reminder_columns and "user_id" not in reminder_columns:
        db.execute("ALTER TABLE reminders ADD COLUMN user_id TEXT")
    if reminder_columns and "scheduled_for" not in reminder_columns:
        db.execute("ALTER TABLE reminders ADD COLUMN scheduled_for TEXT")
    if reminder_columns and "error" not in reminder_columns:
        db.execute("ALTER TABLE reminders ADD COLUMN error TEXT")
    message_columns = {row[1] for row in db.execute("PRAGMA table_info(chat_messages)").fetchall()}
    if message_columns and "session_id" not in message_columns:
        db.execute("ALTER TABLE chat_messages ADD COLUMN session_id TEXT")


def _backfill_legacy_data(db) -> None:
    """Make pre-session chats and pre-ID action plans usable after upgrades."""
    legacy_pairs = fetchall(db.execute(
        "SELECT DISTINCT user_id,document_id FROM chat_messages WHERE session_id IS NULL"
    ))
    for pair in legacy_pairs:
        messages = fetchall(db.execute(
            "SELECT id,content,created_at FROM chat_messages WHERE user_id=? AND document_id=? AND session_id IS NULL ORDER BY created_at ASC",
            (pair["user_id"], pair["document_id"]),
        ))
        if not messages:
            continue
        session_id = str(uuid.uuid4())
        created_at = messages[0]["created_at"]
        updated_at = messages[-1]["created_at"]
        first_message = str(messages[0].get("content") or "Imported chat")
        db.execute(
            "INSERT INTO chat_sessions (id,user_id,document_id,title,created_at,updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (session_id, pair["user_id"], pair["document_id"], _session_title(first_message), created_at, updated_at),
        )
        for message in messages:
            db.execute("UPDATE chat_messages SET session_id=? WHERE id=?", (session_id, message["id"]))

    documents = fetchall(db.execute(
        "SELECT id,report_json FROM documents WHERE report_json IS NOT NULL"
    ))
    for document in documents:
        try:
            report = json.loads(document["report_json"])
        except (TypeError, json.JSONDecodeError):
            continue
        action_plan = report.get("action_plan")
        if not isinstance(action_plan, list) or not action_plan:
            continue
        items = fetchall(db.execute(
            "SELECT id,title,detail,priority,due_date,status FROM action_items WHERE document_id=? ORDER BY ordinal",
            (document["id"],),
        ))
        changed = False
        for ordinal, action in enumerate(action_plan):
            if not isinstance(action, dict):
                continue
            item = items[ordinal] if ordinal < len(items) else None
            if item is None:
                item_id = str(uuid.uuid4())
                db.execute(
                    "INSERT INTO action_items (id,document_id,title,detail,priority,status,due_date,ordinal) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (item_id, document["id"], action.get("title", "Action"), action.get("detail", ""), action.get("priority", "medium"), action.get("status", "open"), action.get("due_date"), ordinal),
                )
                item = {"id": item_id, "status": action.get("status", "open")}
                items.append(item)
            if not action.get("id"):
                action["id"] = item["id"]
                changed = True
            if item.get("status") and action.get("status") != item["status"]:
                action["status"] = item["status"]
                changed = True
        if changed:
            db.execute(
                "UPDATE documents SET report_json=?, updated_at=? WHERE id=?",
                (json.dumps(report), now(), document["id"]),
            )


@app.on_event("startup")
def startup() -> None:
    init_db()
    global _reminder_thread
    if PROCESSING_MODE == "local" and (_reminder_thread is None or not _reminder_thread.is_alive()):
        _reminder_stop.clear()
        _reminder_thread = threading.Thread(target=_reminder_loop, name="docuguardian-reminders", daemon=True)
        _reminder_thread.start()


@app.on_event("shutdown")
def shutdown() -> None:
    _reminder_stop.set()


def _reminder_loop() -> None:
    while not _reminder_stop.is_set():
        try:
            process_due_reminders()
        except Exception:
            # The next tick retries transient database or delivery failures.
            pass
        _reminder_stop.wait(30)


def user_payload(user_id: str) -> dict[str, Any]:
    with connect() as db:
        user = fetchone(db.execute("SELECT id,email,name,role,created_at FROM users WHERE id=?", (user_id,)))
        membership = fetchone(db.execute(
            "SELECT organization_id,role FROM memberships WHERE user_id=? ORDER BY organization_id LIMIT 1", (user_id,)
        ))
    if not user or not membership:
        raise HTTPException(status_code=401, detail="User or organization not found")
    return {**user, "organization_id": membership["organization_id"], "role": membership["role"]}


def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(BEARER)) -> dict[str, Any]:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user_payload(decode_token(credentials.credentials))


def require_role(*allowed: str):
    def dependency(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
        if user["role"] not in allowed:
            raise HTTPException(status_code=403, detail="Insufficient organization permissions")
        return user

    return dependency


def row_document(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item.pop("storage_key", None)
    item.pop("organization_id", None)
    item.pop("extracted_text", None)
    report_json = item.pop("report_json", None)
    item["report"] = filter_report_features(json.loads(report_json)) if report_json else None
    return item


def filter_report_features(report: dict[str, Any]) -> dict[str, Any]:
    """Keep disabled feature data out of API responses and exports."""
    filtered = dict(report)
    if not FEATURE_FRAUD:
        filtered["fraud_indicators"] = []
    return filtered


def fetch_document(document_id: str, organization_id: str) -> dict[str, Any]:
    with connect() as db:
        row = fetchone(db.execute(
            "SELECT * FROM documents WHERE id=? AND organization_id=?", (document_id, organization_id)
        ))
    if not row:
        raise HTTPException(status_code=404, detail="Document not found")
    return row


def record_audit(document_id: str | None, action: str, user: dict[str, Any] | None = None) -> None:
    with DB_LOCK, connect() as db:
        db.execute(
            "INSERT INTO audit_logs (id,organization_id,user_id,document_id,action,created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (
                str(uuid.uuid4()),
                user["organization_id"] if user else None,
                user["id"] if user else None,
                document_id,
                action,
                now(),
            ),
        )


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    target_language: str | None = Field(default=None, max_length=64)
    session_id: str | None = Field(default=None, max_length=64)


class CreateSessionRequest(BaseModel):
    document_id: str = Field(min_length=1, max_length=64)


CHAT_HISTORY_LIMIT = 20


def _session_title(message: str) -> str:
    cleaned = " ".join(message.split())
    if len(cleaned) <= 60:
        return cleaned or "New chat"
    cut = cleaned[:60]
    last_space = cut.rfind(" ")
    if last_space > 40:
        cut = cut[:last_space]
    return f"{cut.rstrip()}…"


def _fetch_chat_session(session_id: str, user_id: str) -> dict[str, Any]:
    with connect() as db:
        row = fetchone(db.execute(
            "SELECT s.*, d.name AS document_name FROM chat_sessions s "
            "JOIN documents d ON d.id=s.document_id WHERE s.id=? AND s.user_id=?",
            (session_id, user_id),
        ))
    if not row:
        raise HTTPException(status_code=404, detail="Chat session not found")
    return row


def _create_chat_session(db, user_id: str, document_id: str) -> str:
    session_id = str(uuid.uuid4())
    timestamp = now()
    db.execute(
        "INSERT INTO chat_sessions (id,user_id,document_id,title,created_at,updated_at) VALUES (?, ?, ?, ?, ?, ?)",
        (session_id, user_id, document_id, "New chat", timestamp, timestamp),
    )
    return session_id


def _load_session_history(db, session_id: str, limit: int = CHAT_HISTORY_LIMIT) -> list[dict[str, Any]]:
    rows = fetchall(db.execute(
        "SELECT role, content FROM chat_messages WHERE session_id=? "
        "ORDER BY created_at DESC, CASE role WHEN 'assistant' THEN 1 ELSE 0 END DESC LIMIT ?",
        (session_id, limit),
    ))
    rows.reverse()
    return rows


def _resolve_chat_session(
    db,
    user: dict[str, Any],
    document_id: str,
    session_id: str | None,
) -> str:
    if session_id:
        session = fetchone(db.execute(
            "SELECT id, document_id FROM chat_sessions WHERE id=? AND user_id=?",
            (session_id, user["id"]),
        ))
        if not session:
            raise HTTPException(status_code=404, detail="Chat session not found")
        if session["document_id"] != document_id:
            raise HTTPException(status_code=409, detail="Chat session does not match this document")
        return session_id
    return _create_chat_session(db, user["id"], document_id)


class ReminderRequest(BaseModel):
    channel: str = Field(default="in_app", pattern="^(in_app|email)$")
    days_before: int = Field(default=7, ge=0, le=365)


class ActionItemUpdate(BaseModel):
    status: str = Field(pattern="^(open|completed)$")


class ComparisonRequest(BaseModel):
    document_a_id: str
    document_b_id: str


class RegisterRequest(BaseModel):
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    name: str = Field(min_length=2, max_length=100)
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: str
    password: str


class TranslateRequest(BaseModel):
    text: str = Field(min_length=1, max_length=8000)
    target_language: str = Field(min_length=2, max_length=64)


class ReportTranslationRequest(BaseModel):
    target_language: str = Field(min_length=2, max_length=64)


class VoiceRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    target_language: str | None = Field(default=None, max_length=64)


@app.post("/api/v1/auth/demo")
def demo_login() -> dict[str, Any]:
    if not ENABLE_DEMO_AUTH:
        raise HTTPException(status_code=404, detail="Not found")
    return {"access_token": make_token("demo-user"), "token_type": "bearer", "user": user_payload("demo-user")}


@app.post("/api/v1/auth/register", status_code=201)
def register(request: RegisterRequest) -> dict[str, Any]:
    user_id, organization_id = str(uuid.uuid4()), str(uuid.uuid4())
    with DB_LOCK, connect() as db:
        try:
            db.execute(
                "INSERT INTO users VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, request.email.lower(), request.name.strip(), password_hash(request.password), "Owner", now()),
            )
            db.execute("INSERT INTO organizations VALUES (?, ?, ?)", (organization_id, f"{request.name.strip()}'s workspace", now()))
            db.execute("INSERT INTO memberships VALUES (?, ?, 'Owner')", (user_id, organization_id))
        except IntegrityError:
            raise HTTPException(status_code=409, detail="An account with that email already exists")
    return {"access_token": make_token(user_id), "token_type": "bearer", "user": user_payload(user_id)}


@app.post("/api/v1/auth/login")
def login(request: LoginRequest) -> dict[str, Any]:
    with connect() as db:
        user = fetchone(db.execute("SELECT id,password_hash FROM users WHERE email=?", (request.email.lower(),)))
    legacy_hash = hashlib.sha256(request.password.encode()).hexdigest()
    if not user or not (
        hmac.compare_digest(user["password_hash"], password_hash(request.password))
        or hmac.compare_digest(user["password_hash"], legacy_hash)
    ):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    return {"access_token": make_token(user["id"]), "token_type": "bearer", "user": user_payload(user["id"])}


@app.get("/api/v1/auth/me")
def me(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    return user


@app.get("/health")
def health() -> dict[str, str]:
    with connect() as db:
        db.execute("SELECT 1").fetchone()
    return {"status": "ok", "database": "postgres" if is_postgres() else "sqlite"}


def validate_upload(filename: str, content_type: str, payload: bytes) -> str:
    suffix = Path(filename).suffix.lower()
    if content_type not in SUPPORTED_TYPES and suffix not in SUPPORTED_SUFFIXES:
        raise HTTPException(status_code=415, detail="Unsupported file type. Use PDF, DOCX, PNG, or JPG.")
    if not payload:
        raise HTTPException(status_code=400, detail="The uploaded file is empty")
    if len(payload) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"Maximum file size is {MAX_UPLOAD_BYTES // (1024 * 1024)} MB")
    magic_ok = {
        ".pdf": payload.startswith(b"%PDF"),
        ".png": payload.startswith(b"\x89PNG\r\n\x1a\n"),
        ".jpg": payload.startswith(b"\xff\xd8"),
        ".jpeg": payload.startswith(b"\xff\xd8"),
        ".docx": payload.startswith(b"PK"),
    }
    if suffix in magic_ok and not magic_ok[suffix]:
        raise HTTPException(status_code=415, detail="The file contents do not match the declared file type")
    return suffix


@app.post("/api/v1/documents", status_code=202)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    user: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    filename = Path(file.filename or "untitled").name
    content_type = file.content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
    payload = await file.read()
    suffix = validate_upload(filename, content_type, payload)
    document_id = str(uuid.uuid4())
    storage_key = f"{user['organization_id']}/{document_id}{suffix}"
    store_object(storage_key, payload, UPLOAD_DIR)
    timestamp = now()
    with DB_LOCK, connect() as db:
        db.execute(
            "INSERT INTO documents (id,organization_id,name,content_type,size,status,stage,progress,created_at,updated_at,storage_key) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (document_id, user["organization_id"], filename, content_type, len(payload), "queued", "Queued", 0, timestamp, timestamp, storage_key),
        )
        for stage in PIPELINE_STAGES:
            db.execute(
                "INSERT INTO processing_stages (id,document_id,stage,status) VALUES (?,?,?,'pending')",
                (str(uuid.uuid4()), document_id, stage),
            )
    record_audit(document_id, "upload", user)
    if PROCESSING_MODE == "local":
        background_tasks.add_task(process_document, document_id, user["organization_id"], user)
    return {"id": document_id, "status": "queued", "message": "Document accepted for analysis."}


@app.get("/api/v1/documents")
def list_documents(user: dict[str, Any] = Depends(current_user)) -> list[dict[str, Any]]:
    with connect() as db:
        rows = fetchall(db.execute(
            "SELECT * FROM documents WHERE organization_id=? ORDER BY created_at DESC", (user["organization_id"],)
        ))
    return [row_document(row) for row in rows]


@app.get("/api/v1/documents/{document_id}")
def get_document(document_id: str, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    return row_document(fetch_document(document_id, user["organization_id"]))


@app.get("/api/v1/documents/{document_id}/processing")
def processing_status(document_id: str, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    document = fetch_document(document_id, user["organization_id"])
    with connect() as db:
        stages = fetchall(db.execute(
            "SELECT stage,status,progress,error,started_at,completed_at FROM processing_stages WHERE document_id=?",
            (document_id,),
        ))
        order = {name: index for index, name in enumerate(PIPELINE_STAGES)}
        stages.sort(key=lambda item: order.get(item["stage"], 999))
    return {"id": document["id"], "status": document["status"], "stage": document["stage"], "progress": document["progress"], "stages": stages}


@app.get("/api/v1/documents/{document_id}/report")
def document_report(document_id: str, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    document = fetch_document(document_id, user["organization_id"])
    if document["status"] != "completed":
        raise HTTPException(status_code=409, detail="Report is not ready yet")
    return filter_report_features(json.loads(document["report_json"])) if document["report_json"] else {}


@app.patch("/api/v1/action-items/{action_item_id}")
def update_action_item(
    action_item_id: str,
    request: ActionItemUpdate,
    user: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    with DB_LOCK, connect() as db:
        item = fetchone(db.execute(
            "SELECT a.*, d.organization_id, d.report_json FROM action_items a JOIN documents d ON d.id=a.document_id "
            "WHERE a.id=? AND d.organization_id=?",
            (action_item_id, user["organization_id"]),
        ))
        if not item:
            raise HTTPException(status_code=404, detail="Action item not found")
        db.execute("UPDATE action_items SET status=? WHERE id=?", (request.status, action_item_id))
        if item.get("report_json"):
            try:
                report = json.loads(item["report_json"])
                for action in report.get("action_plan", []):
                    if action.get("id") == action_item_id:
                        action["status"] = request.status
                db.execute("UPDATE documents SET report_json=?, updated_at=? WHERE id=?", (json.dumps(report), now(), item["document_id"]))
            except json.JSONDecodeError:
                pass
    record_audit(item["document_id"], f"action_item_{request.status}", user)
    return {
        "id": action_item_id,
        "document_id": item["document_id"],
        "title": item["title"],
        "detail": item["detail"],
        "priority": item["priority"],
        "due_date": item["due_date"],
        "status": request.status,
    }


@app.get("/api/v1/documents/{document_id}/report/download")
def download_report(
    document_id: str,
    format: str = Query(default="pdf", pattern="^(pdf|json)$"),
    target_language: str | None = Query(default=None, max_length=64),
    user: dict[str, Any] = Depends(current_user),
) -> Response:
    document = fetch_document(document_id, user["organization_id"])
    if document["status"] != "completed" or not document["report_json"]:
        raise HTTPException(status_code=409, detail="Report is not ready yet")
    try:
        report = filter_report_features(json.loads(document["report_json"]))
    except json.JSONDecodeError as error:
        raise HTTPException(status_code=503, detail="Document report is unavailable") from error

    if target_language and FEATURE_TRANSLATION:
        try:
            report = translate_report(report, target_language)
        except RuntimeError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error

    stem = Path(document["name"]).stem
    record_audit(document_id, "report_download", user)

    if format == "json":
        return Response(
            content=json.dumps(report, ensure_ascii=False, indent=2),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{stem}-report.json"'},
        )

    try:
        pdf_bytes = render_report_pdf(document["name"], report)
    except Exception as error:
        raise HTTPException(status_code=503, detail=f"PDF generation failed: {error}") from error

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{stem}-report.pdf"'},
    )


def _parse_embedding(raw: str | None) -> list[float]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


@app.post("/api/v1/chat/sessions")
def create_chat_session(request: CreateSessionRequest, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    document = fetch_document(request.document_id, user["organization_id"])
    if document["status"] != "completed":
        raise HTTPException(status_code=409, detail="Chat is available after analysis completes")
    with DB_LOCK, connect() as db:
        session_id = _create_chat_session(db, user["id"], request.document_id)
    session = _fetch_chat_session(session_id, user["id"])
    return {
        "id": session["id"],
        "document_id": session["document_id"],
        "document_name": session["document_name"],
        "title": session["title"],
        "preview": None,
        "created_at": session["created_at"],
        "updated_at": session["updated_at"],
    }


@app.get("/api/v1/chat/sessions")
def list_chat_sessions(user: dict[str, Any] = Depends(current_user)) -> list[dict[str, Any]]:
    with connect() as db:
        rows = fetchall(db.execute(
            "SELECT s.id, s.document_id, s.title, s.created_at, s.updated_at, d.name AS document_name, "
            "(SELECT content FROM chat_messages WHERE session_id=s.id ORDER BY created_at DESC LIMIT 1) AS preview "
            "FROM chat_sessions s JOIN documents d ON d.id=s.document_id "
            "WHERE s.user_id=? ORDER BY s.updated_at DESC",
            (user["id"],),
        ))
    return [
        {
            "id": row["id"],
            "document_id": row["document_id"],
            "document_name": row["document_name"],
            "title": row["title"],
            "preview": row.get("preview"),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
        for row in rows
    ]


@app.get("/api/v1/chat/sessions/{session_id}/messages")
def list_chat_session_messages(session_id: str, user: dict[str, Any] = Depends(current_user)) -> list[dict[str, Any]]:
    _fetch_chat_session(session_id, user["id"])
    with connect() as db:
        rows = fetchall(db.execute(
            "SELECT id, role, content, citations_json, created_at FROM chat_messages "
            "WHERE session_id=? ORDER BY created_at ASC",
            (session_id,),
        ))
    messages: list[dict[str, Any]] = []
    for row in rows:
        citations = None
        if row.get("citations_json"):
            try:
                citations = json.loads(row["citations_json"])
            except json.JSONDecodeError:
                citations = None
        messages.append(
            {
                "id": row["id"],
                "role": row["role"],
                "content": row["content"],
                "citations": citations,
                "created_at": row["created_at"],
            }
        )
    return messages


@app.delete("/api/v1/chat/sessions/{session_id}", status_code=204)
def delete_chat_session(session_id: str, user: dict[str, Any] = Depends(current_user)) -> Response:
    _fetch_chat_session(session_id, user["id"])
    with DB_LOCK, connect() as db:
        db.execute("DELETE FROM chat_sessions WHERE id=? AND user_id=?", (session_id, user["id"]))
    return Response(status_code=204)


@app.post("/api/v1/documents/{document_id}/chat")
def chat(document_id: str, request: ChatRequest, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    document = fetch_document(document_id, user["organization_id"])
    if document["status"] != "completed":
        raise HTTPException(status_code=409, detail="Chat is available after analysis completes")
    try:
        report = filter_report_features(json.loads(document["report_json"])) if document["report_json"] else {}
    except json.JSONDecodeError:
        raise HTTPException(status_code=503, detail="Document report is unavailable")
    with connect() as db:
        chunk_rows = fetchall(db.execute(
            "SELECT content,page,ordinal,embedding_json FROM document_chunks WHERE document_id=? ORDER BY ordinal",
            (document_id,),
        ))
    chunks = [
        {
            "content": row["content"],
            "page": row["page"],
            "ordinal": row["ordinal"],
            "embedding": _parse_embedding(row.get("embedding_json")),
        }
        for row in chunk_rows
    ]
    with DB_LOCK, connect() as db:
        session_id = _resolve_chat_session(db, user, document_id, request.session_id)
        history_rows = _load_session_history(db, session_id)
        history = [{"role": row["role"], "content": row["content"]} for row in history_rows]
    retrieval_query = request.message
    last_user = next((row for row in reversed(history_rows) if row["role"] == "user"), None)
    if last_user:
        retrieval_query = f"{last_user['content']} {request.message}"
    retrieved = retrieve_chunks(retrieval_query, chunks)
    try:
        response = answer_question(
            document["name"],
            report,
            request.message,
            retrieved,
            target_language=request.target_language,
            history=history,
        )
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error))
    except Exception as error:
        raise HTTPException(status_code=503, detail=f"Chat failed: {error}")
    timestamp = now()
    with DB_LOCK, connect() as db:
        db.execute(
            "INSERT INTO chat_messages (id,document_id,user_id,role,content,citations_json,created_at,session_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), document_id, user["id"], "user", request.message, None, timestamp, session_id),
        )
        db.execute(
            "INSERT INTO chat_messages (id,document_id,user_id,role,content,citations_json,created_at,session_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                str(uuid.uuid4()),
                document_id,
                user["id"],
                "assistant",
                response["answer"],
                json.dumps(response.get("citations", [])),
                timestamp,
                session_id,
            ),
        )
        session_row = fetchone(db.execute("SELECT title FROM chat_sessions WHERE id=?", (session_id,)))
        if session_row and session_row["title"] == "New chat":
            db.execute(
                "UPDATE chat_sessions SET title=?, updated_at=? WHERE id=?",
                (_session_title(request.message), timestamp, session_id),
            )
        else:
            db.execute("UPDATE chat_sessions SET updated_at=? WHERE id=?", (timestamp, session_id))
    record_audit(document_id, "chat", user)
    return {
        **response,
        "session_id": session_id,
        "disclaimer": "AI-generated decision support. Consult a qualified professional for advice.",
    }


@app.get("/api/v1/deadlines")
def list_deadlines(user: dict[str, Any] = Depends(current_user)) -> list[dict[str, Any]]:
    with connect() as db:
        return fetchall(db.execute(
            "SELECT d.*, doc.name AS document_name FROM deadlines d JOIN documents doc ON doc.id=d.document_id WHERE doc.organization_id=? ORDER BY d.due_date ASC",
            (user["organization_id"],),
        ))


@app.get("/api/v1/analytics/overview")
def analytics(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    org = user["organization_id"]
    with connect() as db:
        total = fetchone(db.execute("SELECT COUNT(*) AS count FROM documents WHERE organization_id=?", (org,)))["count"]
        high = fetchone(db.execute("SELECT COUNT(*) AS count FROM documents WHERE organization_id=? AND risk_level='high'", (org,)))["count"]
        medium = fetchone(db.execute("SELECT COUNT(*) AS count FROM documents WHERE organization_id=? AND risk_level='medium'", (org,)))["count"]
        low = fetchone(db.execute("SELECT COUNT(*) AS count FROM documents WHERE organization_id=? AND risk_level='low'", (org,)))["count"]
        average = fetchone(db.execute(
            "SELECT COALESCE(AVG(risk_score), 0) AS average FROM documents WHERE organization_id=? AND risk_score IS NOT NULL", (org,)
        ))["average"]
        if is_postgres():
            deadlines = fetchone(db.execute(
                "SELECT COUNT(*) AS count FROM deadlines d JOIN documents doc ON doc.id=d.document_id WHERE doc.organization_id=? AND d.due_date >= CURRENT_DATE",
                (org,),
            ))["count"]
            categories = fetchall(db.execute(
                "SELECT COALESCE(classification, 'Unclassified') AS category, COUNT(*) AS count FROM documents WHERE organization_id=? GROUP BY classification ORDER BY count DESC",
                (org,),
            ))
            monthly = fetchall(db.execute(
                "SELECT substr(created_at, 1, 7) AS month, COUNT(*) AS count FROM documents WHERE organization_id=? GROUP BY 1 ORDER BY 1 DESC LIMIT 6",
                (org,),
            ))
        else:
            deadlines = fetchone(db.execute(
                "SELECT COUNT(*) AS count FROM deadlines d JOIN documents doc ON doc.id=d.document_id WHERE doc.organization_id=? AND d.due_date >= date('now')",
                (org,),
            ))["count"]
            categories = fetchall(db.execute(
                "SELECT COALESCE(classification, 'Unclassified') AS category, COUNT(*) AS count FROM documents WHERE organization_id=? GROUP BY classification ORDER BY count DESC",
                (org,),
            ))
            monthly = fetchall(db.execute(
                "SELECT substr(created_at, 1, 7) AS month, COUNT(*) AS count FROM documents WHERE organization_id=? GROUP BY 1 ORDER BY 1 DESC LIMIT 6",
                (org,),
            ))
        fraud_docs = 0
        if FEATURE_FRAUD:
            fraud_docs = fetchone(db.execute(
                "SELECT COUNT(DISTINCT f.document_id) AS count FROM document_fraud_indicators f "
                "JOIN documents doc ON doc.id=f.document_id WHERE doc.organization_id=? AND f.severity='high'",
                (org,),
            ))["count"]
    protection = max(0, 100 - round(average))
    return {
        "documents_uploaded": total,
        "high_risk_documents": high,
        "medium_risk_documents": medium,
        "low_risk_documents": low,
        "average_risk_score": round(average),
        "protection_score": protection,
        "upcoming_deadlines": deadlines,
        "fraud_flagged_documents": fraud_docs,
        "categories": categories,
        "monthly_uploads": list(reversed(monthly)),
    }


@app.post("/api/v1/deadlines/{deadline_id}/reminders")
def create_reminder(
    deadline_id: str,
    request: ReminderRequest,
    user: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    with DB_LOCK, connect() as db:
        deadline = fetchone(db.execute(
            "SELECT d.* FROM deadlines d JOIN documents doc ON doc.id=d.document_id WHERE d.id=? AND doc.organization_id=?",
            (deadline_id, user["organization_id"]),
        ))
        if not deadline:
            raise HTTPException(status_code=404, detail="Deadline not found")
        try:
            scheduled_for = _scheduled_time(deadline["due_date"], request.days_before)
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail="Deadline has an invalid date")
        existing = fetchone(db.execute(
            "SELECT * FROM reminders WHERE deadline_id=? AND user_id=? AND channel=? AND days_before=? "
            "AND status IN ('scheduled','processing','delivered') ORDER BY created_at DESC LIMIT 1",
            (deadline_id, user["id"], request.channel, request.days_before),
        ))
        if existing:
            return existing
        reminder = {
            "id": str(uuid.uuid4()),
            "deadline_id": deadline_id,
            "channel": request.channel,
            "days_before": request.days_before,
            "status": "scheduled",
            "created_at": now(),
            "delivered_at": None,
            "user_id": user["id"],
            "scheduled_for": scheduled_for,
            "error": None,
        }
        db.execute(
            "INSERT INTO reminders (id,deadline_id,channel,days_before,status,created_at,delivered_at,user_id,scheduled_for,error) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            tuple(reminder.values()),
        )
    record_audit(deadline["document_id"], "reminder_created", user)
    return reminder


@app.get("/api/v1/notifications")
def list_notifications(user: dict[str, Any] = Depends(current_user)) -> list[dict[str, Any]]:
    with connect() as db:
        return fetchall(db.execute(
            "SELECT * FROM notifications WHERE organization_id=? AND (user_id IS NULL OR user_id=?) ORDER BY created_at DESC LIMIT 50",
            (user["organization_id"], user["id"]),
        ))


@app.delete("/api/v1/documents/{document_id}", status_code=204, response_class=Response)
def delete_document(document_id: str, user: dict[str, Any] = Depends(require_role("Owner", "Admin", "Member"))) -> Response:
    document = fetch_document(document_id, user["organization_id"])
    storage_key = document["storage_key"]
    with DB_LOCK, connect() as db:
        db.execute("DELETE FROM documents WHERE id=? AND organization_id=?", (document_id, user["organization_id"]))
    delete_object(storage_key, UPLOAD_DIR)
    record_audit(document_id, "delete", user)
    return Response(status_code=204)


@app.post("/api/v1/documents/{document_id}/retry", status_code=202)
def retry_document(document_id: str, background_tasks: BackgroundTasks, user: dict[str, Any] = Depends(current_user)) -> dict[str, str]:
    document = fetch_document(document_id, user["organization_id"])
    if document["status"] not in {"failed", "completed"}:
        raise HTTPException(status_code=409, detail="Document is already processing")
    with DB_LOCK, connect() as db:
        db.execute("UPDATE documents SET status='queued', stage='Queued', progress=0, updated_at=? WHERE id=?", (now(), document_id))
        db.execute("UPDATE processing_stages SET status='pending', progress=0, error=NULL, started_at=NULL, completed_at=NULL WHERE document_id=?", (document_id,))
    if PROCESSING_MODE == "local":
        background_tasks.add_task(process_document, document_id, user["organization_id"], user)
    record_audit(document_id, "retry", user)
    return {"id": document_id, "status": "queued"}


@app.post("/api/v1/comparisons")
def compare_documents(request: ComparisonRequest, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    first = fetch_document(request.document_a_id, user["organization_id"])
    second = fetch_document(request.document_b_id, user["organization_id"])
    if first["status"] != "completed" or second["status"] != "completed":
        raise HTTPException(status_code=409, detail="Both documents must finish analysis before comparison")
    first_report = filter_report_features(json.loads(first["report_json"] or "{}"))
    second_report = filter_report_features(json.loads(second["report_json"] or "{}"))
    def normalized(value: Any) -> str:
        return " ".join("".join(character.lower() if character.isalnum() else " " for character in str(value or "")).split())

    def clause_matches(left: list[dict[str, Any]], right: list[dict[str, Any]]) -> list[tuple[dict[str, Any], dict[str, Any], float]]:
        remaining = set(range(len(right)))
        matches: list[tuple[dict[str, Any], dict[str, Any], float]] = []
        for left_clause in left:
            title = normalized(left_clause.get("title"))
            candidates = [index for index in remaining if normalized(right[index].get("title")) == title and title]
            if not candidates:
                candidates = [
                    index for index in remaining
                    if left_clause.get("category") and left_clause.get("category") == right[index].get("category")
                ]
            if not candidates:
                continue
            index = max(candidates, key=lambda item: difflib.SequenceMatcher(None, normalized(left_clause.get("body")), normalized(right[item].get("body"))).ratio())
            remaining.remove(index)
            score = difflib.SequenceMatcher(None, normalized(left_clause.get("body")), normalized(right[index].get("body"))).ratio()
            matches.append((left_clause, right[index], score))
        return matches

    first_risks = {normalized(risk.get("title")): risk.get("title") for risk in first_report.get("risks", []) if risk.get("title")}
    second_risks = {normalized(risk.get("title")): risk.get("title") for risk in second_report.get("risks", []) if risk.get("title")}
    first_deadlines = {normalized(deadline.get("title")): deadline for deadline in first_report.get("deadlines", []) if deadline.get("title")}
    second_deadlines = {normalized(deadline.get("title")): deadline for deadline in second_report.get("deadlines", []) if deadline.get("title")}
    first_clauses_list = [clause for clause in first_report.get("clauses", []) if clause.get("title")]
    second_clauses_list = [clause for clause in second_report.get("clauses", []) if clause.get("title")]
    matches = clause_matches(first_clauses_list, second_clauses_list)
    matched_left = {id(left) for left, _, _ in matches}
    matched_right = {id(right) for _, right, _ in matches}
    modified = []
    for left, right, match_score in matches:
        if (normalized(left.get("body")) != normalized(right.get("body")) or left.get("severity") != right.get("severity")):
            modified.append({
                "title": left.get("title") or right.get("title"),
                "document_b_title": right.get("title"),
                "document_a_severity": left.get("severity"),
                "document_b_severity": right.get("severity"),
                "severity_changed": left.get("severity") != right.get("severity"),
                "match_score": round(match_score * 100),
                "document_a_excerpt": (left.get("body") or "")[:240],
                "document_b_excerpt": (right.get("body") or "")[:240],
            })
    added_clause_items = [clause.get("title") for clause in second_clauses_list if id(clause) not in matched_right]
    removed_clause_items = [clause.get("title") for clause in first_clauses_list if id(clause) not in matched_left]
    deadline_changes = []
    for title in sorted(set(first_deadlines) & set(second_deadlines)):
        left, right = first_deadlines[title], second_deadlines[title]
        if left.get("date") != right.get("date"):
            deadline_changes.append({"title": left.get("title"), "document_a_date": left.get("date"), "document_b_date": right.get("date")})
    first_text = json.dumps(first_report, sort_keys=True)
    second_text = json.dumps(second_report, sort_keys=True)
    return {
        "document_a": first["name"],
        "document_b": second["name"],
        "similarity_score": round(difflib.SequenceMatcher(None, first_text, second_text).ratio() * 100),
        "added_risks": sorted(second_risks[key] for key in set(second_risks) - set(first_risks)),
        "removed_risks": sorted(first_risks[key] for key in set(first_risks) - set(second_risks)),
        "added_deadlines": sorted(second_deadlines[key].get("title", key) for key in set(second_deadlines) - set(first_deadlines)),
        "removed_deadlines": sorted(first_deadlines[key].get("title", key) for key in set(first_deadlines) - set(second_deadlines)),
        "deadline_changes": deadline_changes,
        "added_clauses": sorted(added_clause_items),
        "removed_clauses": sorted(removed_clause_items),
        "modified_clauses": modified,
        "risk_score_delta": int(second_report.get("risk_score", 0)) - int(first_report.get("risk_score", 0)),
        "risk_level_changed": first_report.get("risk_level") != second_report.get("risk_level"),
        "disclaimer": "Comparison is an AI-assisted review and should not replace professional advice.",
    }


@app.get("/api/v1/audit")
def audit_logs(user: dict[str, Any] = Depends(require_role("Owner", "Admin"))) -> list[dict[str, Any]]:
    with connect() as db:
        return fetchall(db.execute(
            "SELECT id,user_id,document_id,action,created_at FROM audit_logs WHERE organization_id=? ORDER BY created_at DESC LIMIT 100",
            (user["organization_id"],),
        ))


@app.get("/api/v1/features")
def features() -> dict[str, Any]:
    return {
        "voice": FEATURE_VOICE,
        "translation": FEATURE_TRANSLATION,
        "fraud": FEATURE_FRAUD,
        "external_calendar": FEATURE_EXTERNAL_CALENDAR and calendar_sync.is_configured(),
        "demo_auth": ENABLE_DEMO_AUTH,
        "pipeline_stages": list(PIPELINE_STAGES),
        "supported_languages": list(SUPPORTED_LANGUAGES),
        "language_options": [
            {"label": label, "code": LANGUAGE_CODES.get(label, label[:2].lower())}
            for label in SUPPORTED_LANGUAGES
        ],
    }


class CalendarAutoSyncRequest(BaseModel):
    enabled: bool


@app.get("/api/v1/integrations/calendar")
def calendar_status(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    return {
        "enabled": FEATURE_EXTERNAL_CALENDAR and calendar_sync.is_configured(),
        "integrations": calendar_sync.list_integrations(user["organization_id"], user["id"]),
    }


@app.get("/api/v1/integrations/calendar/google/authorize")
def calendar_google_authorize(user: dict[str, Any] = Depends(current_user)) -> dict[str, str]:
    if not FEATURE_EXTERNAL_CALENDAR or not GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=404, detail="Google Calendar integration is not configured")
    state = calendar_sync.create_oauth_state(user["organization_id"], user["id"], "google")
    return {"authorization_url": calendar_sync.google_authorize_url(state)}


@app.get("/api/v1/integrations/calendar/google/callback")
def calendar_google_callback(code: str = Query(...), state: str = Query(...)) -> RedirectResponse:
    try:
        payload = calendar_sync.consume_oauth_state(state, "google")
        if not payload:
            raise ValueError("Invalid or expired OAuth state")
        calendar_sync.complete_google_oauth(code, payload["organization_id"], payload["user_id"])
        return RedirectResponse(calendar_sync.settings_redirect("connected", "google"))
    except Exception:
        return RedirectResponse(calendar_sync.settings_redirect("failed", "google"))


@app.get("/api/v1/integrations/calendar/outlook/authorize")
def calendar_outlook_authorize(user: dict[str, Any] = Depends(current_user)) -> dict[str, str]:
    if not FEATURE_EXTERNAL_CALENDAR or not MICROSOFT_CLIENT_ID:
        raise HTTPException(status_code=404, detail="Outlook Calendar integration is not configured")
    state = calendar_sync.create_oauth_state(user["organization_id"], user["id"], "outlook")
    return {"authorization_url": calendar_sync.outlook_authorize_url(state)}


@app.get("/api/v1/integrations/calendar/outlook/callback")
def calendar_outlook_callback(code: str = Query(...), state: str = Query(...)) -> RedirectResponse:
    try:
        payload = calendar_sync.consume_oauth_state(state, "outlook")
        if not payload:
            raise ValueError("Invalid or expired OAuth state")
        calendar_sync.complete_outlook_oauth(code, payload["organization_id"], payload["user_id"])
        return RedirectResponse(calendar_sync.settings_redirect("connected", "outlook"))
    except Exception:
        return RedirectResponse(calendar_sync.settings_redirect("failed", "outlook"))


@app.delete("/api/v1/integrations/calendar/{provider}")
def calendar_disconnect(provider: str, user: dict[str, Any] = Depends(current_user)) -> dict[str, str]:
    if provider not in {"google", "outlook"}:
        raise HTTPException(status_code=400, detail="Unsupported calendar provider")
    calendar_sync.disconnect(user["organization_id"], user["id"], provider)
    record_audit(None, f"calendar_disconnected_{provider}", user)
    return {"status": "disconnected", "provider": provider}


@app.post("/api/v1/integrations/calendar/sync")
def calendar_sync_all(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    result = calendar_sync.sync_organization_deadlines(user["organization_id"], user["id"])
    record_audit(None, "calendar_sync", user)
    return result


@app.patch("/api/v1/integrations/calendar/{integration_id}/auto-sync")
def calendar_auto_sync(integration_id: str, request: CalendarAutoSyncRequest, user: dict[str, Any] = Depends(current_user)) -> dict[str, str]:
    calendar_sync.set_auto_sync(integration_id, user["organization_id"], user["id"], request.enabled)
    return {"status": "updated", "auto_sync": "on" if request.enabled else "off"}


@app.post("/api/v1/translate")
def translate(request: TranslateRequest, user: dict[str, Any] = Depends(current_user)) -> dict[str, str]:
    if not FEATURE_TRANSLATION:
        raise HTTPException(status_code=404, detail="Translation is disabled")
    try:
        return {"translated_text": translate_text(request.text, request.target_language), "target_language": request.target_language}
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error))


@app.post("/api/v1/documents/{document_id}/translate")
def translate_document_report(
    document_id: str,
    request: ReportTranslationRequest,
    user: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    if not FEATURE_TRANSLATION:
        raise HTTPException(status_code=404, detail="Translation is disabled")
    document = fetch_document(document_id, user["organization_id"])
    if document["status"] != "completed" or not document["report_json"]:
        raise HTTPException(status_code=409, detail="Report is not ready yet")
    try:
        report = filter_report_features(json.loads(document["report_json"]))
        translated = translate_report(report, request.target_language)
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error))
    except json.JSONDecodeError as error:
        raise HTTPException(status_code=503, detail="Document report is unavailable") from error
    record_audit(document_id, "report_translated", user)
    return {"target_language": request.target_language, "report": translated}


@app.post("/api/v1/voice-summary")
def voice_summary(request: VoiceRequest, user: dict[str, Any] = Depends(current_user)) -> Response:
    if not FEATURE_VOICE:
        raise HTTPException(status_code=404, detail="Voice summary is disabled")
    try:
        spoken_text, spoken_language = speech_text_for_language(request.text, request.target_language)
        audio = synthesize_speech(spoken_text, request.target_language)
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error))
    except Exception as error:
        raise HTTPException(status_code=503, detail=f"Voice synthesis unavailable: {error}")
    headers = {"X-Voice-Language": spoken_language or "English"}
    return Response(content=audio, media_type="audio/mpeg", headers=headers)


def process_document(document_id: str, organization_id: str, user: dict[str, Any]) -> None:
    with connect() as db:
        row = fetchone(db.execute("SELECT * FROM documents WHERE id=? AND organization_id=?", (document_id, organization_id)))
    if not row:
        return

    def on_stage(stage: str, progress: int) -> None:
        if stage == "Complete":
            return
        with DB_LOCK, connect() as db:
            db.execute(
                "UPDATE documents SET status='processing',stage=?,progress=?,updated_at=? WHERE id=?",
                (stage, progress, now(), document_id),
            )
            running = fetchone(db.execute(
                "SELECT stage FROM processing_stages WHERE document_id=? AND status='running'", (document_id,)
            ))
            if running and running["stage"] != stage:
                db.execute(
                    "UPDATE processing_stages SET status='completed',progress=?,completed_at=? WHERE document_id=? AND stage=?",
                    (progress, now(), document_id, running["stage"]),
                )
            db.execute(
                "UPDATE processing_stages SET status='running',progress=?,started_at=COALESCE(started_at, ?) WHERE document_id=? AND stage=?",
                (progress, now(), document_id, stage),
            )
            # Mark prior pending stages completed when advancing
            for prior in PIPELINE_STAGES:
                if prior == stage:
                    break
                db.execute(
                    "UPDATE processing_stages SET status='completed',progress=100,completed_at=COALESCE(completed_at, ?) WHERE document_id=? AND stage=? AND status!='completed'",
                    (now(), document_id, prior),
                )

    try:
        run_pipeline(
            document_id=document_id,
            organization_id=organization_id,
            storage_key=row["storage_key"],
            filename=row["name"],
            upload_dir=UPLOAD_DIR,
            on_stage=on_stage,
        )
        try:
            calendar_sync.sync_document_deadlines(document_id, organization_id)
        except Exception:
            pass
        with DB_LOCK, connect() as db:
            db.execute(
                "UPDATE processing_stages SET status='completed',progress=100,completed_at=COALESCE(completed_at, ?) WHERE document_id=?",
                (now(), document_id),
            )
        record_audit(document_id, "analysis_completed", user)
    except Exception as error:
        with DB_LOCK, connect() as db:
            db.execute("UPDATE documents SET status='failed',stage='Failed',updated_at=? WHERE id=?", (now(), document_id))
            db.execute(
                "UPDATE processing_stages SET status='failed',error=? WHERE document_id=? AND status='running'",
                (str(error)[:500], document_id),
            )
        record_audit(document_id, "analysis_failed", user)
