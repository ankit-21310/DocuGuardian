# DocuGuardian

DocuGuardian is an AI document-intelligence workspace with authenticated workspaces, organization-scoped documents, a real multi-stage analysis pipeline, structured persistence, grounded chat, deadlines/reminders, analytics, comparison, multi-language translation, voice summaries, and env-driven feature flags.

## Key features

- Plain-language summary with risk score (0–100)
- Clause severity and hidden penalty detection
- Deadline extraction with calendar and reminders
- Grounded AI chat with citations and suggested follow-ups
- Document comparison across analyzed reports
- Multi-language translation for reports and chat responses
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

### Multi-language and voice

- `FEATURE_TRANSLATION=true` — enables `/api/v1/translate`, report translation, and language-aware chat
- `FEATURE_VOICE=true` — enables `/api/v1/voice-summary` playback in the report panel
- `SUPPORTED_LANGUAGES` — comma-separated list exposed to the UI (Settings and AI Chat language selectors)

When translation is enabled:

- **Settings** stores the preferred workspace language in browser local storage
- **AI Chat** sends `target_language` so answers and follow-up prompts are returned in that language
- **Documents → Report** can translate summary, recommendations, and action plan

Restart the API after changing feature flags or language settings in `.env`.

### Notifications

- `SMTP_URL` — optional email delivery for reminders
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
- `api/app/notifications.py` — in-app/email reminder delivery
- `worker/` — compose worker + shared stage contract
- `infra/docker-compose.yml` — web, API, worker, PostgreSQL, Redis, MinIO
- `plan.md` / `arch.md` / `ui.md` — product specs

## Deferred (by design)

Fraud indicators, Google/Outlook calendar OAuth, full UI localization (menus/buttons in every language), and React Native mobile are deferred until the core pipeline remains stable.
