"""Centralized configuration loaded from environment variables.

All secrets are read here and nowhere else. Defaults are safe for the
deterministic fallback so the app boots even when nothing is configured.
"""
from __future__ import annotations

from functools import lru_cache
from typing import List, Literal, Optional

from dotenv import load_dotenv
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Snowflake
    snowflake_account: str = ""
    snowflake_user: str = ""
    snowflake_password: str = ""
    snowflake_warehouse: str = "COMPUTE_WH"
    snowflake_database: str = "OPSLENS"
    snowflake_schema: str = "PUBLIC"
    snowflake_role: str = "ACCOUNTADMIN"

    # LLM
    llm_provider: Literal["openai", "anthropic", "huggingface", "fallback"] = "fallback"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-haiku-4-5-20251001"
    huggingface_api_key: str = ""
    huggingface_model: str = "meta-llama/Llama-3.2-3B-Instruct"

    # SMTP
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "opslens@example.com"
    digest_recipients: str = ""
    dashboard_url: str = "http://localhost:8501"

    # Dashboard auth
    dashboard_username: str = "ops"
    dashboard_password_hash: str = ""

    # Detectors
    zscore_threshold: float = 3.0
    failure_rate_threshold: float = 0.05
    baseline_window_days: int = 14
    history_days: int = 30
    anomaly_seed: int = 42

    # Efficiency narrative
    minutes_per_manual_issue: int = 12

    @field_validator("zscore_threshold")
    @classmethod
    def _zscore_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("zscore_threshold must be positive")
        return v

    @field_validator("failure_rate_threshold")
    @classmethod
    def _rate_in_range(cls, v: float) -> float:
        if not 0 < v < 1:
            raise ValueError("failure_rate_threshold must be between 0 and 1")
        return v

    @property
    def digest_recipient_list(self) -> List[str]:
        return [r.strip() for r in self.digest_recipients.split(",") if r.strip()]

    def snowflake_configured(self) -> bool:
        return bool(self.snowflake_account and self.snowflake_user and self.snowflake_password)

    def llm_key_present(self) -> bool:
        if self.llm_provider == "openai":
            return bool(self.openai_api_key)
        if self.llm_provider == "anthropic":
            return bool(self.anthropic_api_key)
        if self.llm_provider == "huggingface":
            return bool(self.huggingface_api_key)
        return False


@lru_cache
def get_settings() -> Settings:
    return Settings()
