"""Render the daily HTML digest from a list of insights."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, List

import pandas as pd
from jinja2 import Environment, FileSystemLoader, select_autoescape

from src.config import get_settings

SEVERITY_ORDER = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]
SEVERITY_COLORS = {
    "CRITICAL": "#b91c1c",
    "HIGH": "#dc2626",
    "MEDIUM": "#f59e0b",
    "LOW": "#10b981",
}


@dataclass
class RenderedDigest:
    subject: str
    html: str
    total: int
    critical_count: int
    high_count: int


def _env() -> Environment:
    template_dir = Path(__file__).parent / "templates"
    return Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=select_autoescape(["html", "xml"]),
    )


def _group_by_severity(rows: List[Dict]) -> List[tuple[str, List[Dict]]]:
    grouped: Dict[str, List[Dict]] = {}
    for r in rows:
        grouped.setdefault(r["severity"], []).append(r)
    ordered: List[tuple[str, List[Dict]]] = []
    for sev in SEVERITY_ORDER:
        if sev in grouped:
            ordered.append((sev, grouped[sev]))
    return ordered


def _normalize(insights_df: pd.DataFrame) -> List[Dict]:
    rows: List[Dict] = []
    for _, r in insights_df.iterrows():
        rows.append(
            {
                "source_system": r["SOURCE_SYSTEM"],
                "category": r["CATEGORY"],
                "severity": r["SEVERITY"],
                "metric_name": r["METRIC_NAME"],
                "plain_english_summary": r["PLAIN_ENGLISH_SUMMARY"],
                "suggested_root_cause": r["SUGGESTED_ROOT_CAUSE"],
            }
        )
    return rows


def render_digest(insights_df: pd.DataFrame, digest_date: date | None = None) -> RenderedDigest:
    settings = get_settings()
    digest_date = digest_date or date.today()
    rows = _normalize(insights_df)
    groups = _group_by_severity(rows)

    critical = sum(1 for r in rows if r["severity"] == "CRITICAL")
    high = sum(1 for r in rows if r["severity"] == "HIGH")
    total = len(rows)
    minutes_saved = total * settings.minutes_per_manual_issue

    if total == 0:
        subject = f"OpsLens {digest_date}: All clear"
        subject_line = "No operational issues detected."
    elif critical > 0:
        subject = f"OpsLens {digest_date}: {critical} critical, {high} high"
        subject_line = f"{total} issue(s) need attention, {critical} critical."
    else:
        subject = f"OpsLens {digest_date}: {total} issues, {high} high"
        subject_line = f"{total} issue(s) detected today."

    env = _env()
    template = env.get_template("digest.html")
    html = template.render(
        digest_date=digest_date.strftime("%A, %d %B %Y"),
        subject_line=subject_line,
        total=total,
        critical_count=critical,
        high_count=high,
        minutes_saved=minutes_saved,
        groups=groups,
        severity_color=lambda s: SEVERITY_COLORS.get(s, "#6b7280"),
        dashboard_url=settings.dashboard_url,
    )
    return RenderedDigest(
        subject=subject,
        html=html,
        total=total,
        critical_count=critical,
        high_count=high,
    )
