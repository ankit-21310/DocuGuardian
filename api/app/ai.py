from __future__ import annotations

import json
import math
import os
import re
from pathlib import Path
from typing import Any

from openai import OpenAI

from .config import EMBEDDING_MODEL, OPENAI_MODEL


def client() -> OpenAI:
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not configured. Real document analysis cannot run.")
    return OpenAI()


INTELLIGENCE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "summary": {"type": "string"},
        "classification": {"type": "string"},
        "risk_score": {"type": "integer", "minimum": 0, "maximum": 100},
        "risk_level": {"type": "string", "enum": ["low", "medium", "high"]},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "entities": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "label": {"type": "string"},
                    "value": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "page": {"type": ["integer", "null"], "minimum": 1},
                    "text_span": {"type": ["string", "null"]},
                },
                "required": ["label", "value", "confidence", "page", "text_span"],
            },
        },
        "clauses": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "title": {"type": "string"},
                    "body": {"type": "string"},
                    "severity": {"type": "string", "enum": ["low", "medium", "high"]},
                    "category": {"type": "string"},
                    "page": {"type": ["integer", "null"], "minimum": 1},
                    "text_span": {"type": ["string", "null"]},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
                "required": ["title", "body", "severity", "category", "page", "text_span", "confidence"],
            },
        },
        "risks": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "title": {"type": "string"},
                    "severity": {"type": "string", "enum": ["low", "medium", "high"]},
                    "explanation": {"type": "string"},
                    "recommendation": {"type": "string"},
                    "source": {"type": "string"},
                    "page": {"type": ["integer", "null"], "minimum": 1},
                    "text_span": {"type": ["string", "null"]},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "is_penalty": {"type": "boolean"},
                },
                "required": ["title", "severity", "explanation", "recommendation", "source", "page", "text_span", "confidence", "is_penalty"],
            },
        },
        "obligations": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "title": {"type": "string"},
                    "party": {"type": "string"},
                    "description": {"type": "string"},
                    "severity": {"type": "string", "enum": ["low", "medium", "high"]},
                    "due_date": {"type": ["string", "null"]},
                    "page": {"type": ["integer", "null"], "minimum": 1},
                    "text_span": {"type": ["string", "null"]},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
                "required": ["title", "party", "description", "severity", "due_date", "page", "text_span", "confidence"],
            },
        },
        "fraud_indicators": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "title": {"type": "string"},
                    "indicator_type": {
                        "type": "string",
                        "enum": [
                            "missing_signature",
                            "inconsistent_dates",
                            "suspicious_terms",
                            "unverified_party",
                            "altered_document",
                            "misleading_claims",
                        ],
                    },
                    "severity": {"type": "string", "enum": ["low", "medium", "high"]},
                    "explanation": {"type": "string"},
                    "page": {"type": ["integer", "null"], "minimum": 1},
                    "text_span": {"type": ["string", "null"]},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
                "required": ["title", "indicator_type", "severity", "explanation", "page", "text_span", "confidence"],
            },
        },
        "deadlines": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "title": {"type": "string"},
                    "date": {"type": "string"},
                    "priority": {"type": "string", "enum": ["low", "medium", "high"]},
                    "source": {"type": "string"},
                    "timezone": {"type": "string"},
                    "page": {"type": ["integer", "null"], "minimum": 1},
                    "text_span": {"type": ["string", "null"]},
                },
                "required": ["title", "date", "priority", "source", "timezone", "page", "text_span"],
            },
        },
        "recommendations": {"type": "array", "items": {"type": "string"}},
        "action_plan": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "title": {"type": "string"},
                    "detail": {"type": "string"},
                    "priority": {"type": "string", "enum": ["low", "medium", "high"]},
                    "due_date": {"type": ["string", "null"]},
                },
                "required": ["title", "detail", "priority", "due_date"],
            },
        },
        "evidence": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "page": {"type": ["integer", "null"], "minimum": 1},
                    "text_span": {"type": "string"},
                    "label": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
                "required": ["page", "text_span", "label", "confidence"],
            },
        },
        "model_version": {"type": "string"},
    },
    "required": [
        "summary",
        "classification",
        "risk_score",
        "risk_level",
        "confidence",
        "entities",
        "clauses",
        "risks",
        "obligations",
        "fraud_indicators",
        "deadlines",
        "recommendations",
        "action_plan",
        "evidence",
        "model_version",
    ],
}


