"""Input validation models for the dashboard and CLI arguments.

Every value the user can influence goes through one of these models.
Pydantic enforces size, length, and allow-list constraints. Anything
malformed is rejected before it reaches the engine or the DB.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Allowed dropdown values; the dashboard pre-fills these and validation
# rejects anything outside the set.
ALLOWED_SOURCES = {"MARKETING_CLOUD", "HEALTH_CLOUD"}
ALLOWED_SEVERITIES = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
ALLOWED_CATEGORIES = {"ANOMALY", "FAILED_JOB", "MISSING_JOB", "RECONCILIATION", "THRESHOLD"}

MAX_SEARCH_LENGTH = 100
MAX_DATE_RANGE_DAYS = 90
SAFE_TEXT_PATTERN = re.compile(r"^[\w\s\-.,:/()'\"]*$")


class IssueFilter(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    sources: List[str] = Field(default_factory=list)
    severities: List[str] = Field(default_factory=list)
    categories: List[str] = Field(default_factory=list)
    start_date: date
    end_date: date
    search: str = ""

    @field_validator("sources")
    @classmethod
    def _sources_ok(cls, v: List[str]) -> List[str]:
        invalid = [s for s in v if s not in ALLOWED_SOURCES]
        if invalid:
            raise ValueError(f"unsupported source(s): {invalid}")
        return v

    @field_validator("severities")
    @classmethod
    def _severities_ok(cls, v: List[str]) -> List[str]:
        invalid = [s for s in v if s not in ALLOWED_SEVERITIES]
        if invalid:
            raise ValueError(f"unsupported severity: {invalid}")
        return v

    @field_validator("categories")
    @classmethod
    def _categories_ok(cls, v: List[str]) -> List[str]:
        invalid = [s for s in v if s not in ALLOWED_CATEGORIES]
        if invalid:
            raise ValueError(f"unsupported category: {invalid}")
        return v

    @field_validator("search")
    @classmethod
    def _search_safe(cls, v: str) -> str:
        if len(v) > MAX_SEARCH_LENGTH:
            raise ValueError(f"search text exceeds {MAX_SEARCH_LENGTH} characters")
        if v and not SAFE_TEXT_PATTERN.match(v):
            raise ValueError("search text contains unsupported characters")
        return v

    def validate_range(self) -> "IssueFilter":
        if self.start_date > self.end_date:
            raise ValueError("start_date must be on or before end_date")
        if (self.end_date - self.start_date).days > MAX_DATE_RANGE_DAYS:
            raise ValueError(f"date range cannot exceed {MAX_DATE_RANGE_DAYS} days")
        if self.end_date > date.today() + timedelta(days=1):
            raise ValueError("end_date cannot be in the future")
        return self


class RunAnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_date: date

    @field_validator("run_date")
    @classmethod
    def _not_too_old(cls, v: date) -> date:
        if v < date.today() - timedelta(days=365):
            raise ValueError("run_date is more than a year old")
        if v > date.today() + timedelta(days=1):
            raise ValueError("run_date cannot be in the future")
        return v


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("username")
    @classmethod
    def _username_safe(cls, v: str) -> str:
        if not re.match(r"^[A-Za-z0-9_.\-@]+$", v):
            raise ValueError("username contains unsupported characters")
        return v
