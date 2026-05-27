"""LLM provider abstract base.

Two responsibilities: turn a structured finding into a one-sentence
plain English summary, and suggest a likely root cause given some
short recent-history context. Providers must enforce their own
timeouts and surface errors as exceptions; callers are expected to
fall back to the template provider if anything goes wrong.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List

from src.insights.models import Finding


class LLMProvider(ABC):
    name: str = "base"

    @abstractmethod
    def summarize(self, finding: Finding) -> str:
        ...

    @abstractmethod
    def suggest_root_cause(self, finding: Finding, history: List[Dict[str, Any]]) -> str:
        ...


def build_summary_prompt(finding: Finding) -> str:
    return (
        "You are summarizing operational issues for a non-technical operations manager.\n"
        "Produce exactly one short, factual sentence. No jargon, no hedging, no emojis.\n\n"
        f"Source: {finding.source_system}\n"
        f"Category: {finding.category}\n"
        f"Severity: {finding.severity}\n"
        f"Metric: {finding.metric_name}\n"
        f"Observed: {finding.observed_value}\n"
        f"Expected: {finding.expected_value}\n"
        f"Evidence: {finding.evidence}\n"
    )


def build_root_cause_prompt(finding: Finding, history: List[Dict[str, Any]]) -> str:
    return (
        "Suggest a single likely root cause for this issue in one or two sentences.\n"
        "Begin with 'Likely cause:' and make clear it is a suggestion, not a certainty.\n"
        "Do not invent specific people, vendors, or ticket numbers.\n\n"
        f"Finding: source={finding.source_system}, category={finding.category}, "
        f"metric={finding.metric_name}, observed={finding.observed_value}, "
        f"expected={finding.expected_value}, evidence={finding.evidence}\n"
        f"Recent history (latest first): {history[:5]}\n"
    )