def analyze_document_text(text: str, filename: str) -> dict[str, Any]:
    api = client()
    truncated = text[:120_000] if text else f"(No extractable text for {filename}; classify conservatively.)"
    response = api.responses.create(
        model=OPENAI_MODEL,
        input=[{
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": (
                        f"Analyze the document `{filename}` for DocuGuardian. Use ONLY evidence present in the text. "
                        "Return classification, entities, clauses with severity, risks (set is_penalty true for hidden fees/"
                        "penalties/liquidated damages), party-specific obligations (payment, notice, insurance, confidentiality), "
                        "fraud_indicators for missing signatures, inconsistent dates, suspicious terms, or unverified parties, "
                        "deadlines as YYYY-MM-DD when possible, recommendations, a concrete "
                        "action_plan checklist, and evidence spans with pages when available. "
                        f"Return model_version as `{OPENAI_MODEL}`. Decision support only, not professional advice.\n\n"
                        f"DOCUMENT TEXT:\n{truncated}"
                    ),
                }
            ],
        }],
        text={"format": {"type": "json_schema", "name": "document_intelligence", "strict": True, "schema": INTELLIGENCE_SCHEMA}},
    )
    return json.loads(response.output_text)


def analyze_file(path: Path, filename: str, extracted_text: str | None = None, *, force_vision: bool = False) -> dict[str, Any]:
    if (
        not force_vision
        and extracted_text
        and extracted_text.strip()
        and not extracted_text.startswith("[Image document:")
        and not extracted_text.startswith("[OCR fallback:")
    ):
        return analyze_document_text(extracted_text, filename)
    api = client()
    uploaded = api.files.create(file=path.open("rb"), purpose="user_data")
    try:
        response = api.responses.create(
            model=OPENAI_MODEL,
            input=[{
                "role": "user",
                "content": [
                    {"type": "input_file", "file_id": uploaded.id},
                    {
                        "type": "input_text",
                        "text": (
                            f"Analyze {filename} as DocuGuardian. Extract only evidence present in the document. "
                            "Include entities, clauses with severity, risks with is_penalty for hidden penalties, "
                            "obligations with party and due dates, fraud_indicators when evidence supports them, "
                            "deadlines, recommendations, action_plan, and evidence. "
                            f"Return model_version as `{OPENAI_MODEL}`."
                        ),
                    },
                ],
            }],
            text={"format": {"type": "json_schema", "name": "document_intelligence", "strict": True, "schema": INTELLIGENCE_SCHEMA}},
        )
        return json.loads(response.output_text)
    finally:
        try:
            api.files.delete(uploaded.id)
        except Exception:
            pass


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    api = client()
    response = api.embeddings.create(model=EMBEDDING_MODEL, input=texts)
    return [item.embedding for item in response.data]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


def retrieve_chunks(question: str, chunks: list[dict[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
    if not chunks:
        return []
    try:
        query_embedding = embed_texts([question])[0]
        scored = []
        for chunk in chunks:
            embedding = chunk.get("embedding") or []
            if isinstance(embedding, str):
                embedding = json.loads(embedding)
            score = cosine_similarity(query_embedding, embedding) if embedding else 0.0
            if score == 0.0:
                score = _lexical_score(question, chunk.get("content", ""))
            scored.append((score, chunk))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [chunk for score, chunk in scored[:limit] if score > 0]
    except Exception:
        scored = [(_lexical_score(question, chunk.get("content", "")), chunk) for chunk in chunks]
        scored.sort(key=lambda item: item[0], reverse=True)
        return [chunk for score, chunk in scored[:limit] if score > 0]


CHAT_RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "answer": {"type": "string"},
        "suggested_prompts": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 2,
            "maxItems": 4,
        },
    },
    "required": ["answer", "suggested_prompts"],
}


