"""Shared pipeline stage contract used by API workers and compose runners."""

from __future__ import annotations

from dataclasses import dataclass

from app.config import PIPELINE_STAGES


@dataclass(frozen=True)
class PipelineStage:
    key: str
    label: str


def _key(label: str) -> str:
    return label.lower().replace(" ", "_").replace("&", "and")


PIPELINE = tuple(PipelineStage(_key(label), label) for label in PIPELINE_STAGES)
