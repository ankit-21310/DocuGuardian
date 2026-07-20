import json
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi.testclient import TestClient

from app.db import connect
from app.main import app, init_db
from app.notifications import process_due_reminders


client = TestClient(app)
init_db()


def headers() -> dict[str, str]:
    response = client.post("/api/v1/auth/demo")
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["database"] in {"sqlite", "postgres"}


def test_rejects_unsupported_file() -> None:
    response = client.post("/api/v1/documents", headers=headers(), files={"file": ("script.exe", b"bad", "application/octet-stream")})
    assert response.status_code == 415


def test_documents_require_authentication() -> None:
    response = client.get("/api/v1/documents")
    assert response.status_code == 401


def test_demo_user_can_read_scoped_workspace() -> None:
    response = client.get("/api/v1/analytics/overview", headers=headers())
    assert response.status_code == 200
    payload = response.json()
    assert set(payload) >= {"documents_uploaded", "high_risk_documents", "upcoming_deadlines", "protection_score", "categories", "monthly_uploads", "fraud_flagged_documents"}


def test_registration_creates_a_separate_workspace() -> None:
    response = client.post("/api/v1/auth/register", json={"email": "test-owner@example.com", "name": "Test Owner", "password": "secure-password"})
    assert response.status_code in {201, 409}
    if response.status_code == 201:
        assert response.json()["user"]["organization_id"] != "demo-org"


def test_features_endpoint() -> None:
    response = client.get("/api/v1/features")
    assert response.status_code == 200
    payload = response.json()
    assert "pipeline_stages" in payload
    assert "supported_languages" in payload
    assert "fraud" in payload
    assert "external_calendar" in payload
    assert "language_options" in payload
    assert len(payload["pipeline_stages"]) >= 8
    assert len(payload["supported_languages"]) >= 2


def test_demo_report_includes_obligations_and_fraud(monkeypatch) -> None:
    import app.pipeline_runner as pipeline_runner
    from app import ai

    monkeypatch.setattr(pipeline_runner, "AI_MODE", "demo")
    monkeypatch.setattr(pipeline_runner, "ENABLE_FIXTURE_ANALYSIS", True)
    monkeypatch.setattr(ai, "embed_texts", lambda texts: [[] for _ in texts])

    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
    auth = headers()
    response = client.post("/api/v1/documents", headers=auth, files={"file": ("obligations.png", png, "image/png")})
    assert response.status_code == 202
    document_id = response.json()["id"]
    for _ in range(100):
        processing = client.get(f"/api/v1/documents/{document_id}/processing", headers=auth)
        if processing.json()["status"] in {"completed", "failed"}:
            break
    report = client.get(f"/api/v1/documents/{document_id}/report", headers=auth)
    assert report.status_code == 200
    payload = report.json()
    assert "obligations" in payload
    assert "fraud_indicators" in payload
    assert payload["obligations"]


def test_calendar_status_endpoint() -> None:
    response = client.get("/api/v1/integrations/calendar", headers=headers())
    assert response.status_code == 200
    payload = response.json()
    assert "enabled" in payload
    assert "integrations" in payload
    assert isinstance(payload["integrations"], list)


def test_comparison_reports_deadline_changes() -> None:
    first = _seed_completed_document({"risk_score": 30, "risk_level": "low", "risks": [], "clauses": [], "deadlines": [{"title": "Renewal", "date": "2026-01-01", "priority": "high", "source": "A"}]})
    second = _seed_completed_document({"risk_score": 30, "risk_level": "low", "risks": [], "clauses": [], "deadlines": [{"title": "Renewal", "date": "2026-06-01", "priority": "high", "source": "B"}]})
    response = client.post("/api/v1/comparisons", headers=headers(), json={"document_a_id": first, "document_b_id": second})
    assert response.status_code == 200
    payload = response.json()
    assert payload["deadline_changes"]
    assert payload["deadline_changes"][0]["document_a_date"] == "2026-01-01"
    assert payload["deadline_changes"][0]["document_b_date"] == "2026-06-01"