def _format_citation_label(content: str, limit: int = 140) -> str:
    cleaned = re.sub(r"\s+", " ", content or "").strip()
    cleaned = re.sub(r"^Page\s+\d+\s+of\s+\d+\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^Document\s+No\.?\s*[\d/]+\s*", "", cleaned, flags=re.IGNORECASE)
    if len(cleaned) <= limit:
        return cleaned
    cut = cleaned[:limit]
    last_space = cut.rfind(" ")
    if last_space > 70:
        cut = cut[:last_space]
    return f"{cut.rstrip()}…"


def _default_suggested_prompts(report: dict[str, Any], question: str) -> list[str]:
    prompts: list[str] = []
    if report.get("risks"):
        prompts.append("Which risks need attention first?")
    if report.get("deadlines"):
        prompts.append("What deadlines should I calendar?")
    if report.get("clauses"):
        prompts.append("Explain the most important clauses in plain language.")
    if len(prompts) < 2:
        prompts.extend(["What should I do next?", "Summarize this document in simple terms."])
    filtered = [item for item in prompts if item.lower() not in question.lower()]
    return (filtered or prompts)[:3]


def _lexical_score(question: str, content: str) -> float:
    terms = {term for term in re.findall(r"[a-z0-9]{3,}", question.lower())}
    if not terms:
        return 0.0
    haystack = content.lower()
    hits = sum(1 for term in terms if term in haystack)
    return hits / len(terms)


