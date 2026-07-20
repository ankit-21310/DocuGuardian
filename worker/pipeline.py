"""Provider-neutral processing stages for the production worker.

The API's local background task uses the same stage contract. A queue worker can
import these functions and replace the deterministic adapters with OCR/LLM providers.
"""

from dataclasses import dataclass
from typing import Protocol


class OCRProvider(Protocol):
    def extract_text(self, path: str) -> str: ...


class ReasoningProvider(Protocol):
    def analyze(self, text: str) -> dict: ...


@dataclass(frozen=True)
class PipelineStage:
    key: str
    label: str


PIPELINE = tuple(PipelineStage(key, label) for key, label in (
    ("ocr", "OCR and parsing"), ("classification", "Classification"),
    ("clauses", "Clause extraction"), ("risks", "Risk analysis"),
    ("deadlines", "Deadline detection"), ("recommendations", "Recommendations"),
    ("report", "Report generation"),
))