def test_notifications_require_auth() -> None:
    response = client.get("/api/v1/notifications")
    assert response.status_code == 401


def test_upload_completes_and_allows_chat(monkeypatch) -> None:
    import app.pipeline_runner as pipeline_runner
    from app import ai

    monkeypatch.setattr(pipeline_runner, "AI_MODE", "demo")
    monkeypatch.setattr(pipeline_runner, "ENABLE_FIXTURE_ANALYSIS", True)
    monkeypatch.setattr(ai, "embed_texts", lambda texts: [[] for _ in texts])
    monkeypatch.setattr(
        ai,
        "answer_question",
        lambda *args, **kwargs: {
            "answer": "**Fixture answer.**",
            "citations": [],
            "suggested_prompts": ["What risks should I review?", "What deadlines matter?"],
        },
    )

    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
    auth = headers()
    response = client.post(
        "/api/v1/documents",
        headers=auth,
        files={"file": ("fixture.png", png, "image/png")},
    )
    assert response.status_code == 202
    document_id = response.json()["id"]

    status = "queued"
    for _ in range(100):
        processing = client.get(f"/api/v1/documents/{document_id}/processing", headers=auth)
        assert processing.status_code == 200
        status = processing.json()["status"]
        if status in {"completed", "failed"}:
            break

    document = client.get(f"/api/v1/documents/{document_id}", headers=auth)
    assert document.status_code == 200
    assert document.json()["status"] == "completed", f"expected completed, got {status}"

    chat = client.post(
        f"/api/v1/documents/{document_id}/chat",
        headers=auth,
        json={"message": "What is this document about?"},
    )
    assert chat.status_code == 200
    payload = chat.json()
    assert payload["answer"]
    assert payload["suggested_prompts"]
    assert payload["session_id"]


def test_chat_sessions_require_auth() -> None:
    response = client.get("/api/v1/chat/sessions")
    assert response.status_code == 401


def test_chat_session_lifecycle_and_history(monkeypatch) -> None:
    import app.main as main_module
    import app.pipeline_runner as pipeline_runner
    from app import ai

    monkeypatch.setattr(pipeline_runner, "AI_MODE", "demo")
    monkeypatch.setattr(pipeline_runner, "ENABLE_FIXTURE_ANALYSIS", True)
    monkeypatch.setattr(ai, "embed_texts", lambda texts: [[] for _ in texts])

    captured: dict[str, Any] = {}

    def fake_answer(*args, **kwargs):
        captured["history"] = kwargs.get("history")
        return {
            "answer": f"Reply to: {kwargs.get('history') and len(kwargs['history'])}",
            "citations": [],
            "suggested_prompts": ["Follow up one", "Follow up two"],
        }

    monkeypatch.setattr(main_module, "answer_question", fake_answer)

    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
    auth = headers()
    upload = client.post(
        "/api/v1/documents",
        headers=auth,
        files={"file": ("session-test.png", png, "image/png")},
    )
    assert upload.status_code == 202
    document_id = upload.json()["id"]
    for _ in range(100):
        processing = client.get(f"/api/v1/documents/{document_id}/processing", headers=auth)
        if processing.json()["status"] in {"completed", "failed"}:
            break

    create = client.post(
        "/api/v1/chat/sessions",
        headers=auth,
        json={"document_id": document_id},
    )
    assert create.status_code == 200
    session_id = create.json()["id"]

    first = client.post(
        f"/api/v1/documents/{document_id}/chat",
        headers=auth,
        json={"message": "What are the risks?", "session_id": session_id},
    )
    assert first.status_code == 200
    assert captured["history"] == []

    second = client.post(
        f"/api/v1/documents/{document_id}/chat",
        headers=auth,
        json={"message": "Explain the first one", "session_id": session_id},
    )
    assert second.status_code == 200
    assert captured["history"] is not None
    assert len(captured["history"]) == 2
    assert captured["history"][0]["role"] == "user"
    assert captured["history"][0]["content"] == "What are the risks?"
    assert captured["history"][1]["role"] == "assistant"

    sessions = client.get("/api/v1/chat/sessions", headers=auth)
    assert sessions.status_code == 200
    session_ids = [item["id"] for item in sessions.json()]
    assert session_id in session_ids
    assert sessions.json()[0]["title"] != "New chat"

    messages = client.get(f"/api/v1/chat/sessions/{session_id}/messages", headers=auth)
    assert messages.status_code == 200
    assert len(messages.json()) == 4

    other = client.post("/api/v1/chat/sessions", headers=auth, json={"document_id": document_id})
    other_id = other.json()["id"]
    isolated = client.get(f"/api/v1/chat/sessions/{other_id}/messages", headers=auth)
    assert isolated.status_code == 200
    assert isolated.json() == []

    delete = client.delete(f"/api/v1/chat/sessions/{other_id}", headers=auth)
    assert delete.status_code == 204


