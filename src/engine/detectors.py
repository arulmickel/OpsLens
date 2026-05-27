"""Detection functions. Pure data in, structured findings out.

Each detector operates on a pandas DataFrame already filtered to the
relevant table. The orchestrator in pipeline.py is responsible for
sourcing those frames from Snowflake. Keeping detectors pure makes
them straightforward to unit test against fixed series.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import List

import numpy as np
import pandas as pd

from src.config import get_settings
from src.insights.models import Category, Finding, Severity, SourceSystem


def _severity_from_zscore(z: float) -> Severity:
    z = abs(z)
    if z >= 5:
        return Severity.CRITICAL
    if z >= 4:
        return Severity.HIGH
    if z >= 3:
        return Severity.MEDIUM
    return Severity.LOW


def zscore_anomalies(
    series_df: pd.DataFrame,
    date_col: str,
    metric_col: str,
    run_date: date,
    source_system: SourceSystem,
    metric_name: str,
    group_col: str | None = None,
) -> List[Finding]:
    """Rolling-baseline z-score check.

    The baseline is the prior `baseline_window_days` excluding the run
    date itself. Anything past `zscore_threshold` standard deviations is
    flagged. Works per-group when `group_col` is provided.
    """
    settings = get_settings()
    findings: List[Finding] = []
    if series_df.empty:
        return findings

    df = series_df.copy()
    df[date_col] = pd.to_datetime(df[date_col]).dt.date

    groups = df[group_col].unique() if group_col else [None]
    window_start = run_date - timedelta(days=settings.baseline_window_days)

    for g in groups:
        sub = df if g is None else df[df[group_col] == g]
        baseline = sub[(sub[date_col] >= window_start) & (sub[date_col] < run_date)]
        today_rows = sub[sub[date_col] == run_date]
        if baseline.empty or today_rows.empty:
            continue

        mean = float(baseline[metric_col].mean())
        std = float(baseline[metric_col].std(ddof=0))
        if std == 0 or np.isnan(std):
            continue

        today_value = float(today_rows[metric_col].sum())
        # Aggregate the same way the baseline did: per-day total.
        baseline_daily = baseline.groupby(date_col)[metric_col].sum()
        if baseline_daily.empty:
            continue
        b_mean = float(baseline_daily.mean())
        b_std = float(baseline_daily.std(ddof=0))
        if b_std == 0 or np.isnan(b_std):
            continue
        z = (today_value - b_mean) / b_std

        if abs(z) >= settings.zscore_threshold:
            findings.append(
                Finding(
                    run_date=run_date,
                    source_system=source_system,
                    category=Category.ANOMALY,
                    severity=_severity_from_zscore(z),
                    metric_name=metric_name if g is None else f"{metric_name}:{g}",
                    observed_value=today_value,
                    expected_value=b_mean,
                    evidence={
                        "z_score": round(z, 2),
                        "baseline_mean": round(b_mean, 2),
                        "baseline_std": round(b_std, 2),
                        "window_days": settings.baseline_window_days,
                        "group": g,
                    },
                )
            )
    return findings


def failed_jobs(
    jobs_df: pd.DataFrame,
    run_date: date,
    source_system: SourceSystem,
) -> List[Finding]:
    """Flag any job that ran today with status FAILED."""
    if jobs_df.empty:
        return []
    df = jobs_df.copy()
    df["RUN_DATE"] = pd.to_datetime(df["RUN_DATE"]).dt.date
    today = df[(df["RUN_DATE"] == run_date) & (df["STATUS"].str.upper() == "FAILED")]
    findings: List[Finding] = []
    for _, row in today.iterrows():
        findings.append(
            Finding(
                run_date=run_date,
                source_system=source_system,
                category=Category.FAILED_JOB,
                severity=Severity.HIGH,
                metric_name=f"job:{row['JOB_NAME']}",
                observed_value=0.0,
                expected_value=1.0,
                evidence={
                    "job_id": row.get("JOB_ID"),
                    "job_name": row.get("JOB_NAME"),
                    "error_message": row.get("ERROR_MESSAGE"),
                    "duration_seconds": int(row.get("DURATION_SECONDS") or 0),
                },
            )
        )
    return findings


def missing_jobs(
    jobs_df: pd.DataFrame,
    run_date: date,
    source_system: SourceSystem,
    lookback_days: int = 7,
) -> List[Finding]:
    """A job that ran on prior days but is absent today."""
    if jobs_df.empty:
        return []
    df = jobs_df.copy()
    df["RUN_DATE"] = pd.to_datetime(df["RUN_DATE"]).dt.date
    window_start = run_date - timedelta(days=lookback_days)
    prior = df[(df["RUN_DATE"] >= window_start) & (df["RUN_DATE"] < run_date)]
    today = df[df["RUN_DATE"] == run_date]

    expected = set(prior["JOB_NAME"].unique())
    actual = set(today["JOB_NAME"].unique())
    missing = expected - actual

    findings: List[Finding] = []
    for job_name in sorted(missing):
        last_run = prior[prior["JOB_NAME"] == job_name]["RUN_DATE"].max()
        findings.append(
            Finding(
                run_date=run_date,
                source_system=source_system,
                category=Category.MISSING_JOB,
                severity=Severity.CRITICAL,
                metric_name=f"job:{job_name}",
                observed_value=0.0,
                expected_value=1.0,
                evidence={
                    "job_name": job_name,
                    "last_seen": str(last_run),
                    "lookback_days": lookback_days,
                },
            )
        )
    return findings


def threshold_breach(
    df: pd.DataFrame,
    date_col: str,
    numerator_col: str,
    denominator_col: str,
    run_date: date,
    source_system: SourceSystem,
    metric_name: str,
    threshold: float,
    group_col: str | None = None,
) -> List[Finding]:
    """Flag when numerator/denominator exceeds a configured ratio."""
    if df.empty:
        return []
    work = df.copy()
    work[date_col] = pd.to_datetime(work[date_col]).dt.date
    today = work[work[date_col] == run_date]
    if today.empty:
        return []

    findings: List[Finding] = []
    groups = today[group_col].unique() if group_col else [None]
    for g in groups:
        sub = today if g is None else today[today[group_col] == g]
        numerator = float(sub[numerator_col].sum())
        denominator = float(sub[denominator_col].sum())
        if denominator <= 0:
            continue
        rate = numerator / denominator
        if rate > threshold:
            severity = Severity.HIGH if rate > threshold * 3 else Severity.MEDIUM
            findings.append(
                Finding(
                    run_date=run_date,
                    source_system=source_system,
                    category=Category.THRESHOLD,
                    severity=severity,
                    metric_name=metric_name if g is None else f"{metric_name}:{g}",
                    observed_value=round(rate, 4),
                    expected_value=round(threshold, 4),
                    evidence={
                        "numerator": numerator,
                        "denominator": denominator,
                        "group": g,
                    },
                )
            )
    return findings
