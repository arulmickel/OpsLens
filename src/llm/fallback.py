"""Deterministic template provider.

Used when no LLM key is configured so the demo always runs. The text
is rule-based but written to read like a human ops summary, not a
debug dump. Categories and severities drive the wording.
"""
from __future__ import annotations

from typing import Any, Dict, List

from src.insights.models import Category, Finding, Severity
from src.llm.base import LLMProvider


def _fmt_metric(metric_name: str) -> str:
    if ":" in metric_name:
        kind, value = metric_name.split(":", 1)
        return f"{kind.replace('_', ' ')} {value}"
    return metric_name.replace("_", " ")


def _direction(observed: float | None, expected: float | None) -> str:
    if observed is None or expected is None:
        return "changed"
    if observed > expected:
        return "spiked above"
    return "dropped below"


def _summary_for(finding: Finding) -> str:
    metric = _fmt_metric(finding.metric_name)
    sev = str(finding.severity).lower()
    src = "Marketing Cloud" if str(finding.source_system) == "MARKETING_CLOUD" else "Health Cloud"
    cat = str(finding.category)

    if cat == Category.ANOMALY.value:
        direction = _direction(finding.observed_value, finding.expected_value)
        return (
            f"{src} {metric} {direction} its 14 day baseline today "
            f"(observed {finding.observed_value}, expected near {finding.expected_value}); "
            f"severity {sev}."
        )
    if cat == Category.FAILED_JOB.value:
        err = finding.evidence.get("error_message") or "an unspecified error"
        return f"{src} job {metric} failed today with error: {err}."
    if cat == Category.MISSING_JOB.value:
        last = finding.evidence.get("last_seen", "recently")
        return f"{src} job {metric} did not run today; last seen on {last}."
    if cat == Category.RECONCILIATION.value:
        ev = finding.evidence
        return (
            f"{src} reconciliation gap for {ev.get('object_type')}: exported {ev.get('exported_count')} "
            f"but loaded {ev.get('loaded_count')} (mismatch {ev.get('mismatch_count')})."
        )
    if cat == Category.THRESHOLD.value:
        return (
            f"{src} {metric} crossed its threshold today "
            f"(observed {finding.observed_value} vs threshold {finding.expected_value})."
        )
    return f"{src} {metric} flagged with severity {sev}."


def _root_cause_for(finding: Finding, history: List[Dict[str, Any]]) -> str:
    cat = str(finding.category)
    if cat == Category.ANOMALY.value:
        return (
            "Likely cause: a campaign or upstream content change introduced an unusual send "
            "pattern, or a deliverability issue affected this segment. This is a suggestion; "
            "review the change log and the affected campaign list to confirm."
        )
    if cat == Category.FAILED_JOB.value:
        err = (finding.evidence.get("error_message") or "").lower()
        if "timeout" in err:
            return (
                "Likely cause: an upstream system was slow or unreachable during the run "
                "window. This is a suggestion; check upstream health and retry policies."
            )
        if "connection" in err or "reset" in err:
            return (
                "Likely cause: a transient network or connector issue interrupted the job. "
                "This is a suggestion; rerun the job and confirm credentials are still valid."
            )
        return (
            "Likely cause: a transient or upstream failure interrupted the job. This is a "
            "suggestion; inspect the job log for stack traces and rerun if the cause was transient."
        )
    if cat == Category.MISSING_JOB.value:
        return (
            "Likely cause: the scheduler did not trigger the job, or the source export did not "
            "produce a file in time. This is a suggestion; verify the schedule and the upstream "
            "delivery."
        )
    if cat == Category.RECONCILIATION.value:
        return (
            "Likely cause: rows were dropped during load due to validation failures or a partial "
            "load window. This is a suggestion; inspect the loader error file and compare row "
            "counts at each stage."
        )
    if cat == Category.THRESHOLD.value:
        return (
            "Likely cause: a content, list-hygiene, or deliverability change pushed the rate "
            "above the configured threshold. This is a suggestion; review the most recent "
            "campaign changes and any audience refreshes."
        )
    return "Likely cause: insufficient context to suggest a specific cause."


class FallbackProvider(LLMProvider):
    name = "fallback"

    def summarize(self, finding: Finding) -> str:
        return _summary_for(finding)

    def suggest_root_cause(self, finding: Finding, history: List[Dict[str, Any]]) -> str:
        return _root_cause_for(finding, history)