def _seed_completed_document(report: dict[str, Any]) -> str:
    document_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc).isoformat()
    with connect() as db:
        db.execute(
            "INSERT INTO documents (id,organization_id,name,content_type,size,status,stage,progress,risk_level,risk_score,classification,created_at,updated_at,storage_key,report_json) "
            "VALUES (?, ?, ?, ?, ?, 'completed', 'Complete', 100, ?, ?, ?, ?, ?, ?, ?)",
            (document_id, "demo-org", f"seed-{document_id[:8]}.json", "application/json", 1, report.get("risk_level", "medium"), report.get("risk_score", 50), "Contract", timestamp, timestamp, f"demo-org/{document_id}.json", json.dumps(report)),
        )
    return document_id


def test_action_items_are_persistent_and_scoped() -> None:
    document_id = _seed_completed_document({"risk_score": 40, "risk_level": "medium", "risks": [], "clauses": [], "deadlines": []})
    action_id = str(uuid.uuid4())
    with connect() as db:
        db.execute(
            "INSERT INTO action_items (id,document_id,title,detail,priority,status,due_date,ordinal) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (action_id, document_id, "Review renewal clause", "Confirm the notice period.", "high", "open", None, 0),
        )
    response = client.patch(f"/api/v1/action-items/{action_id}", headers=headers(), json={"status": "completed"})
    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    with connect() as db:
        assert db.execute("SELECT status FROM action_items WHERE id=?", (action_id,)).fetchone()[0] == "completed"


def test_reminders_are_scheduled_and_delivered_when_due() -> None:
    document_id = _seed_completed_document({"risk_score": 20, "risk_level": "low", "risks": [], "clauses": [], "deadlines": []})
    deadline_id = str(uuid.uuid4())
    with connect() as db:
        db.execute(
            "INSERT INTO deadlines (id,document_id,title,due_date,priority,source,timezone) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (deadline_id, document_id, "Renewal notice", "2099-01-20", "high", "Page 1", "UTC"),
        )
    auth = headers()
    response = client.post(f"/api/v1/deadlines/{deadline_id}/reminders", headers=auth, json={"channel": "in_app", "days_before": 7})
    assert response.status_code == 200
    assert response.json()["status"] == "scheduled"
    with connect() as db:
        assert db.execute("SELECT COUNT(*) FROM notifications WHERE related_deadline_id=?", (deadline_id,)).fetchone()[0] == 0
        db.execute("UPDATE reminders SET scheduled_for=? WHERE id=?", (datetime.now(timezone.utc).isoformat(), response.json()["id"]))
    assert process_due_reminders() >= 1
    with connect() as db:
        assert db.execute("SELECT status FROM reminders WHERE id=?", (response.json()["id"],)).fetchone()[0] == "delivered"
        assert db.execute("SELECT COUNT(*) FROM notifications WHERE related_deadline_id=?", (deadline_id,)).fetchone()[0] == 1


