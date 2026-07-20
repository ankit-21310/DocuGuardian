# DocuGuardian

DocuGuardian is an AI document-intelligence workspace with authenticated workspaces, organization-scoped documents, API-backed dashboard data, resumable processing stages, evidence-aware reports, deadlines, analytics, grounded chat, audit events, and a compose profile with PostgreSQL/Redis/MinIO services.

## Run locally

```bash
npm install
npm run dev
```

Open `http://localhost:3000`, then run the API in a second terminal:

```bash
cd api
python -m venv .venv
.venv\\Scripts\\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Sign in, create an account, or use the local demo account (`alex@example.com` / `demo-password`). Upload a PDF, DOCX, PNG, or JPG. The frontend polls persisted processing stages and updates the report when analysis completes.

For the containerized stack:

```bash
docker compose -f infra/docker-compose.yml up --build
```

Real analysis is enabled by default with `AI_MODE=real`. Set `OPENAI_API_KEY` in `.env`; the API analyzes each source document through the Responses API with a structured report schema and uses the same provider for grounded chat. If no key is configured, processing fails explicitly. Use `AI_MODE=demo` only for an explicit local fixture run.

## Important environment settings

Copy `.env.example` to `.env` and configure `AUTH_SECRET`, `OPENAI_API_KEY`, CORS origins, and storage/queue settings for the environment. `PROCESSING_MODE=local` runs processing through FastAPI background tasks; the compose stack uses a database-backed worker process.

## Structure

- `app/page.tsx` — authenticated, API-backed workspace UI
- `app/globals.css` — responsive design system and components
- `api/app/main.py` — FastAPI routes, authentication, organization scoping, persistence, processing lifecycle, reports, deadlines, and chat
- `api/app/ai.py` — structured OpenAI analysis and grounded chat adapter
- `worker/pipeline.py` — provider-neutral pipeline stage contract
- `worker/runner.py` — database-backed compose worker
- `infra/docker-compose.yml` — web, API, worker, PostgreSQL, Redis, and MinIO services
- `plan.md` — delivery plan
