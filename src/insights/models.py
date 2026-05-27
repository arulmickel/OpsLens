"""Pydantic models for findings and enriched insights.

A `Finding` is what a detector emits: structured, no prose. An
`Insight` is the LLM-enriched record we persist to OPS_INSIGHTS.
Keeping them separate lets us re-enrich without re-detecting.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field


class SourceSystem(str, Enum):
    MARKETING_CLOUD = "MARKETING_CLOUD"
    HEALTH_CLOUD = "HEALTH_CLOUD"


class Category(str, Enum):
    ANOMALY = "ANOMALY"
    FAILED_JOB = "FAILED_JOB"
    MISSING_JOB = "MISSING_JOB"
    RECONCILIATION = "RECONCILIATION"
    THRESHOLD = "THRESHOLD"


class Severity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class Finding(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    run_date: date
    source_system: SourceSystem
    category: Category
    severity: Severity
    metric_name: str
    observed_value: Optional[float] = None
    expected_value: Optional[float] = None
    evidence: Dict[str, Any] = Field(default_factory=dict)


class Insight(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    insight_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    detected_at: datetime = Field(default_factory=datetime.utcnow)
    run_date: date
    source_system: SourceSystem
    category: Category
    severity: Severity
    metric_name: str
    observed_value: Optional[float] = None
    expected_value: Optional[float] = None
    plain_english_summary: str
    suggested_root_cause: str
    evidence: Dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_finding(cls, f: Finding, summary: str, root_cause: str) -> "Insight":
        return cls(
            run_date=f.run_date,
            source_system=SourceSystem(f.source_system),
            category=Category(f.category),
            severity=Severity(f.severity),
            metric_name=f.metric_name,
            observed_value=f.observed_value,
            expected_value=f.expected_value,
            plain_english_summary=summary,
            suggested_root_cause=root_cause,
            evidence=f.evidence,
        )
