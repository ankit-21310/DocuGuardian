from __future__ import annotations

import re
from pathlib import Path


def extract_text(path: Path, filename: str) -> str:
    suffix = path.suffix.lower() or Path(filename).suffix.lower()
    if suffix == ".pdf":
        return _extract_pdf(path)
    if suffix == ".docx":
        return _extract_docx(path)
    if suffix in {".png", ".jpg", ".jpeg"}:
        return _extract_image_placeholder(path, filename)
    return path.read_text(encoding="utf-8", errors="ignore")


def _extract_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        pages = []
        for index, page in enumerate(reader.pages, 1):
            text = (page.extract_text() or "").strip()
            if text:
                pages.append(f"[Page {index}]\n{text}")
        if pages:
            return "\n\n".join(pages)
    except Exception:
        pass
    return path.read_bytes()[:2000].decode("utf-8", errors="ignore")


def _extract_docx(path: Path) -> str:
    try:
        from docx import Document

        document = Document(str(path))
        paragraphs = [paragraph.text.strip() for paragraph in document.paragraphs if paragraph.text.strip()]
        if paragraphs:
            return "\n".join(paragraphs)
    except Exception:
        pass
    return path.read_bytes()[:2000].decode("utf-8", errors="ignore")


def _extract_image_placeholder(path: Path, filename: str) -> str:
    # Images rely on the vision-capable LLM stage; keep a stable local parse marker.
    return f"[Image document: {filename}]\nLocal OCR parse prepared file bytes at {path.name}."


def is_low_quality_extraction(text: str) -> bool:
    cleaned = text.strip()
    if not cleaned:
        return True
    if cleaned.startswith("[Image document:"):
        return True
    if len(cleaned) < 200:
        return True
    printable = sum(1 for char in cleaned if char.isprintable() or char in "\n\r\t")
    if printable / max(len(cleaned), 1) < 0.85:
        return True
    words = re.findall(r"[a-zA-Z]{3,}", cleaned)
    return len(words) < 20


def split_sections(text: str) -> list[dict]:
    if not text.strip():
        return [{"heading": "Document", "content": "", "page": None, "ordinal": 0}]
    blocks = re.split(r"\n(?=(?:[A-Z][A-Z0-9 /&-]{3,}|Article\s+\d+|Section\s+\d+|\[Page\s+\d+\]))", text)
    sections: list[dict] = []
    for ordinal, block in enumerate(blocks):
        block = block.strip()
        if not block:
            continue
        lines = block.splitlines()
        heading = lines[0][:120] if lines else f"Section {ordinal + 1}"
        page_match = re.search(r"\[Page\s+(\d+)\]", block)
        sections.append(
            {
                "heading": heading,
                "content": block,
                "page": int(page_match.group(1)) if page_match else None,
                "ordinal": ordinal,
            }
        )
    return sections or [{"heading": "Document", "content": text, "page": None, "ordinal": 0}]


def chunk_text(text: str, size: int = 900, overlap: int = 120) -> list[dict]:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if not cleaned:
        return []
    chunks: list[dict] = []
    start = 0
    ordinal = 0
    while start < len(cleaned):
        end = min(len(cleaned), start + size)
        piece = cleaned[start:end]
        page_match = re.search(r"Page\s+(\d+)", piece)
        chunks.append({"content": piece, "page": int(page_match.group(1)) if page_match else None, "ordinal": ordinal})
        ordinal += 1
        if end >= len(cleaned):
            break
        start = max(end - overlap, start + 1)
    return chunks