def test_report_download_pdf_default() -> None:
    report = {
        "summary": "Sample contract summary.",
        "classification": "Contract",
        "risk_score": 55,
        "risk_level": "medium",
        "confidence": 0.82,
        "entities": [{"label": "Party", "value": "Acme Corp", "confidence": 0.9, "page": 1, "text_span": None}],
        "risks": [{"title": "Auto-renewal", "severity": "medium", "explanation": "Renews automatically.", "recommendation": "Review notice period.", "source": "Section 4", "page": 2, "text_span": "auto-renew", "confidence": 0.8, "is_penalty": False}],
        "clauses": [],
        "obligations": [],
        "fraud_indicators": [],
        "deadlines": [{"title": "Renewal", "date": "2099-01-01", "priority": "high", "source": "Section 4"}],
        "recommendations": ["Review renewal terms."],
        "action_plan": [{"title": "Confirm notice", "detail": "Check calendar", "priority": "high", "due_date": None, "status": "open"}],
        "evidence": [{"label": "Renewal clause", "page": 2, "text_span": "auto-renew", "confidence": 0.85}],
    }
    document_id = _seed_completed_document(report)
    auth = headers()
    response = client.get(f"/api/v1/documents/{document_id}/report/download", headers=auth)
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content[:4] == b"%PDF"
    assert len(response.content) > 100


def test_report_download_json_format() -> None:
    report = {"summary": "JSON export test.", "classification": "Contract", "risk_score": 40, "risk_level": "medium", "confidence": 0.7, "risks": [], "clauses": [], "deadlines": [], "recommendations": []}
    document_id = _seed_completed_document(report)
    auth = headers()
    response = client.get(f"/api/v1/documents/{document_id}/report/download?format=json", headers=auth)
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    payload = response.json()
    assert payload["summary"] == "JSON export test."
    assert payload["risk_score"] == 40


def test_report_download_with_target_language(monkeypatch) -> None:
    import app.main as main_module

    captured: dict[str, Any] = {}

    def fake_translate(report: dict[str, Any], target_language: str) -> dict[str, Any]:
        captured["target_language"] = target_language
        return {**report, "summary": f"Translated ({target_language})"}

    monkeypatch.setattr(main_module, "translate_report", fake_translate)
    report = {"summary": "Original summary.", "classification": "Contract", "risk_score": 30, "risk_level": "low", "confidence": 0.6, "risks": [], "clauses": [], "deadlines": [], "recommendations": []}
    document_id = _seed_completed_document(report)
    auth = headers()
    response = client.get(
        f"/api/v1/documents/{document_id}/report/download?format=pdf&target_language=Hindi",
        headers=auth,
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert captured.get("target_language") == "Hindi"


def test_voice_summary_accepts_target_language(monkeypatch) -> None:
    import app.main as main_module

    captured: dict[str, Any] = {}

    def fake_speech(text: str, target_language: str | None = None) -> tuple[str, str | None]:
        captured["text"] = text
        captured["target_language"] = target_language
        return text, target_language

    monkeypatch.setattr(main_module, "speech_text_for_language", fake_speech)
    monkeypatch.setattr(main_module, "synthesize_speech", lambda text, target_language=None: b"audio-bytes")

    response = client.post(
        "/api/v1/voice-summary",
        headers=headers(),
        json={"text": "This is a summary.", "target_language": "Hindi"},
    )
    assert response.status_code == 200
    assert response.content == b"audio-bytes"
    assert response.headers["x-voice-language"] == "Hindi"
    assert captured["target_language"] == "Hindi"


def test_comparison_reports_score_delta_and_semantic_clause_changes() -> None:
    first = _seed_completed_document({"risk_score": 30, "risk_level": "low", "risks": [], "clauses": [{"title": "Termination", "body": "Thirty days notice.", "severity": "low", "category": "termination"}], "deadlines": []})
    second = _seed_completed_document({"risk_score": 70, "risk_level": "high", "risks": [{"title": "Late fee"}], "clauses": [{"title": "Termination of agreement", "body": "Seven days notice.", "severity": "high", "category": "termination"}], "deadlines": []})
    response = client.post("/api/v1/comparisons", headers=headers(), json={"document_a_id": first, "document_b_id": second})
    assert response.status_code == 200
    payload = response.json()
    assert payload["risk_score_delta"] == 40
    assert payload["risk_level_changed"] is True
    assert payload["modified_clauses"][0]["severity_changed"] is True
    assert payload["added_risks"] == ["Late fee"]
