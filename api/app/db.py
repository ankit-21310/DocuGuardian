from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from typing import Any, Iterator, Sequence
from urllib.parse import unquote, urlparse

from .config import DATA_DIR, DATABASE_URL

DB_LOCK = threading.Lock()
_IS_POSTGRES = DATABASE_URL.startswith("postgres")


class DatabaseError(Exception):
    pass


class IntegrityError(DatabaseError):
    pass


def _sqlite_path() -> str:
    if DATABASE_URL.startswith("sqlite:///"):
        return DATABASE_URL.removeprefix("sqlite:///")
    parsed = urlparse(DATABASE_URL)
    if parsed.scheme == "sqlite":
        return unquote(parsed.path.lstrip("/")) if parsed.path else str(DATA_DIR / "docuguardian.db")
    return str(DATA_DIR / "docuguardian.db")


def is_postgres() -> bool:
    return _IS_POSTGRES


def _adapt_sql(sql: str) -> str:
    if not _IS_POSTGRES:
        return sql
    return sql.replace("?", "%s")


class Connection:
    def __init__(self, raw: Any):
        self._raw = raw

    def execute(self, sql: str, params: Sequence[Any] | None = None):
        params = params or ()
        try:
            if _IS_POSTGRES:
                from psycopg.rows import dict_row

                cursor = self._raw.cursor(row_factory=dict_row)
                cursor.execute(_adapt_sql(sql), params)
                return cursor
            cursor = self._raw.execute(sql, params)
            return cursor
        except Exception as error:
            name = type(error).__name__
            if "Integrity" in name or "UniqueViolation" in name:
                raise IntegrityError(str(error)) from error
            raise

    def executescript(self, script: str) -> None:
        if _IS_POSTGRES:
            statements = [part.strip() for part in script.split(";") if part.strip()]
            for statement in statements:
                self.execute(statement)
            return
        self._raw.executescript(script)

    def commit(self) -> None:
        self._raw.commit()

    def close(self) -> None:
        self._raw.close()


@contextmanager
def connect() -> Iterator[Connection]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if _IS_POSTGRES:
        import psycopg

        raw = psycopg.connect(DATABASE_URL)
        connection = Connection(raw)
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()
        return

    raw = sqlite3.connect(_sqlite_path(), check_same_thread=False)
    raw.row_factory = sqlite3.Row
    raw.execute("PRAGMA foreign_keys = ON")
    connection = Connection(raw)
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def fetchone(cursor) -> dict[str, Any] | None:
    row = cursor.fetchone()
    if row is None:
        return None
    if isinstance(row, dict):
        return row
    return dict(row)


def fetchall(cursor) -> list[dict[str, Any]]:
    rows = cursor.fetchall()
    if not rows:
        return []
    if isinstance(rows[0], dict):
        return list(rows)
    return [dict(row) for row in rows]


SCHEMA_SQL = """
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
  extracted_text TEXT,
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
  delivered_at TEXT, FOREIGN KEY(deadline_id) REFERENCES deadlines(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS audit_logs (
  id TEXT PRIMARY KEY, organization_id TEXT, user_id TEXT, document_id TEXT,
  action TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS document_sections (
  id TEXT PRIMARY KEY, document_id TEXT NOT NULL, heading TEXT NOT NULL,
  content TEXT NOT NULL, page INTEGER, ordinal INTEGER NOT NULL DEFAULT 0,
  FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS document_entities (
  id TEXT PRIMARY KEY, document_id TEXT NOT NULL, label TEXT NOT NULL,
  value TEXT NOT NULL, confidence REAL, page INTEGER, text_span TEXT,
  FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS document_clauses (
  id TEXT PRIMARY KEY, document_id TEXT NOT NULL, title TEXT NOT NULL,
  body TEXT NOT NULL, severity TEXT NOT NULL, category TEXT NOT NULL,
  page INTEGER, text_span TEXT, confidence REAL,
  FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS document_risks (
  id TEXT PRIMARY KEY, document_id TEXT NOT NULL, title TEXT NOT NULL,
  severity TEXT NOT NULL, explanation TEXT NOT NULL, recommendation TEXT NOT NULL,
  source TEXT NOT NULL, page INTEGER, text_span TEXT, confidence REAL,
  is_penalty INTEGER NOT NULL DEFAULT 0,
  FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS action_items (
  id TEXT PRIMARY KEY, document_id TEXT NOT NULL, title TEXT NOT NULL,
  detail TEXT NOT NULL, priority TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open',
  due_date TEXT, ordinal INTEGER NOT NULL DEFAULT 0,
  FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS document_chunks (
  id TEXT PRIMARY KEY, document_id TEXT NOT NULL, content TEXT NOT NULL,
  page INTEGER, ordinal INTEGER NOT NULL DEFAULT 0, embedding_json TEXT,
  FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS notifications (
  id TEXT PRIMARY KEY, organization_id TEXT NOT NULL, user_id TEXT,
  title TEXT NOT NULL, body TEXT NOT NULL, channel TEXT NOT NULL,
  status TEXT NOT NULL, created_at TEXT NOT NULL, read_at TEXT,
  related_deadline_id TEXT, related_document_id TEXT
);
CREATE TABLE IF NOT EXISTS chat_messages (
  id TEXT PRIMARY KEY, document_id TEXT NOT NULL, user_id TEXT NOT NULL,
  role TEXT NOT NULL, content TEXT NOT NULL, citations_json TEXT,
  created_at TEXT NOT NULL, FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE
);
"""
