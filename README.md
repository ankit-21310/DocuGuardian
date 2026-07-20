# DocuGuardian

DocuGuardian is an AI document-intelligence workspace with authenticated workspaces, organization-scoped documents, a real multi-stage analysis pipeline, structured persistence, grounded chat, deadlines/reminders, analytics, comparison, multi-language translation, voice summaries, and env-driven feature flags.

## Key features

- Plain-language summary with risk score (0–100)
- Clause severity, hidden penalty detection, obligations, and fraud indicators
- Deadline extraction with internal calendar, reminders, and optional Google/Outlook sync
- Grounded AI chat with citations and suggested follow-ups
- Document comparison across analyzed reports (including deadline date changes and risk deltas)
- Multi-language translation for reports, chat responses, and localized UI chrome
- Voice summary playback for translated or original summaries
- Workspace analytics and audit trail

## Run locally

```bash
npm install
npm run dev
```

Open `http://localhost:3000`, then run the API in a second terminal:

```bash
cd api
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Sign in or create an account. When `ENABLE_DEMO_AUTH=true`, the local demo account (`alex@example.com` / `demo-password`) is available. Upload a PDF, DOCX, PNG, or JPG. The frontend polls persisted processing stages and updates the report when analysis completes.

For the containerized stack (Postgres + Redis + MinIO):

```bash
docker compose -f infra/docker-compose.yml up --build
```

## Environment setup

Copy `.env.example` to `.env` and configure:

```bash
cp .env.example .env
```

### Required

- `AUTH_SECRET` — required (no production default)
- `OPENAI_API_KEY` — required for real analysis, translation, voice, and grounded chat

### Core app

- `NEXT_PUBLIC_API_URL` — frontend API base URL (default `http://localhost:8000`)
- `DOCUGUARDIAN_DATA_DIR` — local SQLite/uploads directory (default `./data`)
- `CORS_ORIGINS` — comma-separated frontend origins
- `DATABASE_URL` — `sqlite:///./data/docuguardian.db` locally, or Postgres in compose
- `OPENAI_MODEL` — chat/analysis model (default `gpt-4.1-mini`)
- `EMBEDDING_MODEL` — chunk embedding model (default `text-embedding-3-small`)

### Processing

- `PROCESSING_MODE=local` — runs processing through FastAPI background tasks
- Compose uses a database-backed worker via `WORKER_POLL_SECONDS`
- `ENABLE_FIXTURE_ANALYSIS` — must be `true` to allow `AI_MODE=demo` fixture reports

### Auth and demo

- `ENABLE_DEMO_AUTH` — demo login seed (off in production by default)

### Multi-language, voice, and fraud

- `FEATURE_TRANSLATION` — enables translation when true; leave blank to enable automatically when `OPENAI_API_KEY` is configured
- `FEATURE_VOICE` — enables voice summaries when true; leave blank to enable automatically when `OPENAI_API_KEY` is configured
- `FEATURE_FRAUD` — enables fraud indicator extraction in reports; leave blank to enable automatically when `OPENAI_API_KEY` is configured
- `SUPPORTED_LANGUAGES` — comma-separated list exposed to the UI (Settings and AI Chat language selectors)

When translation is enabled:

- **Settings** stores the preferred workspace language in browser local storage
- **UI chrome** (navigation, report section headings, compare labels) follows the selected language via `app/i18n/`
- **AI Chat** sends `target_language` so answers and follow-up prompts are returned in that language
- **Documents → Report** can translate the full report while preserving source citations and severity metadata

### External calendar sync

Set `FEATURE_EXTERNAL_CALENDAR=true` and configure OAuth credentials:

- `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI`
- `MICROSOFT_CLIENT_ID`, `MICROSOFT_CLIENT_SECRET`, `MICROSOFT_TENANT_ID`, `MICROSOFT_REDIRECT_URI`
- `FRONTEND_URL` — used to redirect back to Settings after OAuth

Connect Google or Outlook from **Settings → Calendar integrations**. Auto-sync pushes extracted deadlines to the connected calendar.

Restart the API after changing feature flags or language settings in `.env`.

### Notifications

- `SMTP_URL` — optional email delivery for scheduled reminders
- `NOTIFICATION_FROM` — sender address for email reminders

## Structure

- `app/page.tsx` — landing, auth, and API-backed workspace UI
- `app/globals.css` — responsive design system
- `api/app/config.py` — shared env/config, pipeline stages, supported languages
- `api/app/db.py` — SQLite/Postgres connection layer
- `api/app/main.py` — FastAPI routes
- `api/app/pipeline_runner.py` — multi-stage document pipeline
- `api/app/ai.py` — OpenAI analysis, embeddings, grounded chat, translation, TTS
- `api/app/parsing.py` — OCR/text extraction and chunking
- `api/app/calendar_sync.py` — Google/Outlook OAuth and deadline sync
- `app/i18n/` — localized UI messages and translation hook
- `worker/` — compose worker + shared stage contract
- `infra/docker-compose.yml` — web, API, worker, PostgreSQL, Redis, MinIO
- `plan.md` / `arch.md` / `ui.md` — product specs

Additional workflow endpoints include `PATCH /api/v1/action-items/{id}` for persistent action completion, `POST /api/v1/documents/{id}/translate` for full-report translation, and `/api/v1/integrations/calendar/*` for external calendar OAuth and sync. Reminder requests are scheduled and delivered by the local API loop or compose worker.

## Still out of scope

React Native mobile remains a separate future app.
