from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        key, _, value = line.partition("=")
        if not key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(key.strip(), value)


_load_dotenv(ROOT / ".env")


def _resolve_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def _resolve_database_url(url: str) -> str:
    if url.startswith("sqlite:///"):
        sqlite_path = url.removeprefix("sqlite:///")
        if sqlite_path and sqlite_path != ":memory:":
            return f"sqlite:///{_resolve_path(sqlite_path).as_posix()}"
    return url


_data_dir_default = ROOT / "data"
_data_dir_env = os.getenv("DOCUGUARDIAN_DATA_DIR")
DATA_DIR = _resolve_path(_data_dir_env) if _data_dir_env else _data_dir_default
UPLOAD_DIR = DATA_DIR / "uploads"
ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()
DATABASE_URL = _resolve_database_url(os.getenv("DATABASE_URL", f"sqlite:///{(_data_dir_default / 'docuguardian.db').as_posix()}"))
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
def _service_feature_enabled(name: str) -> bool:
    """Enable AI add-ons automatically when an API key is available.

    An explicit environment value still wins, so deployments can disable a
    paid feature without changing application code.
    """
    configured = os.getenv(name)
    if not configured or not configured.strip():
        return bool(os.getenv("OPENAI_API_KEY", "").strip())
    return configured.lower() in {"1", "true", "yes", "on"}


FEATURE_VOICE = _service_feature_enabled("FEATURE_VOICE")
FEATURE_TRANSLATION = _service_feature_enabled("FEATURE_TRANSLATION")
FEATURE_FRAUD = os.getenv("FEATURE_FRAUD", "false").strip().lower() in {"1", "true", "yes", "on"}
FEATURE_EXTERNAL_CALENDAR = os.getenv("FEATURE_EXTERNAL_CALENDAR", "").strip().lower() in {"1", "true", "yes", "on"}
SUPPORTED_LANGUAGES = tuple(
    language.strip()
    for language in os.getenv(
        "SUPPORTED_LANGUAGES",
        "English,Spanish,Hindi,French,German,Arabic,Portuguese,Chinese (Simplified),Japanese,Marathi,Tamil",
    ).split(",")
    if language.strip()
)
LANGUAGE_CODES: dict[str, str] = {
    "English": "en",
    "Spanish": "es",
    "Hindi": "hi",
    "French": "fr",
    "German": "de",
    "Arabic": "ar",
    "Portuguese": "pt",
    "Chinese (Simplified)": "zh",
    "Japanese": "ja",
    "Marathi": "mr",
    "Tamil": "ta",
}
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "").strip()
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/api/v1/integrations/calendar/google/callback").strip()
MICROSOFT_CLIENT_ID = os.getenv("MICROSOFT_CLIENT_ID", "").strip()
MICROSOFT_CLIENT_SECRET = os.getenv("MICROSOFT_CLIENT_SECRET", "").strip()
MICROSOFT_TENANT_ID = os.getenv("MICROSOFT_TENANT_ID", "common").strip()
MICROSOFT_REDIRECT_URI = os.getenv("MICROSOFT_REDIRECT_URI", "http://localhost:8000/api/v1/integrations/calendar/outlook/callback").strip()
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000").strip()
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
