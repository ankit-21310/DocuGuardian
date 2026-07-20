# DocuGuardian

DocuGuardian is an AI document-intelligence workspace. Users upload contracts,
policies, insurance documents, reports, and other supported files; the platform
extracts structured intelligence; and the workspace presents risks, deadlines,
obligations, recommendations, comparisons, and grounded answers.

DocuGuardian is decision-support software. Its reports are not a substitute for
qualified legal, medical, financial, or other professional advice.

## What is included

- Authenticated, organization-scoped workspaces with Owner, Admin, Member, and
  Viewer roles.
- Email/password registration and login, plus an optional local demo account.
- Upload validation for PDF, DOCX, PNG, and JPG/JPEG files.
- A persisted, multi-stage analysis pipeline with progress reporting and retry.
- Plain-language summaries, document classification, confidence, and a 0–100
  risk score.
- Risk and clause analysis, hidden-penalty detection, obligations, fraud
  indicators, recommendations, and source evidence.
- Deadline extraction, an internal calendar, action items, in-app reminders,
  optional email reminders, and optional Google Calendar/Outlook sync.
- Grounded document chat with semantic/lexical retrieval, citations, suggested
  follow-up prompts, and persistent chat sessions.
- Side-by-side document comparison with risk-score deltas, clause changes,
  deadline changes, added risks, and removed risks.
- Full report translation, localized UI chrome, translated chat, and optional
  voice summaries.
- PDF and JSON report downloads.
- Workspace analytics and role-protected audit logs.

## Architecture

```text
                         ┌────────────────────┐
                         │ Next.js web app     │
                         │ localhost:3000      │
                         └─────────┬──────────┘
                                   │ REST / JSON
                         ┌─────────▼──────────┐
                         │ FastAPI API         │
                         │ localhost:8000      │
                         └───┬──────────┬──────┘
                             │          │
                 local mode │          │ worker mode
                   background│          ▼
                         ┌───▼───┐  ┌──────────────┐
                         │Pipeline│  │ Database     │
                         │tasks   │  │ polling worker│
                         └───┬───┘  └──────┬───────┘
                             │             │
                 ┌───────────▼─────────────▼──────────┐
                 │ SQLite or PostgreSQL                 │
                 │ reports, stages, chunks, reminders  │
                 └─────────────────────────────────────┘

       Original files: local filesystem or S3-compatible storage (MinIO)
       AI services: OpenAI model and embedding endpoints
```

The frontend is a Next.js 14 application. The API is FastAPI with a small
database abstraction that supports SQLite and PostgreSQL. In local mode, the
API runs document processing through FastAPI background tasks and also runs the
reminder loop. In Compose mode, the API queues documents in the database and
`worker/runner.py` polls for queued work; the worker also processes reminders.

Redis is included in the Compose stack for infrastructure compatibility, but
the current worker coordination path is database polling rather than a Redis
queue.

## Repository layout

```text
.
├── app/                         Next.js pages, styles, and localization
├── api/app/                     FastAPI application and domain modules
│   ├── ai.py                    Analysis, embeddings, chat, translation, TTS
│   ├── calendar_sync.py         Google and Microsoft calendar OAuth/sync
│   ├── config.py                Environment values and pipeline contract
│   ├── db.py                    SQLite/PostgreSQL connection and schema
│   ├── main.py                  HTTP routes, auth, orchestration
│   ├── notifications.py         Reminder scheduling and delivery
│   ├── parsing.py               PDF/DOCX/image extraction and chunking
│   ├── pipeline_runner.py       Persisted document-analysis pipeline
│   ├── report_pdf.py            PDF report rendering
│   └── storage.py               Local filesystem or S3-compatible storage
├── api/tests/                   API integration tests
├── worker/                      Compose worker entry point and stage contract
├── infra/                       Dockerfiles and docker-compose.yml
├── public/                      Static frontend assets
├── .env.example                 Local configuration template
├── arch.md                      Detailed architecture proposal
├── plan.md                      Product and implementation plan
└── ui.md                       UI/UX specification
```

## Prerequisites

For local development, install:

- Node.js 20 or later and npm.
- Python 3.12 or later.
- An OpenAI API key for real analysis, embeddings, translation, voice, and
  grounded chat.

