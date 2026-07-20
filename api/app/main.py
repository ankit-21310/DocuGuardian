from __future__ import annotations

import base64
import difflib
import hashlib
import hmac
import json
import mimetypes
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from .ai import answer_question, retrieve_chunks, synthesize_speech, translate_text
from .config import (
    CORS_ORIGINS,
    ENABLE_DEMO_AUTH,
    ENVIRONMENT,
    FEATURE_TRANSLATION,
    FEATURE_VOICE,
    MAX_UPLOAD_BYTES,
    PIPELINE_STAGES,
    PROCESSING_MODE,
    SUPPORTED_SUFFIXES,
    SUPPORTED_TYPES,
    UPLOAD_DIR,
    resolve_auth_secret,
)
from .db import DB_LOCK, IntegrityError, SCHEMA_SQL, connect, fetchall, fetchone, is_postgres
from .notifications import deliver_reminder
from .pipeline_runner import run_pipeline
from .storage import delete_object, store_object


AUTH_SECRET = resolve_auth_secret()
ROLES = {"Owner", "Admin", "Member", "Viewer"}
BEARER = HTTPBearer(auto_error=False)

app = FastAPI(title="DocuGuardian API", version="0.3.0", openapi_url="/api/v1/openapi.json")
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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


@app.on_event("startup")
def startup() -> None:
    init_db()


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
    item["report"] = json.loads(report_json) if report_json else None
    return item


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


class ReminderRequest(BaseModel):
    channel: str = Field(default="in_app", pattern="^(in_app|email)$")
    days_before: int = Field(default=7, ge=0, le=365)


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


class VoiceRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


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
    return json.loads(document["report_json"]) if document["report_json"] else {}


@app.get("/api/v1/documents/{document_id}/report/download")
def download_report(document_id: str, user: dict[str, Any] = Depends(current_user)) -> Response:
    document = fetch_document(document_id, user["organization_id"])
    if document["status"] != "completed" or not document["report_json"]:
        raise HTTPException(status_code=409, detail="Report is not ready yet")
    record_audit(document_id, "report_download", user)
    return Response(
        content=document["report_json"],
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{Path(document["name"]).stem}-report.json"'},
    )


@app.post("/api/v1/documents/{document_id}/chat")
def chat(document_id: str, request: ChatRequest, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    document = fetch_document(document_id, user["organization_id"])
    if document["status"] != "completed":
        raise HTTPException(status_code=409, detail="Chat is available after analysis completes")
    report = json.loads(document["report_json"]) if document["report_json"] else {}
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
            "embedding": json.loads(row["embedding_json"]) if row.get("embedding_json") else [],
        }
        for row in chunk_rows
    ]
    retrieved = retrieve_chunks(request.message, chunks)
    try:
        response = answer_question(document["name"], report, request.message, retrieved)
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error))
    with DB_LOCK, connect() as db:
        db.execute(
            "INSERT INTO chat_messages VALUES (?, ?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), document_id, user["id"], "user", request.message, None, now()),
        )
        db.execute(
            "INSERT INTO chat_messages VALUES (?, ?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), document_id, user["id"], "assistant", response["answer"], json.dumps(response.get("citations", [])), now()),
        )
    record_audit(document_id, "chat", user)
    return {**response, "disclaimer": "AI-generated decision support. Consult a qualified professional for advice."}


