"""Generate realistic mock daily exports with injected anomalies.

Seed is set at module scope so the data is reproducible across runs.
The injected anomalies are placed on known dates so the detectors have
clear targets to find during the demo.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from src.config import get_settings

_settings = get_settings()
_RNG = np.random.default_rng(_settings.anomaly_seed)


CAMPAIGNS: List[Tuple[str, str]] = [
    ("CMP-001", "Spring Wellness Newsletter"),
    ("CMP-002", "Annual Checkup Reminder"),
    ("CMP-003", "Patient Portal Onboarding"),
    ("CMP-004", "Telehealth Promotion"),
]

MC_JOB_NAMES: List[str] = [
    "mc_export_email_sends",
    "mc_export_campaign_metadata",
    "mc_export_subscribers",
]

HC_OBJECT_TYPES: List[str] = ["Patient", "Encounter", "CarePlan"]

HC_JOB_NAMES: List[str] = [
    "hc_export_patients",
    "hc_export_encounters",
    "hc_export_careplans",
]


@dataclass(frozen=True)
class AnomalyPlan:
    """Pre-planned anomaly placement so the demo always has clear findings."""

    bounce_spike_day_offset: int
    missing_mc_job_day_offset: int
    hc_sync_failure_day_offset: int
    recon_mismatch_day_offset: int


def _plan_anomalies(history_days: int) -> AnomalyPlan:
    # Place anomalies in the most recent few days so today's run sees them.
    return AnomalyPlan(
        bounce_spike_day_offset=0,
        missing_mc_job_day_offset=0,
        hc_sync_failure_day_offset=1,
        recon_mismatch_day_offset=0,
    )


def _date_range(history_days: int, end: date) -> List[date]:
    return [end - timedelta(days=history_days - 1 - i) for i in range(history_days)]


def generate_mc_email_sends(dates: List[date], anomalies: AnomalyPlan, today: date) -> pd.DataFrame:
    rows = []
    spike_day = today - timedelta(days=anomalies.bounce_spike_day_offset)
    for d in dates:
        for cid, cname in CAMPAIGNS:
            audience = int(_RNG.normal(50_000, 5_000))
            audience = max(audience, 5_000)
            bounce_rate = float(_RNG.normal(0.015, 0.003))
            failed_rate = float(_RNG.normal(0.002, 0.001))
            # Inject bounce-rate spike on a specific recent day for one campaign.
            if d == spike_day and cid == "CMP-002":
                bounce_rate = float(_RNG.uniform(0.18, 0.25))
            bounce_rate = max(bounce_rate, 0.0)
            failed_rate = max(failed_rate, 0.0)
            bounced = int(audience * bounce_rate)
            failed = int(audience * failed_rate)
            delivered = max(audience - bounced - failed, 0)
            opens = int(delivered * float(_RNG.uniform(0.20, 0.32)))
            clicks = int(opens * float(_RNG.uniform(0.08, 0.14)))
            rows.append(
                {
                    "SEND_ID": str(uuid.uuid4()),
                    "SEND_DATE": d,
                    "CAMPAIGN_ID": cid,
                    "CAMPAIGN_NAME": cname,
                    "AUDIENCE_SIZE": audience,
                    "DELIVERED": delivered,
                    "BOUNCED": bounced,
                    "FAILED": failed,
                    "OPENS": opens,
                    "CLICKS": clicks,
                    "STATUS": "COMPLETED",
                }
            )
    return pd.DataFrame(rows)


def generate_mc_jobs(dates: List[date], anomalies: AnomalyPlan, today: date) -> pd.DataFrame:
    rows = []
    missing_day = today - timedelta(days=anomalies.missing_mc_job_day_offset)
    for d in dates:
        for jname in MC_JOB_NAMES:
            # Drop one job on the chosen day to simulate a missing job.
            if d == missing_day and jname == "mc_export_subscribers":
                continue
            failed = bool(_RNG.uniform() < 0.02)
            duration = int(_RNG.normal(180, 30))
            records = int(_RNG.normal(120_000, 8_000))
            rows.append(
                {
                    "JOB_ID": str(uuid.uuid4()),
                    "JOB_NAME": jname,
                    "RUN_DATE": d,
                    "STATUS": "FAILED" if failed else "SUCCESS",
                    "DURATION_SECONDS": max(duration, 1),
                    "RECORDS_PROCESSED": 0 if failed else max(records, 0),
                    "ERROR_MESSAGE": "Connection reset by peer" if failed else None,
                }
            )
    return pd.DataFrame(rows)


def generate_hc_record_syncs(dates: List[date], anomalies: AnomalyPlan, today: date) -> pd.DataFrame:
    rows = []
    surge_day = today - timedelta(days=anomalies.hc_sync_failure_day_offset)
    for d in dates:
        for obj in HC_OBJECT_TYPES:
            attempted = int(_RNG.normal(8_000, 500))
            attempted = max(attempted, 1_000)
            fail_rate = float(_RNG.normal(0.005, 0.002))
            if d == surge_day and obj == "Encounter":
                fail_rate = float(_RNG.uniform(0.35, 0.50))
            fail_rate = max(fail_rate, 0.0)
            failed = int(attempted * fail_rate)
            succeeded = max(attempted - failed, 0)
            status = "FAILED" if fail_rate > 0.30 else "SUCCESS"
            rows.append(
                {
                    "SYNC_ID": str(uuid.uuid4()),
                    "SYNC_DATE": d,
                    "OBJECT_TYPE": obj,
                    "RECORDS_ATTEMPTED": attempted,
                    "RECORDS_SUCCEEDED": succeeded,
                    "RECORDS_FAILED": failed,
                    "STATUS": status,
                }
            )
    return pd.DataFrame(rows)


def generate_hc_jobs(dates: List[date], anomalies: AnomalyPlan, today: date) -> pd.DataFrame:
    rows = []
    for d in dates:
        for jname in HC_JOB_NAMES:
            failed = bool(_RNG.uniform() < 0.03)
            duration = int(_RNG.normal(220, 40))
            rows.append(
                {
                    "JOB_ID": str(uuid.uuid4()),
                    "JOB_NAME": jname,
                    "RUN_DATE": d,
                    "STATUS": "FAILED" if failed else "SUCCESS",
                    "DURATION_SECONDS": max(duration, 1),
                    "ERROR_MESSAGE": "Upstream timeout" if failed else None,
                }
            )
    return pd.DataFrame(rows)


def generate_hc_reconciliation(dates: List[date], anomalies: AnomalyPlan, today: date) -> pd.DataFrame:
    rows = []
    mismatch_day = today - timedelta(days=anomalies.recon_mismatch_day_offset)
    for d in dates:
        for obj in HC_OBJECT_TYPES:
            exported = int(_RNG.normal(8_000, 500))
            exported = max(exported, 1_000)
            drift = int(_RNG.normal(0, 5))
            loaded = max(exported - max(drift, 0), 0)
            mismatch = exported - loaded
            if d == mismatch_day and obj == "Patient":
                # Big mismatch: a chunk failed to load.
                loaded = int(exported * 0.85)
                mismatch = exported - loaded
            rows.append(
                {
                    "RECON_DATE": d,
                    "SOURCE_SYSTEM": "HEALTH_CLOUD",
                    "OBJECT_TYPE": obj,
                    "EXPORTED_COUNT": exported,
                    "LOADED_COUNT": loaded,
                    "MISMATCH_COUNT": mismatch,
                }
            )
    return pd.DataFrame(rows)


def generate_all(history_days: int | None = None, today: date | None = None) -> Dict[str, pd.DataFrame]:
    """Generate every raw table for the configured history window."""
    history_days = history_days or _settings.history_days
    today = today or date.today()
    anomalies = _plan_anomalies(history_days)
    dates = _date_range(history_days, today)

    return {
        "MC_EMAIL_SENDS": generate_mc_email_sends(dates, anomalies, today),
        "MC_JOBS": generate_mc_jobs(dates, anomalies, today),
        "HC_RECORD_SYNCS": generate_hc_record_syncs(dates, anomalies, today),
        "HC_JOBS": generate_hc_jobs(dates, anomalies, today),
        "HC_RECONCILIATION": generate_hc_reconciliation(dates, anomalies, today),
    }
