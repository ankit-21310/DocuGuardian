from __future__ import annotations

import base64
import difflib
import hashlib
import hmac
import json
import mimetypes
import os
import re
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from .ai import analyze_file, answer_question
from .storage import delete_object, materialize_object, store_object

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.getenv("DOCUGUARDIAN_DATA_DIR", ROOT / "data"))
UPLOAD_DIR = DATA_DIR / "uploads"
DB_PATH = DATA_DIR / "docuguardian.db"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
DB_LOCK = threading.Lock()
AUTH_SECRET = os.getenv("AUTH_SECRET", "local-development-secret-change-me").encode()
ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(25 * 1024 * 1024)))

SUPPORTED_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "image/png",
    "image/jpeg",
}
STAGES = (
    "OCR and parsing",
    "Classification",
    "Layout understanding",
    "Structured extraction",
    "Clause extraction",
    "Risk analysis",
    "Deadline detection",
    "Recommendations",
    "Embeddings",
    "Report generation",
)
ROLES = {"Owner", "Admin", "Member", "Viewer"}
BEARER = HTTPBearer(auto_error=False)

app = FastAPI(title="DocuGuardian API", version="0.2.0", openapi_url="/api/v1/openapi.json")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def password_hash(password: str) -> str:
    # PBKDF2 is available in the standard library and avoids storing raw passwords.
    return hashlib.pbkdf2_hmac("sha256", password.encode(), AUTH_SECRET, 120_000).hex()


