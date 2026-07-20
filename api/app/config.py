from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.getenv("DOCUGUARDIAN_DATA_DIR", ROOT / "data"))
UPLOAD_DIR = DATA_DIR / "uploads"
ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{(DATA_DIR / 'docuguardian.db').as_posix()}")
REDIS_URL = os.getenv("REDIS_URL", "").strip()
CLAMAV_URL = os.getenv("CLAMAV_URL", "").strip()
AUTH_SECRET_RAW = os.getenv("AUTH_SECRET", "").strip()
DEFAULT_DEV_SECRET = "local-development-secret-change-me"
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(25 * 1024 * 1024)))
PROCESSING_MODE = os.getenv("PROCESSING_MODE", "local").lower()
AI_MODE = os.getenv("AI_MODE", "real").lower()
ENABLE_DEMO_AUTH = os.getenv("ENABLE_DEMO_AUTH", "true" if ENVIRONMENT != "production" else "false").lower() in {"1", "true", "yes"}
ENABLE_FIXTURE_ANALYSIS = os.getenv("ENABLE_FIXTURE_ANALYSIS", "false").lower() in {"1", "true", "yes"}
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
CORS_ORIGINS = [origin.strip() for origin in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",") if origin.strip()]
FEATURE_VOICE = os.getenv("FEATURE_VOICE", "false").lower() in {"1", "true", "yes"}
FEATURE_TRANSLATION = os.getenv("FEATURE_TRANSLATION", "false").lower() in {"1", "true", "yes"}
SMTP_URL = os.getenv("SMTP_URL", "").strip()
NOTIFICATION_FROM = os.getenv("NOTIFICATION_FROM", "noreply@docuguardian.local")

SUPPORTED_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "image/png",
    "image/jpeg",
}
SUPPORTED_SUFFIXES = {".pdf", ".docx", ".png", ".jpg", ".jpeg"}

# Single source of truth for API + worker pipeline labels.
PIPELINE_STAGES = (
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


def resolve_auth_secret() -> bytes:
    secret = AUTH_SECRET_RAW or (DEFAULT_DEV_SECRET if ENVIRONMENT != "production" else "")
    if not secret:
        raise RuntimeError("AUTH_SECRET must be configured")
    if ENVIRONMENT == "production" and secret == DEFAULT_DEV_SECRET:
        raise RuntimeError("AUTH_SECRET must be configured in production")
    return secret.encode()