@app.get("/api/v1/deadlines")
def list_deadlines(user: dict[str, Any] = Depends(current_user)) -> list[dict[str, Any]]:
    with connect() as db:
        return fetchall(db.execute(
            "SELECT d.* FROM deadlines d JOIN documents doc ON doc.id=d.document_id WHERE doc.organization_id=? ORDER BY d.due_date ASC",
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
    protection = max(0, 100 - round(average))
    return {
        "documents_uploaded": total,
        "high_risk_documents": high,
        "medium_risk_documents": medium,
        "low_risk_documents": low,
        "average_risk_score": round(average),
        "protection_score": protection,
        "upcoming_deadlines": deadlines,
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
        reminder = {
            "id": str(uuid.uuid4()),
            "deadline_id": deadline_id,
            "channel": request.channel,
            "days_before": request.days_before,
            "status": "scheduled",
            "created_at": now(),
            "delivered_at": None,
        }
        db.execute(
            "INSERT INTO reminders (id,deadline_id,channel,days_before,status,created_at,delivered_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            tuple(reminder.values()),
        )
    notification = deliver_reminder(
        organization_id=user["organization_id"],
        user_id=user["id"],
        deadline=deadline,
        reminder_id=reminder["id"],
        channel=request.channel,
    )
    reminder["status"] = "delivered"
    reminder["notification"] = notification
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
    first_report = json.loads(first["report_json"] or "{}")
    second_report = json.loads(second["report_json"] or "{}")
    first_risks = {risk.get("title", "").strip() for risk in first_report.get("risks", [])}
    second_risks = {risk.get("title", "").strip() for risk in second_report.get("risks", [])}
    first_deadlines = {deadline.get("title", "").strip() for deadline in first_report.get("deadlines", [])}
    second_deadlines = {deadline.get("title", "").strip() for deadline in second_report.get("deadlines", [])}
    first_clauses = {clause.get("title", "").strip(): clause for clause in first_report.get("clauses", []) if clause.get("title")}
    second_clauses = {clause.get("title", "").strip(): clause for clause in second_report.get("clauses", []) if clause.get("title")}
    modified = []
    for title in sorted(set(first_clauses) & set(second_clauses)):
        left, right = first_clauses[title], second_clauses[title]
        if (left.get("body") or "") != (right.get("body") or "") or left.get("severity") != right.get("severity"):
            modified.append({
                "title": title,
                "document_a_severity": left.get("severity"),
                "document_b_severity": right.get("severity"),
                "document_a_excerpt": (left.get("body") or "")[:240],
                "document_b_excerpt": (right.get("body") or "")[:240],
            })
    first_text = json.dumps(first_report, sort_keys=True)
    second_text = json.dumps(second_report, sort_keys=True)
    return {
        "document_a": first["name"],
        "document_b": second["name"],
        "similarity_score": round(difflib.SequenceMatcher(None, first_text, second_text).ratio() * 100),
        "added_risks": sorted(second_risks - first_risks),
        "removed_risks": sorted(first_risks - second_risks),
        "added_deadlines": sorted(second_deadlines - first_deadlines),
        "removed_deadlines": sorted(first_deadlines - second_deadlines),
        "added_clauses": sorted(set(second_clauses) - set(first_clauses)),
        "removed_clauses": sorted(set(first_clauses) - set(second_clauses)),
        "modified_clauses": modified,
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
        "demo_auth": ENABLE_DEMO_AUTH,
        "pipeline_stages": list(PIPELINE_STAGES),
    }


@app.post("/api/v1/translate")
def translate(request: TranslateRequest, user: dict[str, Any] = Depends(current_user)) -> dict[str, str]:
    if not FEATURE_TRANSLATION:
        raise HTTPException(status_code=404, detail="Translation is disabled")
    try:
        return {"translated_text": translate_text(request.text, request.target_language), "target_language": request.target_language}
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error))


@app.post("/api/v1/voice-summary")
def voice_summary(request: VoiceRequest, user: dict[str, Any] = Depends(current_user)) -> Response:
    if not FEATURE_VOICE:
        raise HTTPException(status_code=404, detail="Voice summary is disabled")
    try:
        audio = synthesize_speech(request.text)
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error))
    except Exception as error:
        raise HTTPException(status_code=503, detail=f"Voice synthesis unavailable: {error}")
    return Response(content=audio, media_type="audio/mpeg")


def process_document(document_id: str, organization_id: str, user: dict[str, Any]) -> None:
    with connect() as db:
        row = fetchone(db.execute("SELECT * FROM documents WHERE id=? AND organization_id=?", (document_id, organization_id)))
    if not row:
        return

    def on_stage(stage: str, progress: int) -> None:
        with DB_LOCK, connect() as db:
            db.execute(
                "UPDATE documents SET status='processing',stage=?,progress=?,updated_at=? WHERE id=?",
                (stage, progress, now(), document_id),
            )
            if stage == "Complete":
                return
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