def make_token(user_id: str) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {"sub": user_id, "exp": int((datetime.now(timezone.utc) + timedelta(hours=8)).timestamp())}

    def encode(value: dict[str, Any]) -> str:
        return base64.urlsafe_b64encode(json.dumps(value, separators=(",", ":")).encode()).decode().rstrip("=")

    encoded_header, encoded_payload = encode(header), encode(payload)
    message = f"{encoded_header}.{encoded_payload}"
    signature = hmac.new(AUTH_SECRET, message.encode(), hashlib.sha256).digest()
    encoded_signature = base64.urlsafe_b64encode(signature).decode().rstrip("=")
    return f"{message}.{encoded_signature}"


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
    with connect() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS organizations (
              id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS users (
              id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
              password_hash TEXT NOT NULL, role TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS memberships (
              user_id TEXT NOT NULL, organization_id TEXT NOT NULL, role TEXT NOT NULL,
              PRIMARY KEY (user_id, organization_id),
              FOREIGN KEY(user_id) REFERENCES users(id),
              FOREIGN KEY(organization_id) REFERENCES organizations(id)
            );
            CREATE TABLE IF NOT EXISTS documents (
              id TEXT PRIMARY KEY, organization_id TEXT NOT NULL, name TEXT NOT NULL,
              content_type TEXT NOT NULL, size INTEGER NOT NULL, status TEXT NOT NULL,
              stage TEXT, progress INTEGER NOT NULL DEFAULT 0, risk_level TEXT,
              risk_score INTEGER, classification TEXT, created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL, storage_key TEXT NOT NULL, report_json TEXT,
              FOREIGN KEY(organization_id) REFERENCES organizations(id)
            );
            CREATE TABLE IF NOT EXISTS processing_stages (
              id TEXT PRIMARY KEY, document_id TEXT NOT NULL, stage TEXT NOT NULL,
              status TEXT NOT NULL, progress INTEGER NOT NULL DEFAULT 0,
              error TEXT, started_at TEXT, completed_at TEXT,
              UNIQUE(document_id, stage), FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS deadlines (
              id TEXT PRIMARY KEY, document_id TEXT NOT NULL, title TEXT NOT NULL,
              due_date TEXT NOT NULL, priority TEXT NOT NULL, source TEXT NOT NULL,
              timezone TEXT NOT NULL DEFAULT 'UTC', FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS reminders (
              id TEXT PRIMARY KEY, deadline_id TEXT NOT NULL, channel TEXT NOT NULL,
              days_before INTEGER NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL,
              FOREIGN KEY(deadline_id) REFERENCES deadlines(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS audit_logs (
              id TEXT PRIMARY KEY, organization_id TEXT, user_id TEXT, document_id TEXT,
              action TEXT NOT NULL, created_at TEXT NOT NULL
            );
            """
        )
        # Upgrade databases created by the original demo without destroying local data.
        columns = {row[1] for row in db.execute("PRAGMA table_info(documents)").fetchall()}
        if "organization_id" not in columns:
            db.execute("ALTER TABLE documents ADD COLUMN organization_id TEXT NOT NULL DEFAULT 'demo-org'")
        audit_columns = {row[1] for row in db.execute("PRAGMA table_info(audit_logs)").fetchall()}
        if "organization_id" not in audit_columns:
            db.execute("ALTER TABLE audit_logs ADD COLUMN organization_id TEXT")
        if "user_id" not in audit_columns:
            db.execute("ALTER TABLE audit_logs ADD COLUMN user_id TEXT")
        deadline_columns = {row[1] for row in db.execute("PRAGMA table_info(deadlines)").fetchall()}
        if deadline_columns and "timezone" not in deadline_columns:
            db.execute("ALTER TABLE deadlines ADD COLUMN timezone TEXT NOT NULL DEFAULT 'UTC'")
        db.execute("INSERT OR IGNORE INTO organizations VALUES ('demo-org', 'Personal workspace', ?)", (now(),))
        db.execute(
            "INSERT OR IGNORE INTO users VALUES ('demo-user', 'alex@example.com', 'Alex Morgan', ?, 'Owner', ?)",
            (password_hash("demo-password"), now()),
        )
        db.execute("INSERT OR IGNORE INTO memberships VALUES ('demo-user', 'demo-org', 'Owner')")


@app.on_event("startup")
def startup() -> None:
    if ENVIRONMENT == "production" and AUTH_SECRET == b"local-development-secret-change-me":
        raise RuntimeError("AUTH_SECRET must be configured in production")
    init_db()


def user_payload(user_id: str) -> dict[str, Any]:
    with connect() as db:
        user = db.execute("SELECT id,email,name,role,created_at FROM users WHERE id=?", (user_id,)).fetchone()
        membership = db.execute(
            "SELECT organization_id,role FROM memberships WHERE user_id=? ORDER BY organization_id LIMIT 1", (user_id,)
        ).fetchone()
    if not user or not membership:
        raise HTTPException(status_code=401, detail="User or organization not found")
    return {**dict(user), "organization_id": membership["organization_id"], "role": membership["role"]}


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


def row_document(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    item.pop("storage_key", None)
    item.pop("organization_id", None)
    report_json = item.pop("report_json", None)
    item["report"] = json.loads(report_json) if report_json else None
    return item


def fetch_document(document_id: str, organization_id: str) -> sqlite3.Row:
    with connect() as db:
        row = db.execute(
            "SELECT * FROM documents WHERE id=? AND organization_id=?", (document_id, organization_id)
        ).fetchone()
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


@app.post("/api/v1/auth/demo")
def demo_login() -> dict[str, Any]:
    if ENVIRONMENT == "production":
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
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=409, detail="An account with that email already exists")
    return {"access_token": make_token(user_id), "token_type": "bearer", "user": user_payload(user_id)}


@app.post("/api/v1/auth/login")
def login(request: LoginRequest) -> dict[str, Any]:
    with connect() as db:
        user = db.execute("SELECT id,password_hash FROM users WHERE email=?", (request.email.lower(),)).fetchone()
    legacy_hash = hashlib.sha256(request.password.encode()).hexdigest()
    if not user or not (hmac.compare_digest(user["password_hash"], password_hash(request.password)) or hmac.compare_digest(user["password_hash"], legacy_hash)):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    return {"access_token": make_token(user["id"]), "token_type": "bearer", "user": user_payload(user["id"])}


@app.get("/api/v1/auth/me")
def me(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    return user


@app.get("/health")
def health() -> dict[str, str]:
    with connect() as db:
        db.execute("SELECT 1").fetchone()
    return {"status": "ok", "database": "ok"}


def validate_upload(filename: str, content_type: str, payload: bytes) -> str:
    suffix = Path(filename).suffix.lower()
    allowed_suffixes = {".pdf", ".docx", ".png", ".jpg", ".jpeg"}
    if content_type not in SUPPORTED_TYPES and suffix not in allowed_suffixes:
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
        for stage in STAGES:
            db.execute(
                "INSERT INTO processing_stages (id,document_id,stage,status) VALUES (?,?,?,'pending')",
                (str(uuid.uuid4()), document_id, stage),
            )
    record_audit(document_id, "upload", user)
    if os.getenv("PROCESSING_MODE", "local").lower() == "local":
        background_tasks.add_task(process_document, document_id, user["organization_id"], user)
    return {"id": document_id, "status": "queued", "message": "Document accepted for analysis."}


@app.get("/api/v1/documents")
def list_documents(user: dict[str, Any] = Depends(current_user)) -> list[dict[str, Any]]:
    with connect() as db:
        rows = db.execute(
            "SELECT * FROM documents WHERE organization_id=? ORDER BY created_at DESC", (user["organization_id"],)
        ).fetchall()
    return [row_document(row) for row in rows]


@app.get("/api/v1/documents/{document_id}")
def get_document(document_id: str, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    return row_document(fetch_document(document_id, user["organization_id"]))


@app.get("/api/v1/documents/{document_id}/processing")
def processing_status(document_id: str, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    document = fetch_document(document_id, user["organization_id"])
    with connect() as db:
        stages = [dict(row) for row in db.execute(
            "SELECT stage,status,progress,error,started_at,completed_at FROM processing_stages WHERE document_id=? ORDER BY rowid",
            (document_id,),
        ).fetchall()]
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
    try:
        response = answer_question(document["name"], report, request.message)
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error))
    record_audit(document_id, "chat", user)
    return {**response, "disclaimer": "AI-generated decision support. Consult a qualified professional for advice."}


@app.get("/api/v1/deadlines")
def list_deadlines(user: dict[str, Any] = Depends(current_user)) -> list[dict[str, Any]]:
    with connect() as db:
        return [dict(row) for row in db.execute(
            "SELECT d.* FROM deadlines d JOIN documents doc ON doc.id=d.document_id WHERE doc.organization_id=? ORDER BY d.due_date ASC",
            (user["organization_id"],),
        ).fetchall()]


@app.get("/api/v1/analytics/overview")
def analytics(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    with connect() as db:
        total = db.execute("SELECT COUNT(*) FROM documents WHERE organization_id=?", (user["organization_id"],)).fetchone()[0]
        high = db.execute("SELECT COUNT(*) FROM documents WHERE organization_id=? AND risk_level='high'", (user["organization_id"],)).fetchone()[0]
        medium = db.execute("SELECT COUNT(*) FROM documents WHERE organization_id=? AND risk_level='medium'", (user["organization_id"],)).fetchone()[0]
        low = db.execute("SELECT COUNT(*) FROM documents WHERE organization_id=? AND risk_level='low'", (user["organization_id"],)).fetchone()[0]
        average = db.execute("SELECT COALESCE(AVG(risk_score), 0) FROM documents WHERE organization_id=? AND risk_score IS NOT NULL", (user["organization_id"],)).fetchone()[0]
        deadlines = db.execute("SELECT COUNT(*) FROM deadlines d JOIN documents doc ON doc.id=d.document_id WHERE doc.organization_id=? AND d.due_date >= date('now')", (user["organization_id"],)).fetchone()[0]
    return {
        "documents_uploaded": total,
        "high_risk_documents": high,
        "medium_risk_documents": medium,
        "low_risk_documents": low,
        "average_risk_score": round(average),
        "upcoming_deadlines": deadlines,
    }


@app.post("/api/v1/deadlines/{deadline_id}/reminders")
def create_reminder(
    deadline_id: str,
    request: ReminderRequest,
    user: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    with DB_LOCK, connect() as db:
        deadline = db.execute(
            "SELECT d.* FROM deadlines d JOIN documents doc ON doc.id=d.document_id WHERE d.id=? AND doc.organization_id=?",
            (deadline_id, user["organization_id"]),
        ).fetchone()
        if not deadline:
            raise HTTPException(status_code=404, detail="Deadline not found")
        reminder = {"id": str(uuid.uuid4()), "deadline_id": deadline_id, "channel": request.channel, "days_before": request.days_before, "status": "scheduled", "created_at": now()}
        db.execute("INSERT INTO reminders VALUES (?, ?, ?, ?, ?, ?)", tuple(reminder.values()))
    record_audit(deadline["document_id"], "reminder_created", user)
    return reminder


@app.delete("/api/v1/documents/{document_id}", status_code=204)
def delete_document(document_id: str, user: dict[str, Any] = Depends(require_role("Owner", "Admin", "Member"))) -> None:
    document = fetch_document(document_id, user["organization_id"])
    storage_key = document["storage_key"]
    with DB_LOCK, connect() as db:
        db.execute("DELETE FROM documents WHERE id=? AND organization_id=?", (document_id, user["organization_id"]))
    delete_object(storage_key, UPLOAD_DIR)
    record_audit(document_id, "delete", user)


@app.post("/api/v1/documents/{document_id}/retry", status_code=202)
def retry_document(document_id: str, background_tasks: BackgroundTasks, user: dict[str, Any] = Depends(current_user)) -> dict[str, str]:
    document = fetch_document(document_id, user["organization_id"])
    if document["status"] not in {"failed", "completed"}:
        raise HTTPException(status_code=409, detail="Document is already processing")
    with DB_LOCK, connect() as db:
        db.execute("UPDATE documents SET status='queued', stage='Queued', progress=0, updated_at=? WHERE id=?", (now(), document_id))
        db.execute("UPDATE processing_stages SET status='pending', progress=0, error=NULL, started_at=NULL, completed_at=NULL WHERE document_id=?", (document_id,))
    if os.getenv("PROCESSING_MODE", "local").lower() == "local":
        background_tasks.add_task(process_document, document_id, user["organization_id"], user)
    record_audit(document_id, "retry", user)
    return {"id": document_id, "status": "queued"}


@app.post("/api/v1/comparisons")
def compare_documents(request: ComparisonRequest, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    first, second = fetch_document(request.document_a_id, user["organization_id"]), fetch_document(request.document_b_id, user["organization_id"])
    if first["status"] != "completed" or second["status"] != "completed":
        raise HTTPException(status_code=409, detail="Both documents must finish analysis before comparison")
    first_report, second_report = json.loads(first["report_json"] or "{}"), json.loads(second["report_json"] or "{}")
    first_risks = {risk.get("title", "").strip() for risk in first_report.get("risks", [])}
    second_risks = {risk.get("title", "").strip() for risk in second_report.get("risks", [])}
    first_deadlines = {deadline.get("title", "").strip() for deadline in first_report.get("deadlines", [])}
    second_deadlines = {deadline.get("title", "").strip() for deadline in second_report.get("deadlines", [])}
    first_text = json.dumps(first_report, sort_keys=True)
    second_text = json.dumps(second_report, sort_keys=True)
    return {
        "document_a": first["name"], "document_b": second["name"],
        "similarity_score": round(difflib.SequenceMatcher(None, first_text, second_text).ratio() * 100),
        "added_risks": sorted(second_risks - first_risks),
        "removed_risks": sorted(first_risks - second_risks),
        "added_deadlines": sorted(second_deadlines - first_deadlines),
        "removed_deadlines": sorted(first_deadlines - second_deadlines),
        "modified_clauses": [],
        "disclaimer": "Comparison is an AI-assisted review and should not replace professional advice.",
    }


@app.get("/api/v1/audit")
def audit_logs(user: dict[str, Any] = Depends(require_role("Owner", "Admin"))) -> list[dict[str, Any]]:
    with connect() as db:
        return [dict(row) for row in db.execute(
            "SELECT id,user_id,document_id,action,created_at FROM audit_logs WHERE organization_id=? ORDER BY created_at DESC LIMIT 100",
            (user["organization_id"],),
        ).fetchall()]


def process_document(document_id: str, organization_id: str, user: dict[str, Any]) -> None:
    with connect() as db:
        row = db.execute("SELECT * FROM documents WHERE id=? AND organization_id=?", (document_id, organization_id)).fetchone()
    if not row:
        return
    try:
        for index, stage in enumerate(STAGES, 1):
            progress = round((index - 1) / len(STAGES) * 100)
            with DB_LOCK, connect() as db:
                db.execute("UPDATE documents SET status='processing',stage=?,progress=?,updated_at=? WHERE id=?", (stage, progress, now(), document_id))
                db.execute("UPDATE processing_stages SET status='running',progress=?,started_at=? WHERE document_id=? AND stage=?", (progress, now(), document_id, stage))
            time.sleep(0.05)
            with DB_LOCK, connect() as db:
                db.execute("UPDATE processing_stages SET status='completed',progress=?,completed_at=? WHERE document_id=? AND stage=?", (round(index / len(STAGES) * 100), now(), document_id, stage))

        path = materialize_object(row["storage_key"], UPLOAD_DIR)
        if os.getenv("AI_MODE", "real").lower() == "demo":
            filename = row["name"].lower()
            digest = int(hashlib.sha256(filename.encode()).hexdigest()[:4], 16)
            score = 28 + digest % 58
            level = "high" if score >= 70 else "medium" if score >= 45 else "low"
            report = {
                "summary": f"{row['name']} was analyzed in explicit demo mode.",
                "classification": "Document",
                "risk_score": score,
                "risk_level": level,
                "risks": [], "deadlines": [], "recommendations": [], "confidence": 0.5,
                "evidence": [], "model_version": "demo",
            }
        else:
            report = analyze_file(path, row["name"])
        if os.getenv("STORAGE_MODE", "local").lower() == "s3":
            path.unlink(missing_ok=True)
        score, level = int(report["risk_score"]), report["risk_level"]
        with DB_LOCK, connect() as db:
            timestamp = now()
            db.execute("UPDATE documents SET status='completed',stage='Complete',progress=100,risk_level=?,risk_score=?,classification=?,report_json=?,updated_at=? WHERE id=?", (level, score, report["classification"], json.dumps(report), timestamp, document_id))
            db.execute("DELETE FROM deadlines WHERE document_id=?", (document_id,))
            for deadline in report.get("deadlines", []):
                due_date = deadline.get("date") or deadline.get("due_date")
                if due_date:
                    db.execute("INSERT INTO deadlines VALUES (?, ?, ?, ?, ?, ?, ?)", (str(uuid.uuid4()), document_id, deadline["title"], due_date, deadline["priority"], deadline.get("source", "Document evidence"), deadline.get("timezone", "UTC")))
        record_audit(document_id, "analysis_completed", user)
    except Exception as error:
        with DB_LOCK, connect() as db:
            db.execute("UPDATE documents SET status='failed',stage='Failed',updated_at=? WHERE id=?", (now(), document_id))
            db.execute("UPDATE processing_stages SET status='failed',error=? WHERE document_id=? AND status='running'", (str(error)[:500], document_id))
        record_audit(document_id, "analysis_failed", user)
