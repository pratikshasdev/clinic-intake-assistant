from __future__ import annotations

from typing import Protocol

from ..config import Settings
from ..models import Extraction, IntakeText


class Extractor(Protocol):
    name: str

    async def extract(self, text: IntakeText) -> Extraction: ...


def get_extractor(settings: Settings) -> Extractor:
    choice = settings.extractor.lower()
    if choice == "auto":
        choice = "claude" if settings.anthropic_api_key else "rules"
    if choice == "claude":
        from .claude import ClaudeExtractor

        return ClaudeExtractor(
            model=settings.claude_model,
            effort=settings.claude_effort,
            api_key=settings.anthropic_api_key,
        )
    if choice == "rules":
        from .rules import RulesExtractor

        return RulesExtractor()
    raise ValueError(f"Unknown extractor {settings.extractor!r}; use auto, claude or rules")
