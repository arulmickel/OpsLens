"""Detector unit tests against fixed series."""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest

from src.engine import detectors as det
from src.engine.reconciliation import reconciliation_mismatches
from src.insights.models import Category, SourceSystem


@pytest.fixture
def run_date() -> date:
    return date(2025, 5, 26)


def _daily_series(values, start_date, col_name, date_col):
    rows = []
    for i, v in enumerate(values):
        rows.append({date_col: start_date + timedelta(days=i), col_name: v})
    return pd.DataFrame(rows)


def test_zscore_anomaly_detects_spike(run_date):
    # 14 baseline days of ~100 with small natural variation, then a big jump.
    baseline_values = [95, 100, 103, 98, 101, 99, 104, 96, 102, 100, 97, 101, 99, 103]
    rows = []
    for i, v in enumerate(baseline_values):
        rows.append({"SEND_DATE": run_date - timedelta(days=len(baseline_values) - i), "BOUNCED": v})
    rows.append({"SEND_DATE": run_date, "BOUNCED": 5000})
    df = pd.DataFrame(rows)
    findings = det.zscore_anomalies(
        df,
        date_col="SEND_DATE",
        metric_col="BOUNCED",
        run_date=run_date,
        source_system=SourceSystem.MARKETING_CLOUD,
        metric_name="daily_bounces",
    )
    assert len(findings) == 1
    f = findings[0]
    assert f.category == Category.ANOMALY.value
    assert f.observed_value == 5000
    assert f.evidence["z_score"] > 3


def test_zscore_no_finding_for_steady_series(run_date):
    rows = []
    for i in range(15):
        rows.append({"SEND_DATE": run_date - timedelta(days=14 - i), "BOUNCED": 100})
    # Today is also 100.
    df = pd.DataFrame(rows)
    findings = det.zscore_anomalies(
        df,
        date_col="SEND_DATE",
        metric_col="BOUNCED",
        run_date=run_date,
        source_system=SourceSystem.MARKETING_CLOUD,
        metric_name="daily_bounces",
    )
    assert findings == []


def test_failed_job_detected(run_date):
    df = pd.DataFrame(
        [
            {"JOB_ID": "j1", "JOB_NAME": "mc_export", "RUN_DATE": run_date, "STATUS": "FAILED", "DURATION_SECONDS": 30, "ERROR_MESSAGE": "boom"},
            {"JOB_ID": "j2", "JOB_NAME": "mc_other", "RUN_DATE": run_date, "STATUS": "SUCCESS", "DURATION_SECONDS": 30, "ERROR_MESSAGE": None},
        ]
    )
    findings = det.failed_jobs(df, run_date, SourceSystem.MARKETING_CLOUD)
    assert len(findings) == 1
    assert findings[0].category == Category.FAILED_JOB.value
    assert findings[0].evidence["error_message"] == "boom"


def test_missing_job_detected(run_date):
    rows = []
    for day_offset in range(1, 5):
        d = run_date - timedelta(days=day_offset)
        rows.append({"JOB_ID": f"a-{day_offset}", "JOB_NAME": "always_runs", "RUN_DATE": d, "STATUS": "SUCCESS", "DURATION_SECONDS": 1, "ERROR_MESSAGE": None})
        rows.append({"JOB_ID": f"b-{day_offset}", "JOB_NAME": "also_runs", "RUN_DATE": d, "STATUS": "SUCCESS", "DURATION_SECONDS": 1, "ERROR_MESSAGE": None})
    # Today only one of the two ran.
    rows.append({"JOB_ID": "a-today", "JOB_NAME": "always_runs", "RUN_DATE": run_date, "STATUS": "SUCCESS", "DURATION_SECONDS": 1, "ERROR_MESSAGE": None})
    df = pd.DataFrame(rows)
    findings = det.missing_jobs(df, run_date, SourceSystem.HEALTH_CLOUD)
    assert len(findings) == 1
    assert findings[0].metric_name.endswith("also_runs")
    assert findings[0].category == Category.MISSING_JOB.value


def test_threshold_breach(run_date):
    df = pd.DataFrame(
        [
            {"SEND_DATE": run_date, "CAMPAIGN_NAME": "Bad", "BOUNCED": 5000, "AUDIENCE_SIZE": 10000},
            {"SEND_DATE": run_date, "CAMPAIGN_NAME": "Good", "BOUNCED": 50, "AUDIENCE_SIZE": 10000},
        ]
    )
    findings = det.threshold_breach(
        df,
        date_col="SEND_DATE",
        numerator_col="BOUNCED",
        denominator_col="AUDIENCE_SIZE",
        run_date=run_date,
        source_system=SourceSystem.MARKETING_CLOUD,
        metric_name="bounce_rate",
        threshold=0.05,
        group_col="CAMPAIGN_NAME",
    )
    metrics = {f.metric_name for f in findings}
    assert any(m.endswith("Bad") for m in metrics)
    assert not any(m.endswith("Good") for m in metrics)


def test_reconciliation_mismatch(run_date):
    df = pd.DataFrame(
        [
            {"RECON_DATE": run_date, "SOURCE_SYSTEM": "HEALTH_CLOUD", "OBJECT_TYPE": "Patient", "EXPORTED_COUNT": 1000, "LOADED_COUNT": 800, "MISMATCH_COUNT": 200},
            {"RECON_DATE": run_date, "SOURCE_SYSTEM": "HEALTH_CLOUD", "OBJECT_TYPE": "Encounter", "EXPORTED_COUNT": 1000, "LOADED_COUNT": 999, "MISMATCH_COUNT": 1},
        ]
    )
    findings = reconciliation_mismatches(df, run_date)
    assert len(findings) == 1
    f = findings[0]
    assert f.category == Category.RECONCILIATION.value
    assert f.evidence["mismatch_ratio"] >= 0.10
