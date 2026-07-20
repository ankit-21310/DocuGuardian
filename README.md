# DocuGuardian

DocuGuardian is an AI document-intelligence workspace with authenticated workspaces, organization-scoped documents, a real multi-stage analysis pipeline, structured persistence, grounded chat, deadlines/reminders, analytics, comparison, and env-driven feature flags.

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

## Important environment settings

Copy `.env.example` to `.env` and configure:

- `AUTH_SECRET` — required (no production default)
- `OPENAI_API_KEY` — required for real analysis
- `DATABASE_URL` — `sqlite:///./data/docuguardian.db` locally, or Postgres in compose
- `ENABLE_DEMO_AUTH` — demo login seed (off in production by default)
- `ENABLE_FIXTURE_ANALYSIS` — must be true to allow `AI_MODE=demo` fixture reports
- `FEATURE_VOICE` / `FEATURE_TRANSLATION` — optional product flags
- `SMTP_URL` — optional email delivery for reminders

`PROCESSING_MODE=local` runs processing through FastAPI background tasks; the compose stack uses a database-backed worker.

## Structure

- `app/page.tsx` — landing, auth, and API-backed workspace UI
- `app/globals.css` — responsive design system
- `api/app/config.py` — shared env/config and pipeline stage list
- `api/app/db.py` — SQLite/Postgres connection layer
- `api/app/main.py` — FastAPI routes
- `api/app/pipeline_runner.py` — multi-stage document pipeline
- `api/app/ai.py` — OpenAI analysis, embeddings, grounded chat
- `api/app/parsing.py` — OCR/text extraction and chunking
- `api/app/notifications.py` — in-app/email reminder delivery
- `worker/` — compose worker + shared stage contract
- `infra/docker-compose.yml` — web, API, worker, PostgreSQL, Redis, MinIO
- `plan.md` / `arch.md` / `ui.md` — product specs

## Deferred (by design)

Fraud indicators, Google/Outlook calendar OAuth, and React Native mobile are deferred until the core pipeline remains stable.
