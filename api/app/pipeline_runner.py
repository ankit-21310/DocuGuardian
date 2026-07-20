from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .ai import analyze_file, embed_texts
from .config import AI_MODE, ENABLE_FIXTURE_ANALYSIS, PIPELINE_STAGES
from .db import DB_LOCK, connect
from .parsing import chunk_text, extract_text, split_sections
from .storage import materialize_object


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


StageCallback = Callable[[str, int], None]


def run_pipeline(
    document_id: str,
    organization_id: str,
    storage_key: str,
    filename: str,
    upload_dir: Path,
    on_stage: StageCallback | None = None,
) -> dict[str, Any]:
    path = materialize_object(storage_key, upload_dir)
    intelligence: dict[str, Any] | None = None
    extracted = ""

    for index, stage in enumerate(PIPELINE_STAGES, 1):
        progress = round((index - 1) / len(PIPELINE_STAGES) * 100)
        if on_stage:
            on_stage(stage, progress)

        if stage == "OCR and parsing":
            extracted = extract_text(path, filename)
            with DB_LOCK, connect() as db:
                db.execute("UPDATE documents SET extracted_text=? WHERE id=?", (extracted, document_id))
        elif stage == "Classification":
            intelligence = _load_intelligence(path, filename, extracted)
            with DB_LOCK, connect() as db:
                db.execute(
                    "UPDATE documents SET classification=? WHERE id=?",
                    (intelligence.get("classification"), document_id),
                )
        elif stage == "Layout understanding":
            sections = split_sections(extracted or (intelligence or {}).get("summary", ""))
            _replace_children(document_id, "document_sections", [
                (str(uuid.uuid4()), document_id, section["heading"], section["content"], section.get("page"), section["ordinal"])
                for section in sections
            ], columns="id,document_id,heading,content,page,ordinal")
        elif stage == "Structured extraction":
            assert intelligence is not None
            _replace_children(document_id, "document_entities", [
                (
                    str(uuid.uuid4()), document_id, entity["label"], entity["value"],
                    entity.get("confidence"), entity.get("page"), entity.get("text_span"),
                )
                for entity in intelligence.get("entities", [])
            ], columns="id,document_id,label,value,confidence,page,text_span")
        elif stage == "Clause extraction":
            assert intelligence is not None
            _replace_children(document_id, "document_clauses", [
                (
                    str(uuid.uuid4()), document_id, clause["title"], clause["body"], clause["severity"],
                    clause.get("category", "general"), clause.get("page"), clause.get("text_span"), clause.get("confidence"),
                )
                for clause in intelligence.get("clauses", [])
            ], columns="id,document_id,title,body,severity,category,page,text_span,confidence")
        elif stage == "Risk analysis":
            assert intelligence is not None
            _replace_children(document_id, "document_risks", [
                (
                    str(uuid.uuid4()), document_id, risk["title"], risk["severity"], risk["explanation"],
                    risk["recommendation"], risk.get("source", "Document evidence"), risk.get("page"),
                    risk.get("text_span"), risk.get("confidence"), 1 if risk.get("is_penalty") else 0,
                )
                for risk in intelligence.get("risks", [])
            ], columns="id,document_id,title,severity,explanation,recommendation,source,page,text_span,confidence,is_penalty")
        elif stage == "Deadline detection":
            assert intelligence is not None
            with DB_LOCK, connect() as db:
                db.execute("DELETE FROM deadlines WHERE document_id=?", (document_id,))
                for deadline in intelligence.get("deadlines", []):
                    due_date = deadline.get("date") or deadline.get("due_date")
                    if not due_date:
                        continue
                    db.execute(
                        "INSERT INTO deadlines VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (
                            str(uuid.uuid4()), document_id, deadline["title"], due_date,
                            deadline["priority"], deadline.get("source", "Document evidence"),
                            deadline.get("timezone", "UTC"),
                        ),
                    )
        elif stage == "Recommendations":
            assert intelligence is not None
            _replace_children(document_id, "action_items", [
                (
                    str(uuid.uuid4()), document_id, item["title"], item["detail"], item["priority"],
                    "open", item.get("due_date"), ordinal,
                )
                for ordinal, item in enumerate(intelligence.get("action_plan", []))
            ], columns="id,document_id,title,detail,priority,status,due_date,ordinal")
        elif stage == "Embeddings":
            chunks = chunk_text(extracted or json.dumps(intelligence or {}))
            embeddings = embed_texts([chunk["content"] for chunk in chunks]) if chunks else []
            _replace_children(document_id, "document_chunks", [
                (
                    str(uuid.uuid4()), document_id, chunk["content"], chunk.get("page"), chunk["ordinal"],
                    json.dumps(embeddings[index]) if index < len(embeddings) else None,
                )
                for index, chunk in enumerate(chunks)
            ], columns="id,document_id,content,page,ordinal,embedding_json")
        elif stage == "Report generation":
            assert intelligence is not None
            report = _assemble_report(document_id, intelligence)
            score, level = int(report["risk_score"]), report["risk_level"]
            with DB_LOCK, connect() as db:
                db.execute(
                    "UPDATE documents SET status='completed',stage='Complete',progress=100,risk_level=?,risk_score=?,classification=?,report_json=?,updated_at=? WHERE id=?",
                    (level, score, report["classification"], json.dumps(report), now(), document_id),
                )
            if on_stage:
                on_stage("Complete", 100)
            return report

        completed_progress = round(index / len(PIPELINE_STAGES) * 100)
        if on_stage and stage != "Report generation":
            on_stage(stage, completed_progress)

    raise RuntimeError("Pipeline finished without report generation")


