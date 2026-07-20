from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from openai import OpenAI


MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")


def client() -> OpenAI:
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not configured. Real document analysis cannot run.")
    return OpenAI()


REPORT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "summary": {"type": "string"},
        "classification": {"type": "string"},
        "risk_score": {"type": "integer", "minimum": 0, "maximum": 100},
        "risk_level": {"type": "string", "enum": ["low", "medium", "high"]},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "risks": {"type": "array", "items": {"type": "object", "additionalProperties": False, "properties": {"title": {"type": "string"}, "severity": {"type": "string", "enum": ["low", "medium", "high"]}, "explanation": {"type": "string"}, "recommendation": {"type": "string"}, "source": {"type": "string"}, "page": {"type": ["integer", "null"], "minimum": 1}, "text_span": {"type": ["string", "null"]}, "confidence": {"type": "number", "minimum": 0, "maximum": 1}}, "required": ["title", "severity", "explanation", "recommendation", "source", "page", "text_span", "confidence"]}},
        "deadlines": {"type": "array", "items": {"type": "object", "additionalProperties": False, "properties": {"title": {"type": "string"}, "date": {"type": "string"}, "priority": {"type": "string", "enum": ["low", "medium", "high"]}, "source": {"type": "string"}, "timezone": {"type": "string"}, "page": {"type": ["integer", "null"], "minimum": 1}, "text_span": {"type": ["string", "null"]}}, "required": ["title", "date", "priority", "source", "timezone", "page", "text_span"]}},
        "recommendations": {"type": "array", "items": {"type": "string"}},
        "evidence": {"type": "array", "items": {"type": "object", "additionalProperties": False, "properties": {"page": {"type": ["integer", "null"], "minimum": 1}, "text_span": {"type": "string"}, "label": {"type": "string"}, "confidence": {"type": "number", "minimum": 0, "maximum": 1}}, "required": ["page", "text_span", "label", "confidence"]}},
        "model_version": {"type": "string"},
    },
    "required": ["summary", "classification", "risk_score", "risk_level", "confidence", "risks", "deadlines", "recommendations", "evidence", "model_version"],
}


def analyze_file(path: Path, filename: str) -> dict[str, Any]:
    api = client()
    uploaded = api.files.create(file=path.open("rb"), purpose="user_data")
    try:
        response = api.responses.create(
            model=MODEL,
            input=[{"role": "user", "content": [
                {"type": "input_file", "file_id": uploaded.id},
                {"type": "input_text", "text": f"Analyze {filename} as a document intelligence system. Extract only evidence present in the document. Cite page numbers and exact text spans for every finding; use null page only when the document has no page concept. Identify legal, financial, privacy, operational, or safety risks, normalize dates as YYYY-MM-DD when possible, provide confidence for each finding, and provide practical next actions. Return model_version as the configured model name. This is decision support, not professional advice."},
            ]}],
            text={"format": {"type": "json_schema", "name": "document_report", "strict": True, "schema": REPORT_SCHEMA}},
        )
        return json.loads(response.output_text)
    finally:
        try:
            api.files.delete(uploaded.id)
        except Exception:
            pass


def answer_question(filename: str, report: dict[str, Any], question: str) -> dict[str, Any]:
    api = client()
    context = json.dumps(report, ensure_ascii=False)
    response = api.responses.create(
        model=MODEL,
        input=[{"role": "developer", "content": "You are DocuGuardian. Answer only from the provided extracted report. If the report does not contain the answer, say that clearly. Include a short source citation label and never present legal, medical, or financial advice as a certainty."}, {"role": "user", "content": f"Document: {filename}\nExtracted report: {context}\nQuestion: {question}"}],
    )
    citations = [
        {"label": evidence.get("label") or evidence.get("text_span", "Document evidence"), "page": evidence.get("page"), "confidence": evidence.get("confidence", report.get("confidence", 0.8))}
        for evidence in report.get("evidence", [])[:5]
    ]
    if not citations:
        citations = [{"label": "Extracted report · source citations preserved", "confidence": report.get("confidence", 0.8)}]
    return {"answer": response.output_text, "citations": citations}
