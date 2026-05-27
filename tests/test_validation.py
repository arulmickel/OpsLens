"""Input validation tests."""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from src.security.validation import (
    IssueFilter,
    LoginRequest,
    MAX_SEARCH_LENGTH,
    RunAnalysisRequest,
)


def test_issue_filter_rejects_unknown_source():
    with pytest.raises(ValidationError):
        IssueFilter(
            sources=["NOT_REAL"],
            severities=[],
            categories=[],
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 2),
            search="",
        )


def test_issue_filter_rejects_oversize_search():
    with pytest.raises(ValidationError):
        IssueFilter(
            sources=[],
            severities=[],
            categories=[],
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 2),
            search="a" * (MAX_SEARCH_LENGTH + 1),
        )


def test_issue_filter_rejects_bad_chars():
    with pytest.raises(ValidationError):
        IssueFilter(
            sources=[],
            severities=[],
            categories=[],
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 2),
            search="<script>",
        )


def test_issue_filter_rejects_inverted_range():
    f = IssueFilter(
        sources=[],
        severities=[],
        categories=[],
        start_date=date(2025, 2, 1),
        end_date=date(2025, 1, 1),
        search="",
    )
    with pytest.raises(ValueError):
        f.validate_range()


def test_issue_filter_rejects_too_long_range():
    f = IssueFilter(
        sources=[],
        severities=[],
        categories=[],
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
        search="",
    )
    with pytest.raises(ValueError):
        f.validate_range()


def test_issue_filter_happy_path():
    f = IssueFilter(
        sources=["MARKETING_CLOUD"],
        severities=["HIGH"],
        categories=["ANOMALY"],
        start_date=date.today() - timedelta(days=7),
        end_date=date.today(),
        search="bounce",
    ).validate_range()
    assert f.sources == ["MARKETING_CLOUD"]


def test_run_analysis_rejects_future_date():
    with pytest.raises(ValidationError):
        RunAnalysisRequest(run_date=date.today() + timedelta(days=10))


def test_login_request_rejects_bad_username():
    with pytest.raises(ValidationError):
        LoginRequest(username="hacker; DROP TABLE", password="abc")


def test_login_request_rejects_overlong_password():
    with pytest.raises(ValidationError):
        LoginRequest(username="ops", password="x" * 1000)