def _load_intelligence(path: Path, filename: str, extracted: str) -> dict[str, Any]:
    if AI_MODE == "demo":
        if not ENABLE_FIXTURE_ANALYSIS:
            raise RuntimeError("AI_MODE=demo is disabled. Set ENABLE_FIXTURE_ANALYSIS=true for fixture runs only.")
        return {
            "summary": f"{filename} was analyzed using explicit fixture analysis.",
            "classification": "Document",
            "risk_score": 42,
            "risk_level": "medium",
            "confidence": 0.5,
            "entities": [],
            "clauses": [],
            "risks": [],
            "deadlines": [],
            "recommendations": ["Review the source document manually."],
            "action_plan": [{"title": "Manual review", "detail": "Fixture mode produced limited findings.", "priority": "medium", "due_date": None}],
            "evidence": [],
            "model_version": "fixture",
        }
    return analyze_file(path, filename, extracted)


def _replace_children(document_id: str, table: str, rows: list[tuple], columns: str) -> None:
    with DB_LOCK, connect() as db:
        db.execute(f"DELETE FROM {table} WHERE document_id=?", (document_id,))
        placeholders = ", ".join("?" for _ in columns.split(","))
        for row in rows:
            db.execute(f"INSERT INTO {table} ({columns}) VALUES ({placeholders})", row)


def _assemble_report(document_id: str, intelligence: dict[str, Any]) -> dict[str, Any]:
    from .db import fetchall

    with connect() as db:
        clauses = fetchall(db.execute(
            "SELECT title,body,severity,category,page,text_span,confidence FROM document_clauses WHERE document_id=?",
            (document_id,),
        ))
        risks = fetchall(db.execute(
            "SELECT title,severity,explanation,recommendation,source,page,text_span,confidence,is_penalty FROM document_risks WHERE document_id=?",
            (document_id,),
        ))
        action_plan = fetchall(db.execute(
            "SELECT title,detail,priority,due_date,status FROM action_items WHERE document_id=? ORDER BY ordinal",
            (document_id,),
        ))
        entities = fetchall(db.execute(
            "SELECT label,value,confidence,page,text_span FROM document_entities WHERE document_id=?",
            (document_id,),
        ))

    report_risks = [
        {
            "title": risk["title"],
            "severity": risk["severity"],
            "explanation": risk["explanation"],
            "recommendation": risk["recommendation"],
            "source": risk["source"],
            "page": risk["page"],
            "text_span": risk["text_span"],
            "confidence": risk["confidence"],
            "is_penalty": bool(risk["is_penalty"]),
        }
        for risk in risks
    ] or intelligence.get("risks", [])

    return {
        "summary": intelligence.get("summary", ""),
        "classification": intelligence.get("classification", "Document"),
        "risk_score": int(intelligence.get("risk_score", 0)),
        "risk_level": intelligence.get("risk_level", "low"),
        "confidence": intelligence.get("confidence", 0.5),
        "entities": entities or intelligence.get("entities", []),
        "clauses": clauses or intelligence.get("clauses", []),
        "risks": report_risks,
        "hidden_penalties": [risk for risk in report_risks if risk.get("is_penalty")],
        "deadlines": intelligence.get("deadlines", []),
        "recommendations": intelligence.get("recommendations", []),
        "action_plan": [
            {"title": item["title"], "detail": item["detail"], "priority": item["priority"], "due_date": item.get("due_date"), "status": item.get("status", "open")}
            for item in action_plan
        ] or intelligence.get("action_plan", []),
        "evidence": intelligence.get("evidence", []),
        "model_version": intelligence.get("model_version", "unknown"),
    }
