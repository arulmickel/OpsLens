"""Hugging Face Inference API provider.

Uses the hosted Inference API directly via requests so we do not pull
in a heavy local model stack. The endpoint and model are configurable.
"""
from __future__ import annotations

from typing import Any, Dict, List

import requests

from src.config import get_settings
from src.insights.models import Finding
from src.llm.base import LLMProvider, build_root_cause_prompt, build_summary_prompt


class HuggingFaceProvider(LLMProvider):
    name = "huggingface"

    def __init__(self) -> None:
        settings = get_settings()
        if not settings.huggingface_api_key:
            raise RuntimeError("HUGGINGFACE_API_KEY is not set")
        self._token = settings.huggingface_api_key
        self._model = settings.huggingface_model
        self._url = f"https://api-inference.huggingface.co/models/{self._model}"

    def _chat(self, prompt: str, max_tokens: int) -> str:
        headers = {"Authorization": f"Bearer {self._token}"}
        payload = {
            "inputs": prompt,
            "parameters": {
                "max_new_tokens": max_tokens,
                "temperature": 0.2,
                "return_full_text": False,
            },
            "options": {"wait_for_model": True},
        }
        resp = requests.post(self._url, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list) and data and "generated_text" in data[0]:
            return str(data[0]["generated_text"]).strip()
        if isinstance(data, dict) and "generated_text" in data:
            return str(data["generated_text"]).strip()
        return str(data).strip()

    def summarize(self, finding: Finding) -> str:
        return self._chat(build_summary_prompt(finding), max_tokens=120)

    def suggest_root_cause(self, finding: Finding, history: List[Dict[str, Any]]) -> str:
        return self._chat(build_root_cause_prompt(finding, history), max_tokens=180)