Docker Desktop with Compose is optional and is required only for the full
PostgreSQL/MinIO/worker stack.

## Quick start: local development

### 1. Configure the environment

From the repository root, copy the example file:

```bash
cp .env.example .env
```

On PowerShell:

```powershell
Copy-Item .env.example .env
```

At minimum, set a long random `AUTH_SECRET`. Set `OPENAI_API_KEY` if you want
real AI analysis. The default local configuration uses SQLite, local file
storage, FastAPI background tasks, and a 25 MB upload limit.

### 2. Install and start the frontend

```bash
npm install
npm run dev
```

The web app is available at [http://localhost:3000](http://localhost:3000).
The frontend reads its API base URL from `NEXT_PUBLIC_API_URL`, which defaults
to `http://localhost:8000`.

### 3. Install and start the API

Create a virtual environment and install the pinned backend dependencies:

```bash
python -m venv api/.venv

# macOS/Linux
source api/.venv/bin/activate

# Windows PowerShell
./api/.venv/Scripts/Activate.ps1

pip install -r api/requirements.txt
```

Start FastAPI from the `api` directory so the `app` package is importable:

```bash
cd api
uvicorn app.main:app --reload --port 8000
```

The API is available at [http://localhost:8000](http://localhost:8000).
Interactive OpenAPI documentation is at
[http://localhost:8000/docs](http://localhost:8000/docs), and the OpenAPI JSON
document is at `/api/v1/openapi.json`.

### 4. Try the application

When `ENABLE_DEMO_AUTH=true`, use the seeded local account:

```text
Email:    alex@example.com
Password: demo-password
```

Alternatively, create a separate workspace through the sign-up screen. Upload
a PDF, DOCX, PNG, or JPG/JPEG file and wait for the persisted processing stages
to complete. The report view becomes available when the document status is
`completed`.

The demo account is intended only for local development. Disable it in any
shared or production environment.

## Docker Compose

The Compose file starts the complete local stack:

- `web`: production-built Next.js server on port 3000.
- `api`: FastAPI server on port 8000.
- `worker`: database-polled analysis and reminder worker.
- `postgres`: PostgreSQL 16 with pgvector on port 5432.
- `redis`: Redis 7 on port 6379.
- `minio`: S3-compatible object storage on ports 9000 and 9001.

Start it from the repository root:

```bash
docker compose -f infra/docker-compose.yml up --build
```

The MinIO console is available at
[http://localhost:9001](http://localhost:9001). The development credentials in
the Compose file are `minioadmin` / `minioadmin`; change them before using the
stack outside a private development machine.

The Compose API uses PostgreSQL, S3-compatible storage, and `PROCESSING_MODE=worker`.
It reads values such as `OPENAI_API_KEY`, `AI_MODE`, `OPENAI_MODEL`,
`EMBEDDING_MODEL`, `FEATURE_VOICE`, and `FEATURE_TRANSLATION` from Compose
interpolation. Place those values in the root `.env` file or export them in
the shell before starting Compose.

To stop the stack while preserving named volumes:

```bash
docker compose -f infra/docker-compose.yml down
```

To remove the local database, object-storage, and API-data volumes, run the
following only when that data is disposable:

```bash
docker compose -f infra/docker-compose.yml down -v
```

## Document processing pipeline

Uploading a document returns HTTP `202` immediately. Processing status is
persisted in the database and can be read from
`GET /api/v1/documents/{document_id}/processing`.

The current stages, in order, are:

1. OCR and parsing
2. Classification
3. Layout understanding
4. Structured extraction
5. Clause extraction
6. Risk analysis
7. Deadline detection
8. Recommendations
9. Embeddings
10. Report generation

The final document state is `completed`, `failed`, or still in progress. A
failed document can be submitted to `POST /api/v1/documents/{document_id}/retry`.

Parsing behavior is format-specific:

- PDFs use `pypdf` text extraction when text is available.
- Images are sent through the vision-capable AI analysis path; the local parser
  stores a stable image marker until that stage runs.
- DOCX files are accepted and the parser attempts to use `python-docx` when it
  is installed. The current requirements file does not pin `python-docx`, so
  DOCX text extraction is best effort unless that dependency is added to the
  environment.

## Authentication and authorization

Protected routes require a bearer token:

```http
Authorization: Bearer <access_token>
```

Tokens are signed with `AUTH_SECRET` and expire after eight hours. Registration
creates a user, organization, and Owner membership. All document, deadline,
notification, chat, and analytics queries are scoped to the authenticated
user's organization.

The built-in roles are:

| Role | Current protected capability |
| --- | --- |
| Owner | Full workspace access, including audit logs |
| Admin | Workspace access and audit logs |
| Member | Read/process workspace data and update permitted action items |
| Viewer | Read-only workspace access |

Document deletion is available to Owners, Admins, and Members. Audit logs are
available only to Owners and Admins.

## API overview

The complete, request/response-validated API is exposed through FastAPI's
OpenAPI documentation. The main route groups are listed below.

### Health and feature discovery

| Method | Route | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Database connectivity and service health |
| `GET` | `/api/v1/features` | Enabled features, languages, and pipeline stages |

### Authentication

| Method | Route | Purpose |
| --- | --- | --- |
| `POST` | `/api/v1/auth/demo` | Issue a token for the local demo user |
| `POST` | `/api/v1/auth/register` | Create a user and personal workspace |
| `POST` | `/api/v1/auth/login` | Authenticate with email and password |
| `GET` | `/api/v1/auth/me` | Return the current user and workspace |

### Documents and reports

| Method | Route | Purpose |
| --- | --- | --- |
| `POST` | `/api/v1/documents` | Upload and queue a document; returns `202` |
| `GET` | `/api/v1/documents` | List documents in the current workspace |
| `GET` | `/api/v1/documents/{id}` | Read document metadata and report summary |
| `GET` | `/api/v1/documents/{id}/processing` | Read status and per-stage progress |
| `GET` | `/api/v1/documents/{id}/report` | Read the completed structured report |
| `GET` | `/api/v1/documents/{id}/report/download` | Download PDF or JSON, optionally translated |
| `POST` | `/api/v1/documents/{id}/retry` | Retry a failed document |
| `DELETE` | `/api/v1/documents/{id}` | Delete the document and stored original |
| `PATCH` | `/api/v1/action-items/{id}` | Set an action item to `open` or `completed` |

Report downloads use `format=pdf` by default. Use `format=json` for the
structured report, and add `target_language=<language>` when translation is
enabled.

### Chat and comparison

| Method | Route | Purpose |
| --- | --- | --- |
| `POST` | `/api/v1/chat/sessions` | Create a chat session for a completed document |
| `GET` | `/api/v1/chat/sessions` | List the current user's sessions |
| `GET` | `/api/v1/chat/sessions/{id}/messages` | Read session history |
| `DELETE` | `/api/v1/chat/sessions/{id}` | Delete a session |
| `POST` | `/api/v1/documents/{id}/chat` | Ask a grounded question about a document |
| `POST` | `/api/v1/comparisons` | Compare two completed documents |

Chat requests accept `message`, optional `session_id`, and optional
`target_language`. The response contains an answer, source citations, suggested
prompts, and the session ID.

### Deadlines, reminders, analytics, and audit

| Method | Route | Purpose |
| --- | --- | --- |
| `GET` | `/api/v1/deadlines` | List extracted deadlines for the workspace |
| `POST` | `/api/v1/deadlines/{id}/reminders` | Schedule an in-app or email reminder |
| `GET` | `/api/v1/notifications` | List recent workspace notifications |
| `GET` | `/api/v1/analytics/overview` | Return workspace metrics and distributions |
| `GET` | `/api/v1/audit` | Read audit events as Owner/Admin |

### Translation, voice, and calendar integrations

| Method | Route | Purpose |
| --- | --- | --- |
| `POST` | `/api/v1/translate` | Translate a text fragment |
| `POST` | `/api/v1/documents/{id}/translate` | Translate and persist a report variant |
| `POST` | `/api/v1/voice-summary` | Generate an audio summary response |
| `GET` | `/api/v1/integrations/calendar` | Show calendar integration status |
| `GET` | `/api/v1/integrations/calendar/google/authorize` | Start Google OAuth |
| `GET` | `/api/v1/integrations/calendar/outlook/authorize` | Start Microsoft OAuth |
| `POST` | `/api/v1/integrations/calendar/sync` | Sync workspace deadlines |
| `PATCH` | `/api/v1/integrations/calendar/{id}/auto-sync` | Toggle integration auto-sync |
| `DELETE` | `/api/v1/integrations/calendar/{provider}` | Disconnect a provider |

## Configuration reference

`.env.example` is the source of truth for the available settings. The most
important values are grouped here for quick reference.

### Frontend and API

| Variable | Default | Description |
| --- | --- | --- |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | API base URL used by the browser |
| `CORS_ORIGINS` | `http://localhost:3000` | Comma-separated browser origins |
| `FRONTEND_URL` | `http://localhost:3000` | OAuth callback redirect target |
| `ENVIRONMENT` | `development` | Use `production` to enforce a configured auth secret |

### Database, files, and processing

| Variable | Default | Description |
| --- | --- | --- |
| `DOCUGUARDIAN_DATA_DIR` | `./data` | Local SQLite database and upload root |
| `DATABASE_URL` | `sqlite:///./data/docuguardian.db` | SQLite or PostgreSQL URL |
| `PROCESSING_MODE` | `local` | `local` for API background tasks; `worker` for Compose worker mode |
| `WORKER_POLL_SECONDS` | `1` | Worker polling interval in seconds |
| `MAX_UPLOAD_BYTES` | `26214400` | Maximum upload size; default is 25 MB |
| `STORAGE_MODE` | `local` | Set to `s3` for S3-compatible object storage |
| `S3_ENDPOINT` | empty | S3/MinIO endpoint |
| `S3_BUCKET` | `docuguardian` | Object-storage bucket |
| `S3_ACCESS_KEY` | empty | Object-storage access key |
| `S3_SECRET_KEY` | empty | Object-storage secret key |
| `AWS_REGION` | `us-east-1` | S3 client region |
| `REDIS_URL` | empty | Redis URL reserved for infrastructure integrations |

In local mode, originals are stored below
`DOCUGUARDIAN_DATA_DIR/uploads/{organization_id}/`. In S3 mode, the same
organization-scoped key is stored in the configured bucket.

### Authentication and AI

| Variable | Default | Description |
| --- | --- | --- |
| `AUTH_SECRET` | empty | Signing and password-hashing secret; required in production |
| `ENABLE_DEMO_AUTH` | `true` outside production | Seeds the local demo user |
| `AI_MODE` | `real` | Use `real` for OpenAI analysis or `demo` only for fixtures |
| `ENABLE_FIXTURE_ANALYSIS` | `false` | Must be `true` before `AI_MODE=demo` can run |
| `OPENAI_API_KEY` | empty | Required for real analysis and AI add-ons |
| `OPENAI_MODEL` | `gpt-4.1-mini` | Chat and analysis model |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | Chunk embedding model |

`AI_MODE=demo` is intentionally blocked unless
`ENABLE_FIXTURE_ANALYSIS=true`; it is for tests and controlled fixture runs,
not production document processing.

### Feature flags and languages

`FEATURE_VOICE`, `FEATURE_TRANSLATION`, and `FEATURE_FRAUD` are enabled
automatically when they are blank and `OPENAI_API_KEY` is configured. Set a
flag explicitly to `true` or `false` to override that behavior. The external
calendar integration is opt-in and requires `FEATURE_EXTERNAL_CALENDAR=true`.

`SUPPORTED_LANGUAGES` is a comma-separated list used by Settings and AI Chat.
The default list is:

```text
English,Spanish,Hindi,French,German,Arabic,Portuguese,
Chinese (Simplified),Japanese,Marathi,Tamil
```

Restart the API after changing environment values. The frontend stores the
preferred workspace language in browser local storage.

### Calendar OAuth

Google requires:

```text
GOOGLE_CLIENT_ID
GOOGLE_CLIENT_SECRET
GOOGLE_REDIRECT_URI
```

Microsoft/Outlook requires:

```text
MICROSOFT_CLIENT_ID
MICROSOFT_CLIENT_SECRET
MICROSOFT_TENANT_ID
MICROSOFT_REDIRECT_URI
```

The redirect URIs must exactly match the URLs registered with each provider.
The local defaults point to:

```text
http://localhost:8000/api/v1/integrations/calendar/google/callback
http://localhost:8000/api/v1/integrations/calendar/outlook/callback
```

### Notifications and upload scanning

Set `SMTP_URL` to enable email reminder delivery and set `NOTIFICATION_FROM`
to choose the sender address. When `SMTP_URL` is empty, reminders remain
available through the in-app notification path.

`CLAMAV_URL` is reserved for an optional antivirus service configuration. The
current upload path validates the extension/content type, size, and common file
magic bytes; deploy an external malware-scanning layer before accepting
untrusted production uploads.

## Database and persistence

The API initializes and migrates its schema on startup. The schema includes:

- Organizations, users, and memberships.
- Documents, stored reports, and processing stages.
- Sections, entities, clauses, risks, obligations, fraud indicators, and chunks.
- Deadlines, reminders, notifications, and action items.
- Calendar integrations and synchronization mappings.
- Chat sessions and messages.
- Audit logs.

SQLite is convenient for a single local process. Use PostgreSQL for the
Compose deployment or any multi-process environment. Back up both the
database and original-file storage; reports and derived records are not a
replacement for backing up the source documents.

## Development commands

Run these from the repository root unless noted otherwise:

```bash
# Frontend development server
npm run dev

# Type-check the frontend
npm run typecheck

# The lint script currently runs the same TypeScript no-emit check
npm run lint

# Production frontend build
npm run build

# Serve a previously built frontend
npm run start
```

Run backend tests from the `api` directory with the virtual environment active:

```bash
cd api
pytest -q
```

The API tests cover health, tenant-scoped authentication, uploads, processing,
reports, chat sessions, comparisons, deadlines, reminders, downloads,
translation, and voice-summary behavior.

## Troubleshooting

### The frontend cannot reach the API

Confirm the API is listening on port 8000 and that `NEXT_PUBLIC_API_URL` points
to the same origin visible from the browser. If you changed `.env`, restart
the Next.js dev server because public environment values are read at build/start
time.

### Analysis fails immediately

Check that `OPENAI_API_KEY` is present in the API process environment and that
`AI_MODE=real` is paired with a usable model configuration. For fixture-only
tests, set both `AI_MODE=demo` and `ENABLE_FIXTURE_ANALYSIS=true`.

### The report is not ready

Poll `/api/v1/documents/{id}/processing`. In local mode, verify the API process
is still running. In Compose mode, inspect the worker logs:

```bash
docker compose -f infra/docker-compose.yml logs -f worker
```

### OAuth redirects fail

Check `FRONTEND_URL`, the provider client credentials, and the exact callback
URI registered with the provider. Also verify that
`FEATURE_EXTERNAL_CALENDAR=true`.

### Email reminders are not delivered

In-app notifications do not require SMTP. Email reminders require a valid
`SMTP_URL`, a reachable SMTP server, and a correctly formatted
`NOTIFICATION_FROM` value. In local mode the reminder loop runs in the API;
Compose runs it in the worker.

### Docker data looks stale

Named volumes intentionally survive `docker compose down`. Inspect the stack
with `docker compose ... ps`; remove volumes only if losing local PostgreSQL,
MinIO, and API data is acceptable.

## Current limitations and production checklist

Before a production deployment, provide the operational controls that are not
part of this local-first repository setup:

- Use a strong secret manager value for `AUTH_SECRET`; never use the Compose
  development secret.
- Disable `ENABLE_DEMO_AUTH` and do not expose the demo credentials.
- Replace default PostgreSQL, MinIO, and Compose credentials.
- Put the web app and API behind HTTPS with restricted CORS origins.
- Use managed PostgreSQL/object storage with backups and retention policies.
- Add a real malware-scanning service for uploads; `CLAMAV_URL` is not wired as
  an enforcement step yet.
- Protect and rotate calendar OAuth credentials and AI provider keys.
- Add rate limiting, request-size limits at the reverse proxy, monitoring,
  centralized logs, and worker failure alerting.
- Review data residency, retention, deletion, and access requirements before
  uploading regulated or highly sensitive documents.
- Treat AI output as unverified decision support and require human review for
  consequential decisions.

React Native/mobile remains outside the current repository scope.
