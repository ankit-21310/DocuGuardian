# 🛡️ DocuGuardian — AI Intelligent Document Protection Agent

> **Don't just read your documents. Let them protect you.**

---

# Problem Statement

Every household stores important documents—loan agreements, insurance policies, property papers, employment contracts, medical records, rental agreements, tax documents—but almost nobody truly understands them.

These documents contain:

- Hidden penalties
- Complex legal clauses
- Renewal deadlines
- Interest rate conditions
- Collateral obligations
- Fine-print exclusions
- Compliance requirements

Most people sign them because they trust the institution or simply don't have the legal expertise to review every page.

The consequences are serious:

- ❌ Missed insurance claims
- ❌ Increased loan interest
- ❌ Hidden collateral risks
- ❌ Missed renewal deadlines
- ❌ Legal disputes
- ❌ Financial losses

Today, AI chatbots can summarize a document.

But summarization is **not protection**.

They usually:

- Read one document at a time
- Wait for users to ask the right questions
- Cannot connect information across multiple documents
- Don't proactively warn users about future risks
- Don't monitor obligations or deadlines
- Don't generate actionable plans

People don't need another chatbot.

They need an intelligent guardian that continuously protects them from expensive mistakes before they happen.

---

# Our Solution

## 🛡️ DocuGuardian

DocuGuardian is an AI-powered **Document Protection Agent** that transforms complex legal and financial documents into clear, actionable intelligence.

Instead of merely summarizing documents, DocGuardian continuously analyzes them to identify hidden risks, extract obligations, monitor deadlines, and generate personalized recommendations.

It acts as a proactive digital advocate for individuals and families—helping them understand what they signed, what they are responsible for, and what actions they should take before problems arise.

---

# What Makes DocGuardian Different?

Traditional AI Chatbot

- Reads one document
- Gives summary
- Waits for questions
- Doesn't monitor future events

↓

**DocuGuardian**

- Understands multiple documents together
- Connects information across documents
- Detects hidden risks automatically
- Finds contradictions
- Tracks deadlines
- Generates action plans
- Sends reminders
- Explains legal language in plain English
- Acts like an intelligent personal document advisor

---

# Key Features

## 📄 Intelligent Document Parsing

Supports multiple document types:

- Loan Agreements
- Insurance Policies
- Medical Documents
- Property Papers
- Rental Agreements
- Tax Documents
- Employment Contracts
- Financial Statements

---

## 🏷️ Automatic Document Classification

Automatically identifies document categories using AI.

Example:

```
Loan Agreement
Insurance Policy
Medical Record
Employment Contract
Property Deed
```

---

## 🔍 Structured Information Extraction

Extracts important information including:

- Parties involved
- Institution
- Policy Number
- Loan Amount
- Interest Rate
- Collateral
- Renewal Dates
- Nominee
- Premium
- Payment Schedule
- Important Clauses

---

## ⚠️ Risk & Obligation Analysis

Identifies:

- Hidden penalties
- Dangerous clauses
- Variable interest risks
- Collateral exposure
- Renewal obligations
- Missed compliance
- Financial liabilities

Each document receives a:

```
Risk Score (0–100)
```

along with severity classification.

---

## 🚨 Clause Severity Detection

Automatically categorizes clauses as:

- Low Risk
- Medium Risk
- High Risk
- Critical

with clear explanations in simple language.

---

## 💰 Hidden Penalty Detection

Finds clauses that may lead to:

- Penalty charges
- Processing fees
- Foreclosure fees
- Interest escalation
- Insurance exclusions
- Automatic renewals

---

## 📅 Deadline Extraction & Reminder Engine

Automatically extracts:

- Renewal dates
- EMI schedules
- Policy expiry
- Claim deadlines
- Compliance deadlines

Creates smart reminders before important dates and integrates with calendar services.

---

## 🤖 Document-Aware AI Assistant

Unlike generic chatbots, the assistant answers questions strictly based on uploaded documents.

Example:

> Can the bank increase my interest rate?

> Which policy covers accidental death?

> What happens if I miss this payment?

Every answer is grounded in the relevant document clauses.

---

## 🔄 Multi-Document Intelligence

One of DocGuardian's biggest strengths.

Instead of treating each file independently, it connects information across multiple documents.

It can detect:

- Name mismatches
- Conflicting clauses
- Duplicate obligations
- Shared collateral
- Cross-document risks
- Linked insurance policies