def answer_question(
    filename: str,
    report: dict[str, Any],
    question: str,
    retrieved_chunks: list[dict[str, Any]] | None = None,
    target_language: str | None = None,
    history: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    api = client()
    chunk_context = "\n\n".join(
        f"[chunk {index + 1} page={chunk.get('page')}] {chunk.get('content', '')[:1200]}"
        for index, chunk in enumerate(retrieved_chunks or [])
    )
    evidence = report.get("evidence", [])
    context = {
        "summary": report.get("summary"),
        "classification": report.get("classification"),
        "risks": report.get("risks", [])[:12],
        "deadlines": report.get("deadlines", [])[:12],
        "clauses": report.get("clauses", [])[:12],
        "action_plan": report.get("action_plan", [])[:12],
        "evidence": evidence[:12],
    }
    language_instruction = ""
    if target_language and target_language.strip().lower() not in {"english", "en"}:
        language_instruction = (
            f" Write both `answer` and every item in `suggested_prompts` in {target_language.strip()}. "
            "Keep source labels in their original language when needed for traceability."
        )
    llm_input: list[dict[str, str]] = [
        {
            "role": "developer",
            "content": (
                "You are DocuGuardian. Answer only from the provided report and retrieved document chunks. "
                "If the answer is not present, say so clearly. Cite concrete source labels. "
                "Never present legal, medical, or financial advice as certainty. "
                "Format `answer` in Markdown with short paragraphs, bullet lists for multiple items, "
                "and **bold** for key terms, dates, and risks. "
                "Return 2-3 concise follow-up questions in `suggested_prompts` that help the user dig deeper "
                f"into this specific document. Do not repeat the user's question.{language_instruction}"
            ),
        },
    ]
    for turn in history or []:
        role = turn.get("role", "")
        content = str(turn.get("content", "")).strip()
        if not content:
            continue
        llm_role = "assistant" if role == "assistant" else "user"
        llm_input.append({"role": llm_role, "content": content})
    llm_input.append(
        {
            "role": "user",
            "content": (
                f"Document: {filename}\nExtracted report: {json.dumps(context, ensure_ascii=False)}\n"
                f"Retrieved chunks:\n{chunk_context or '(none)'}\nQuestion: {question}"
            ),
        },
    )
    response = api.responses.create(
        model=OPENAI_MODEL,
        input=llm_input,
        text={"format": {"type": "json_schema", "name": "chat_response", "strict": True, "schema": CHAT_RESPONSE_SCHEMA}},
    )
    try:
        payload = json.loads(response.output_text)
        answer_text = str(payload.get("answer", "")).strip()
        suggested_prompts = [
            str(item).strip()
            for item in payload.get("suggested_prompts", [])
            if str(item).strip()
        ][:4]
    except json.JSONDecodeError:
        answer_text = response.output_text.strip()
        suggested_prompts = _default_suggested_prompts(report, question)
    if not suggested_prompts:
        suggested_prompts = _default_suggested_prompts(report, question)
    citations: list[dict[str, Any]] = []
    answer_lower = answer_text.lower()
    for chunk in retrieved_chunks or []:
        snippet = _format_citation_label(chunk.get("content") or "")
        if snippet and any(token in answer_lower for token in snippet.lower().split()[:6]):
            citations.append({"label": snippet, "page": chunk.get("page"), "confidence": report.get("confidence", 0.8)})
    for item in evidence:
        label = _format_citation_label(item.get("label") or item.get("text_span", ""))
        if label and label.lower()[:40] in answer_lower or any(
            word in answer_lower for word in re.findall(r"[a-z]{5,}", (label or "").lower())[:3]
        ):
            citations.append(
                {
                    "label": label,
                    "page": item.get("page"),
                    "confidence": item.get("confidence", report.get("confidence", 0.8)),
                }
            )
    if not citations:
        for item in (retrieved_chunks or [])[:3]:
            citations.append({"label": _format_citation_label(item.get("content") or ""), "page": item.get("page"), "confidence": report.get("confidence", 0.8)})
        for item in evidence[:2]:
            citations.append(
                {
                    "label": _format_citation_label(item.get("label") or item.get("text_span", "Document evidence")),
                    "page": item.get("page"),
                    "confidence": item.get("confidence", report.get("confidence", 0.8)),
                }
            )
    # Deduplicate citations
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for citation in citations:
        key = f"{citation.get('label')}|{citation.get('page')}"
        if key in seen:
            continue
        seen.add(key)
        unique.append(citation)
    return {"answer": answer_text, "citations": unique[:5], "suggested_prompts": suggested_prompts}


def translate_text(text: str, target_language: str) -> str:
    api = client()
    response = api.responses.create(
        model=OPENAI_MODEL,
        input=[{
            "role": "user",
            "content": f"Translate the following decision-support summary into {target_language}. Keep meaning faithful.\n\n{text}",
        }],
    )
    return response.output_text


TRANSLATED_REPORT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "summary": {"type": "string"},
        "classification": {"type": "string"},
        "risks": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "title": {"type": "string"},
                    "explanation": {"type": "string"},
                    "recommendation": {"type": "string"},
                },
                "required": ["title", "explanation", "recommendation"],
            },
        },
        "clauses": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {"title": {"type": "string"}, "body": {"type": "string"}},
                "required": ["title", "body"],
            },
        },
        "obligations": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {"title": {"type": "string"}, "description": {"type": "string"}, "party": {"type": "string"}},
                "required": ["title", "description", "party"],
            },
        },
        "fraud_indicators": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {"title": {"type": "string"}, "explanation": {"type": "string"}},
                "required": ["title", "explanation"],
            },
        },
        "deadlines": {"type": "array", "items": {"type": "object", "additionalProperties": False, "properties": {"title": {"type": "string"}}, "required": ["title"]}},
        "recommendations": {"type": "array", "items": {"type": "string"}},
        "action_plan": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {"title": {"type": "string"}, "detail": {"type": "string"}},
                "required": ["title", "detail"],
            },
        },
    },
    "required": ["summary", "classification", "risks", "clauses", "obligations", "fraud_indicators", "deadlines", "recommendations", "action_plan"],
}


