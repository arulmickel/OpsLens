"""OpenAI chat completion provider."""
from __future__ import annotations

from typing import Any, Dict, List

from src.config import get_settings
from src.insights.models import Finding
from src.llm.base import LLMProvider, build_root_cause_prompt, build_summary_prompt


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(self) -> None:
        from openai import OpenAI

        settings = get_settings()
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is not set")
        self._client = OpenAI(api_key=settings.openai_api_key)
        self._model = settings.openai_model

    def _chat(self, prompt: str, max_tokens: int) -> str:
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=max_tokens,
            timeout=20,
        )
        return (resp.choices[0].message.content or "").strip()

    def summarize(self, finding: Finding) -> str:
        return self._chat(build_summary_prompt(finding), max_tokens=120)

    def suggest_root_cause(self, finding: Finding, history: List[Dict[str, Any]]) -> str:
        return self._chat(build_root_cause_prompt(finding, history), max_tokens=180)
