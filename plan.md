# DocuGuardian Implementation Plan

Based on [`arch.md`](./arch.md) and [`ui.md`](./ui.md), DocuGuardian will be delivered as a web-first AI document intelligence platform, with mobile and enterprise capabilities added after the core workflow is stable.

## 1. Foundation

- Create a monorepo containing:
  - `web/`: Next.js, React, TypeScript, Tailwind CSS, and shadcn/ui.
  - `api/`: FastAPI backend.
  - `worker/`: asynchronous document-processing workers.
  - `infra/`: Docker, PostgreSQL, Redis, and object-storage configuration.
- Establish the UI design system using Inter, the specified blue/green/yellow/red palette, responsive layouts, 16px cards, and 12px controls.
- Add environment configuration, structured logging, error handling, API versioning, linting, formatting, and CI checks.

## 2. Authentication and authorization

- Implement email/password and OAuth authentication.
- Use JWT validation between the frontend and FastAPI.
- Add users, organizations, memberships, and roles: Owner, Admin, Member, and Viewer.
- Enforce tenant and document-level access control on every API query.
- Record uploads, downloads, sharing, analysis, and deletion in audit logs.

## 3. Document workflow

Implement the complete upload-to-report flow:

1. Validate PDF, DOCX, image, and scanned-document uploads.
2. Scan files for malware and store originals in S3-compatible object storage.
3. Create an asynchronous processing job.
4. Run OCR, parsing, classification, layout analysis, and structured extraction.
5. Detect clauses, obligations, risks, deadlines, and recommendations.
6. Generate an action plan and report.
7. Generate embeddings for AI Chat and semantic search.
8. Notify the user when processing completes or fails.

Jobs must be resumable, retryable, idempotent, and visible in the UI through pipeline progress updates.

## 4. Backend modules and API

Create modules for authentication, organizations, documents, processing, extraction, risks, deadlines, reports, chat, comparison, calendar, analytics, and notifications.

Initial API surface:

- `POST /api/v1/documents`
- `GET /api/v1/documents`
- `GET /api/v1/documents/{id}`
- `GET /api/v1/documents/{id}/processing`
- `GET /api/v1/documents/{id}/report`
- `POST /api/v1/documents/{id}/chat`
- `POST /api/v1/comparisons`
- `GET /api/v1/deadlines`
- `POST /api/v1/deadlines/{id}/reminders`
- `GET /api/v1/analytics/overview`

Generate shared TypeScript types from the FastAPI OpenAPI schema.

## 5. Data and storage

Use PostgreSQL as the system of record, S3-compatible storage for files, Redis for caching and job coordination, and PostgreSQL with pgvector for the initial vector-search implementation.

Core entities:

- Users, organizations, and memberships.
- Documents and document versions.
- Processing jobs and pipeline stages.
- Sections, extracted entities, clauses, obligations, and embeddings.
- Risks, deadlines, recommendations, action items, and reports.
- Chat sessions, chat messages, notifications, and audit logs.

Every AI result should retain its source document, page or text span, confidence score, model version, and creation timestamp. This is required for citations, highlighting, and auditability.

## 6. AI pipeline

Implement independent pipeline stages for:

1. OCR and document parsing.
2. Document classification.
3. Layout understanding.
4. Entity and metadata extraction.
5. Clause and obligation extraction.
6. Legal and general risk analysis.
7. Deadline detection and date normalization.
8. Recommendation generation.
9. Action-plan generation.
10. Embedding generation.
11. Report generation.

Use provider adapters so OCR and LLM providers can be changed without changing business logic. All recommendations and chat responses must be grounded in document evidence and include citations. AI-generated content must display confidence and appropriate legal, medical, and financial disclaimers.

## 7. Frontend screens

### Public screens

- Landing page with hero section, upload/demo CTAs, feature grid, and trust messaging.
- Sign-in, sign-up, and password recovery screens.

### Authenticated screens

- Dashboard with document counts, high-risk documents, deadlines, protection score, recent documents, and charts.
- Upload screen with drag-and-drop, file validation, progress, and retry states.
- AI processing screen with animated stages for OCR, parsing, classification, extraction, risk analysis, deadline detection, recommendations, and report generation.
- Intelligence report with summary, risk score, classification, highlighted clauses, timeline, recommendations, action checklist, and report download.
- AI Chat with conversation panel, document viewer, suggested prompts, and source citations.
- Contract Comparison with side-by-side documents, clause differences, similarity score, new risks, and removed clauses.
- Calendar with renewal, expiry, payment, warranty, and notice-period events.
- Analytics with total documents, average risk score, risk distribution, categories, and monthly uploads.
- Settings for profile, organization, notifications, integrations, and security.

