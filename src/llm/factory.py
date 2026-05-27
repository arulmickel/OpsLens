"""Pick the configured provider, fall back when no key is present."""
from __future__ import annotations

import logging

from src.config import get_settings
from src.llm.base import LLMProvider
from src.llm.fallback import FallbackProvider

logger = logging.getLogger(__name__)


def get_provider() -> LLMProvider:
    settings = get_settings()
    choice = settings.llm_provider

    if choice == "openai" and settings.openai_api_key:
        try:
            from src.llm.openai_provider import OpenAIProvider

            return OpenAIProvider()
        except Exception as e:
            logger.warning("OpenAI provider unavailable, using fallback: %s", e)
    elif choice == "anthropic" and settings.anthropic_api_key:
        try:
            from src.llm.anthropic_provider import AnthropicProvider

            return AnthropicProvider()
        except Exception as e:
            logger.warning("Anthropic provider unavailable, using fallback: %s", e)
    elif choice == "huggingface" and settings.huggingface_api_key:
        try:
            from src.llm.huggingface_provider import HuggingFaceProvider

            return HuggingFaceProvider()
        except Exception as e:
            logger.warning("Hugging Face provider unavailable, using fallback: %s", e)
    elif choice != "fallback":
        logger.info("LLM_PROVIDER=%s but no key set; using deterministic fallback", choice)

    return FallbackProvider()