This enables insights that traditional document readers cannot provide.

---

## 📊 Dashboard & Analytics

A centralized dashboard displaying:

- Total Documents
- Risk Distribution
- Upcoming Deadlines
- Active Obligations
- Recent Alerts
- Document Categories
- Action Items

---

## 📝 Plain Language Summaries

Converts legal language into simple explanations that anyone can understand.

No legal background required.

---

## 📋 AI Action Plan Generator

Instead of only identifying issues, DocGuardian recommends next steps.

Examples:

- Draft correction letter
- Request bank clarification
- File insurance claim
- Update nominee
- Contact institution
- Prepare required documents

---

## 🌍 Multi-language Translation

Explains documents in multiple regional languages to improve accessibility.

---

## 🎤 Voice Summary

Users can listen to concise audio summaries instead of reading lengthy documents.

---

# End-to-End Pipeline

# ⚙️ AI Processing Pipeline

```text
                         📂 User Upload
                               │
                               ▼
                 ┌─────────────────────────┐
                 │  OCR & Text Extraction  │
                 └─────────────────────────┘
                               │
                               ▼
                 ┌─────────────────────────┐
                 │ Document Classification │
                 └─────────────────────────┘
                               │
                               ▼
                 ┌─────────────────────────┐
                 │ Structured Information  │
                 │     Extraction          │
                 └─────────────────────────┘
                               │
                               ▼
                 ┌─────────────────────────┐
                 │ Multi-Document AI Brain │
                 │ (Knowledge Graph + RAG) │
                 └─────────────────────────┘
                               │
                ┌──────────────┼──────────────┐
                ▼              ▼              ▼
      ┌────────────────┐ ┌──────────────┐ ┌────────────────┐
      │ Risk Analysis  │ │ Clause &     │ │ Deadline &     │
      │ Engine         │ │ Penalty      │ │ Reminder       │
      │                │ │ Detection    │ │ Engine         │
      └────────────────┘ └──────────────┘ └────────────────┘
                └──────────────┼──────────────┘
                               ▼
                 ┌─────────────────────────┐
                 │ AI Recommendation Engine│
                 └─────────────────────────┘
                               │
                ┌──────────────┼──────────────┐
                ▼              ▼              ▼
      ┌────────────────┐ ┌──────────────┐ ┌────────────────┐
      │ AI Assistant   │ │ Action Plan  │ │ Voice Summary  │
      └────────────────┘ └──────────────┘ └────────────────┘
                               │
                               ▼
                 ┌─────────────────────────┐
                 │ Dashboard & Analytics   │
                 └─────────────────────────┘
                               │
                               ▼
                 ┌─────────────────────────┐
                 │ Calendar • Email •      │
                 │ Alerts & Notifications  │
                 └─────────────────────────┘
```

---

# Technology Stack

### Frontend

- React.js / Next.js
- Tailwind CSS
- TypeScript

### Backend

- FastAPI
- Python

### AI/ML

- OCR Engine
- LLM (GPT/Gemini)
- Embedding Models
- Vector Database
- Model Pipeline
- Knowledge Graph

### Database

- PostgreSQL
- Redis

### Storage

- Object Storage
- Document Repository

### Integrations

- Google Calendar
- Email Notifications
- Voice APIs
- Translation APIs

---

# Impact

DocuGuardian empowers individuals by transforming complex legal and financial paperwork into actionable insights.

Instead of reacting after a costly mistake, users receive proactive alerts, personalized recommendations, and continuous monitoring of their obligations.

By simplifying legal language and connecting information across multiple documents, DocGuardian reduces financial risk, improves transparency, and helps families make informed decisions with confidence.

---

# Vision

We believe AI should do more than answer questions.

It should actively protect people.

DocuGuardian is building an intelligent document companion that evolves from a document reader into a lifelong digital guardian—helping individuals, families, and businesses navigate legal and financial complexity with clarity, confidence, and peace of mind.

---

# Future Roadmap

- AI Fraud Detection
- Legal Compliance Checker
- Tax Document Intelligence
- Healthcare Document Assistant
- Financial Health Score
- Smart Contract Comparison
- WhatsApp Assistant
- Mobile Application
- Enterprise Dashboard
- Government Document Support

---

# Our Mission

**Making every important document understandable, actionable, and impossible to overlook.**

Because protection begins with understanding.


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