### Mobile behavior

- Use bottom navigation for Dashboard, Upload, Chat, Calendar, and Profile.
- Use swipeable cards for summaries, risks, deadlines, and recommendations.
- Keep all critical risk information understandable without color alone.

## 8. UI behavior

- Stream processing progress using WebSockets or server-sent events.
- Animate uploads, processing stages, risk gauges, and report completion.
- Make risk items clickable so users can navigate to the source clause in the document viewer.
- Support PDF text and bounding-box highlighting.
- Add a floating AI assistant.
- Keep voice summaries behind a feature flag until the core report experience is stable.
- Implement complete loading, empty, error, retry, and permission-denied states.
- Test keyboard navigation, screen-reader labels, contrast, and responsive layouts.

## 9. Deadlines, reminders, and integrations

- Normalize extracted dates according to the user's timezone.
- Assign deadline priority based on type and proximity.
- Provide in-app and email reminders first.
- Add Google Calendar and Outlook integration after the internal calendar is reliable.
- Keep notification delivery idempotent to prevent duplicate reminders.

## 10. Security and reliability

- Use TLS, encrypted database/object storage, and signed temporary file URLs.
- Validate MIME type, file size, and file content before processing.
- Scan uploads for malware.
- Support secure deletion of originals, derived files, embeddings, and reports.
- Apply rate limits to uploads and AI Chat.
- Protect against prompt injection and malicious document content.
- Avoid PII in logs and store secrets in a managed secrets service.
- Add retries, dead-letter handling, health checks, metrics, traces, and structured logs.
- Isolate organization data in storage, search, caching, and background jobs.

## 11. Delivery phases

### Phase 1: Vertical MVP

- Project setup and design system.
- Authentication and organization access control.
- Document upload and object storage.
- PostgreSQL schema and processing jobs.
- OCR, parsing, basic classification, extraction, and risk report.
- Dashboard and document list.

### Phase 2: Intelligence experience

- Clause highlighting.
- Deadline extraction and timeline.
- Recommendations and action plans.
- Animated processing pipeline.
- Report download.
- Email and in-app reminders.

### Phase 3: Assistant and comparison

- Grounded AI Chat with citations.
- Semantic search.
- Contract comparison.
- Document versioning.
- Analytics dashboards.

### Phase 4: Production integrations

- Google Calendar and Outlook.
- Push notifications.
- Organization administration.
- Advanced auditing and compliance controls.
- Cloud deployment, autoscaling workers, monitoring, and disaster recovery.
- React Native mobile application planning.

## 12. Testing and acceptance criteria

### Tests

- Unit tests for extraction, risk scoring, date normalization, permissions, and recommendation rules.
- API integration tests for uploads, processing, reports, chat, comparisons, deadlines, and reminders.
- End-to-end tests covering upload through completed report.
- Accessibility, responsive-layout, security, and tenant-isolation tests.
- Failure and retry tests for OCR, LLM, storage, notifications, and worker interruptions.

### Acceptance criteria

- A user can upload a supported document and see live processing progress.
- A completed report contains a summary, risk score, risks, deadlines, recommendations, and source evidence.
- Every risk, deadline, and recommendation links to the relevant document page or text span.
- Failed jobs can be retried without duplicating documents, results, or reminders.
- Users cannot access documents outside their organization or role permissions.
- Dashboard metrics match persisted document and risk data.
- AI Chat answers are grounded and cite document sections.
- Comparison identifies added, removed, and modified clauses.
- Critical findings remain understandable without relying only on color.
- Sensitive actions are recorded in audit logs.

## Assumptions and defaults

- The first release is web-only; React Native is deferred.
- FastAPI is the backend standard.
- PostgreSQL and pgvector are used before introducing a separate vector database.
- Redis is used for job coordination; Kafka or RabbitMQ can be introduced at larger scale.
- S3-compatible object storage holds originals and derived artifacts.
- AI providers are accessed through replaceable adapters.
- Version one supports English and a limited set of document categories.
- DocuGuardian provides decision support and does not replace qualified legal, medical, or financial advice.
