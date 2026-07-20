from __future__ import annotations

import io
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

_FONT_NAME = "ReportBody"
_FONT_REGISTERED = False

_FONT_CANDIDATES = (
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("/usr/share/fonts/TTF/DejaVuSans.ttf"),
    Path("C:/Windows/Fonts/arial.ttf"),
    Path("C:/Windows/Fonts/DejaVuSans.ttf"),
)


def _register_font() -> str:
    global _FONT_REGISTERED
    if _FONT_REGISTERED:
        return _FONT_NAME
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    for candidate in _FONT_CANDIDATES:
        if candidate.is_file():
            pdfmetrics.registerFont(TTFont(_FONT_NAME, str(candidate)))
            _FONT_REGISTERED = True
            return _FONT_NAME
    _FONT_REGISTERED = True
    return "Helvetica"


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _severity_color(severity: str) -> colors.Color:
    normalized = severity.lower()
    if normalized == "high":
        return colors.HexColor("#dc2626")
    if normalized == "medium":
        return colors.HexColor("#d97706")
    return colors.HexColor("#059669")


def _styles(font_name: str) -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "ReportTitle",
            parent=base["Heading1"],
            fontName=font_name,
            fontSize=18,
            leading=22,
            textColor=colors.HexColor("#1e40af"),
            spaceAfter=8,
        ),
        "subtitle": ParagraphStyle(
            "ReportSubtitle",
            parent=base["Normal"],
            fontName=font_name,
            fontSize=10,
            leading=14,
            textColor=colors.HexColor("#52627c"),
            spaceAfter=12,
        ),
        "section": ParagraphStyle(
            "ReportSection",
            parent=base["Heading2"],
            fontName=font_name,
            fontSize=13,
            leading=16,
            textColor=colors.HexColor("#1e40af"),
            spaceBefore=14,
            spaceAfter=8,
        ),
        "body": ParagraphStyle(
            "ReportBody",
            parent=base["Normal"],
            fontName=font_name,
            fontSize=10,
            leading=14,
            alignment=TA_LEFT,
            spaceAfter=6,
        ),
        "muted": ParagraphStyle(
            "ReportMuted",
            parent=base["Normal"],
            fontName=font_name,
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#64748b"),
            spaceAfter=4,
        ),
        "item_title": ParagraphStyle(
            "ReportItemTitle",
            parent=base["Normal"],
            fontName=font_name,
            fontSize=10,
            leading=13,
            textColor=colors.HexColor("#0f172a"),
            spaceAfter=2,
        ),
    }


def _section(story: list[Any], styles: dict[str, ParagraphStyle], title: str, items: list[Any], renderer) -> None:
    if not items:
        return
    story.append(Paragraph(_safe_text(title), styles["section"]))
    for item in items:
        renderer(story, styles, item)
    story.append(Spacer(1, 4))