def translate_report(report: dict[str, Any], target_language: str) -> dict[str, Any]:
    """Translate user-facing report text while retaining source metadata."""
    api = client()
    translatable = {
        "summary": report.get("summary", ""),
        "classification": report.get("classification", ""),
        "risks": [
            {key: risk.get(key, "") for key in ("title", "explanation", "recommendation")}
            for risk in report.get("risks", [])
        ],
        "clauses": [{"title": clause.get("title", ""), "body": clause.get("body", "")} for clause in report.get("clauses", [])],
        "obligations": [
            {"title": item.get("title", ""), "description": item.get("description", ""), "party": item.get("party", "")}
            for item in report.get("obligations", [])
        ],
        "fraud_indicators": [
            {"title": item.get("title", ""), "explanation": item.get("explanation", "")}
            for item in report.get("fraud_indicators", [])
        ],
        "deadlines": [{"title": deadline.get("title", "")} for deadline in report.get("deadlines", [])],
        "recommendations": report.get("recommendations", []),
        "action_plan": [{"title": item.get("title", ""), "detail": item.get("detail", "")} for item in report.get("action_plan", [])],
    }
    response = api.responses.create(
        model=OPENAI_MODEL,
        input=[{
            "role": "user",
            "content": (
                f"Translate this DocuGuardian report into {target_language}. Translate only human-readable text. "
                "Keep dates, numbers, severity labels, source citations, and evidence traceability unchanged. "
                f"Return the same array lengths and order.\n\n{json.dumps(translatable, ensure_ascii=False)}"
            ),
        }],
        text={"format": {"type": "json_schema", "name": "translated_report", "strict": True, "schema": TRANSLATED_REPORT_SCHEMA}},
    )
    try:
        translated = json.loads(response.output_text)
    except json.JSONDecodeError as error:
        raise RuntimeError("The translation service returned an invalid report") from error

    result = dict(report)
    result["summary"] = translated.get("summary", result.get("summary", ""))
    result["classification"] = translated.get("classification", result.get("classification", ""))
    original_risks = report.get("risks", [])
    result["risks"] = [
        {**risk, **translated_risk}
        for risk, translated_risk in zip(original_risks, translated.get("risks", []))
    ]
    original_clauses = report.get("clauses", [])
    result["clauses"] = [
        {**clause, **translated_clause}
        for clause, translated_clause in zip(original_clauses, translated.get("clauses", []))
    ]
    original_obligations = report.get("obligations", [])
    result["obligations"] = [
        {**item, **translated_item}
        for item, translated_item in zip(original_obligations, translated.get("obligations", []))
    ]
    original_fraud = report.get("fraud_indicators", [])
    result["fraud_indicators"] = [
        {**item, **translated_item}
        for item, translated_item in zip(original_fraud, translated.get("fraud_indicators", []))
    ]
    original_deadlines = report.get("deadlines", [])
    result["deadlines"] = [
        {**deadline, **translated_deadline}
        for deadline, translated_deadline in zip(original_deadlines, translated.get("deadlines", []))
    ]
    result["recommendations"] = translated.get("recommendations", result.get("recommendations", []))
    original_actions = report.get("action_plan", [])
    result["action_plan"] = [
        {**item, **translated_item}
        for item, translated_item in zip(original_actions, translated.get("action_plan", []))
    ]
    result["hidden_penalties"] = [risk for risk in result["risks"] if risk.get("is_penalty")]
    return result


def _normalize_language(language: str | None) -> str | None:
    if not language:
        return None
    cleaned = language.strip()
    if cleaned.lower() in {"english", "en"}:
        return None
    return cleaned


def synthesize_speech(text: str, target_language: str | None = None) -> bytes:
    api = client()
    language = _normalize_language(target_language)
    payload: dict[str, Any] = {
        "model": "gpt-4o-mini-tts",
        "voice": "alloy",
        "input": text[:4000],
    }
    if language:
        payload["instructions"] = f"Speak naturally in {language} with clear pronunciation suitable for a document summary."
    speech = api.audio.speech.create(**payload)
    return speech.content


def speech_text_for_language(text: str, target_language: str | None) -> tuple[str, str | None]:
    """Return text prepared for TTS and the spoken language label."""
    language = _normalize_language(target_language)
    if not language:
        return text[:4000], None
    translated = translate_text(text[:4000], language)
    return translated[:4000], language
