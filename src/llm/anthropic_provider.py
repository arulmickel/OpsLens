"""Anthropic Claude provider."""
from __future__ import annotations

from typing import Any, Dict, List

from src.config import get_settings
from src.insights.models import Finding
from src.llm.base import LLMProvider, build_root_cause_prompt, build_summary_prompt


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self) -> None:
        import anthropic

        settings = get_settings()
        if not settings.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set")
        self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self._model = settings.anthropic_model

    def _chat(self, prompt: str, max_tokens: int) -> str:
        resp = self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            temperature=0.2,
            messages=[{"role": "user", "content": prompt}],
        )
        parts = [block.text for block in resp.content if getattr(block, "type", "") == "text"]
        return "".join(parts).strip()

    def summarize(self, finding: Finding) -> str:
        return self._chat(build_summary_prompt(finding), max_tokens=160)

    def suggest_root_cause(self, finding: Finding, history: List[Dict[str, Any]]) -> str:
        return self._chat(build_root_cause_prompt(finding, history), max_tokens=220)