def render_report_pdf(document_name: str, report: dict[str, Any]) -> bytes:
    font_name = _register_font()
    styles = _styles(font_name)
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
        title=f"{document_name} — Intelligence Report",
    )
    story: list[Any] = []

    risk_score = report.get("risk_score", 0)
    risk_level = _safe_text(report.get("risk_level", "unknown"))
    classification = _safe_text(report.get("classification", "Document"))
    confidence = round(float(report.get("confidence", 0)) * 100)

    story.append(Paragraph(_safe_text(document_name), styles["title"]))
    story.append(
        Paragraph(
            f"Classification: {classification} · Risk score: {risk_score}/100 ({risk_level}) · Confidence: {confidence}%",
            styles["subtitle"],
        )
    )

    summary = report.get("summary")
    if summary:
        story.append(Paragraph("Summary", styles["section"]))
        story.append(Paragraph(_safe_text(summary), styles["body"]))

    def render_entity(story: list[Any], styles: dict[str, ParagraphStyle], entity: dict[str, Any]) -> None:
        label = _safe_text(entity.get("label"))
        value = _safe_text(entity.get("value"))
        story.append(Paragraph(f"<b>{label}</b>: {value}", styles["item_title"]))
        citation = []
        if entity.get("page"):
            citation.append(f"page {entity['page']}")
        if entity.get("text_span"):
            citation.append(f'"{_safe_text(entity["text_span"])}"')
        if entity.get("confidence") is not None:
            citation.append(f"{round(float(entity['confidence']) * 100)}% confidence")
        if citation:
            story.append(Paragraph(" · ".join(citation), styles["muted"]))

    _section(story, styles, "Key details", report.get("entities") or [], render_entity)

    def render_risk(story: list[Any], styles: dict[str, ParagraphStyle], risk: dict[str, Any]) -> None:
        severity = _safe_text(risk.get("severity", "low"))
        color = _severity_color(severity).hexval()
        title = _safe_text(risk.get("title"))
        penalty = " · penalty" if risk.get("is_penalty") else ""
        story.append(Paragraph(f'<b>{title}{penalty}</b> <font color="{color}">[{severity}]</font>', styles["item_title"]))
        if risk.get("explanation"):
            story.append(Paragraph(_safe_text(risk["explanation"]), styles["body"]))
        if risk.get("recommendation"):
            story.append(Paragraph(f"Recommendation: {_safe_text(risk['recommendation'])}", styles["muted"]))
        citation = []
        if risk.get("source"):
            citation.append(_safe_text(risk["source"]))
        if risk.get("page"):
            citation.append(f"page {risk['page']}")
        if risk.get("text_span"):
            citation.append(f'"{_safe_text(risk["text_span"])}"')
        if citation:
            story.append(Paragraph(" · ".join(citation), styles["muted"]))

    _section(story, styles, "Risk analysis", report.get("risks") or [], render_risk)

    penalties = report.get("hidden_penalties") or []
    if penalties:
        _section(story, styles, "Hidden penalties", penalties, render_risk)

    def render_clause(story: list[Any], styles: dict[str, ParagraphStyle], clause: dict[str, Any]) -> None:
        severity = _safe_text(clause.get("severity", "low"))
        color = _severity_color(severity).hexval()
        story.append(Paragraph(f'<b>{_safe_text(clause.get("title"))}</b> <font color="{color}">[{severity}]</font>', styles["item_title"]))
        if clause.get("body"):
            story.append(Paragraph(_safe_text(clause["body"]), styles["body"]))
        citation = [_safe_text(clause.get("category", ""))]
        if clause.get("page"):
            citation.append(f"page {clause['page']}")
        if clause.get("text_span"):
            citation.append(f'"{_safe_text(clause["text_span"])}"')
        story.append(Paragraph(" · ".join(part for part in citation if part), styles["muted"]))

    _section(story, styles, "Clauses", report.get("clauses") or [], render_clause)

    def render_obligation(story: list[Any], styles: dict[str, ParagraphStyle], item: dict[str, Any]) -> None:
        severity = _safe_text(item.get("severity", "low"))
        color = _severity_color(severity).hexval()
        story.append(Paragraph(f'<b>{_safe_text(item.get("title"))}</b> <font color="{color}">[{severity}]</font>', styles["item_title"]))
        if item.get("description"):
            story.append(Paragraph(_safe_text(item["description"]), styles["body"]))
        citation = [f"Party: {_safe_text(item.get('party', ''))}"]
        if item.get("due_date"):
            citation.append(f"due {item['due_date']}")
        if item.get("page"):
            citation.append(f"page {item['page']}")
        if item.get("text_span"):
            citation.append(f'"{_safe_text(item["text_span"])}"')
        story.append(Paragraph(" · ".join(part for part in citation if part), styles["muted"]))

    _section(story, styles, "Obligations", report.get("obligations") or [], render_obligation)

    def render_fraud(story: list[Any], styles: dict[str, ParagraphStyle], item: dict[str, Any]) -> None:
        severity = _safe_text(item.get("severity", "low"))
        color = _severity_color(severity).hexval()
        story.append(
            Paragraph(
                f'<b>{_safe_text(item.get("title"))}</b> <font color="{color}">[{_safe_text(item.get("indicator_type", ""))}]</font>',
                styles["item_title"],
            )
        )
        if item.get("explanation"):
            story.append(Paragraph(_safe_text(item["explanation"]), styles["body"]))

    fraud = report.get("fraud_indicators") or []
    if fraud:
        story.append(Paragraph("Fraud indicators", styles["section"]))
        story.append(Paragraph("Assistive signals only—not proof of fraud or legal findings.", styles["muted"]))
        for item in fraud:
            render_fraud(story, styles, item)

    def render_deadline(story: list[Any], styles: dict[str, ParagraphStyle], deadline: dict[str, Any]) -> None:
        story.append(Paragraph(f"<b>{_safe_text(deadline.get('title'))}</b>", styles["item_title"]))
        parts = [
            _safe_text(deadline.get("date", "")),
            f"{_safe_text(deadline.get('priority', ''))} priority",
            _safe_text(deadline.get("source", "")),
        ]
        story.append(Paragraph(" · ".join(part for part in parts if part), styles["muted"]))

    _section(story, styles, "Deadlines", report.get("deadlines") or [], render_deadline)

    def render_action(story: list[Any], styles: dict[str, ParagraphStyle], item: dict[str, Any]) -> None:
        checked = "☑" if item.get("status") == "completed" else "☐"
        title = _safe_text(item.get("title"))
        detail = _safe_text(item.get("detail", ""))
        priority = _safe_text(item.get("priority", ""))
        due = f" · due {item['due_date']}" if item.get("due_date") else ""
        story.append(Paragraph(f"{checked} <b>{title}</b> — {detail} · {priority}{due}", styles["body"]))

    _section(story, styles, "Action plan", report.get("action_plan") or [], render_action)

    recommendations = report.get("recommendations") or []
    if recommendations:
        story.append(Paragraph("Recommendations", styles["section"]))
        for item in recommendations:
            story.append(Paragraph(f"• {_safe_text(item)}", styles["body"]))

    evidence = report.get("evidence") or []
    if evidence:
        story.append(Paragraph("Evidence", styles["section"]))
        for item in evidence:
            parts = [_safe_text(item.get("label", ""))]
            if item.get("page"):
                parts.append(f"page {item['page']}")
            if item.get("text_span"):
                parts.append(f'"{_safe_text(item["text_span"])}"')
            if item.get("confidence") is not None:
                parts.append(f"{round(float(item['confidence']) * 100)}%")
            story.append(Paragraph(" · ".join(part for part in parts if part), styles["muted"]))

    doc.build(story)
    return buffer.getvalue()
