"""End-to-end pipeline orchestration.

Pulls recent data from Snowflake, runs every detector, enriches the
findings with an LLM-generated summary and root-cause suggestion, and
persists results to OPS_INSIGHTS. The same record set drives the
dashboard and the email digest.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any, Dict, List, Optional

import pandas as pd

from src.config import get_settings
from src.engine import detectors as det
from src.engine.reconciliation import reconciliation_mismatches
from src.insights.models import Finding, Insight, SourceSystem
from src.insights.store import InsightStore
from src.llm.base import LLMProvider
from src.llm.factory import get_provider

if TYPE_CHECKING:
    from src.snowflake_client import SnowflakeClient

logger = logging.getLogger(__name__)


def _bounce_rate_df(mc_sends: pd.DataFrame) -> pd.DataFrame:
    if mc_sends.empty:
        return mc_sends
    df = mc_sends.copy()
    df["BOUNCE_RATE"] = df["BOUNCED"] / df["AUDIENCE_SIZE"].clip(lower=1)
    return df


def detect_all(
    run_date: date,
    mc_sends: pd.DataFrame,
    mc_jobs: pd.DataFrame,
    hc_syncs: pd.DataFrame,
    hc_jobs: pd.DataFrame,
    hc_recon: pd.DataFrame,
) -> List[Finding]:
    settings = get_settings()
    findings: List[Finding] = []

    # Marketing Cloud signals.
    findings += det.threshold_breach(
        mc_sends,
        date_col="SEND_DATE",
        numerator_col="BOUNCED",
        denominator_col="AUDIENCE_SIZE",
        run_date=run_date,
        source_system=SourceSystem.MARKETING_CLOUD,
        metric_name="bounce_rate",
        threshold=settings.failure_rate_threshold,
        group_col="CAMPAIGN_NAME",
    )
    bounce_df = _bounce_rate_df(mc_sends)
    findings += det.zscore_anomalies(
        bounce_df,
        date_col="SEND_DATE",
        metric_col="BOUNCED",
        run_date=run_date,
        source_system=SourceSystem.MARKETING_CLOUD,
        metric_name="daily_bounces",
    )
    findings += det.failed_jobs(mc_jobs, run_date, SourceSystem.MARKETING_CLOUD)
    findings += det.missing_jobs(mc_jobs, run_date, SourceSystem.MARKETING_CLOUD)

    # Health Cloud signals.
    if not hc_syncs.empty:
        hc = hc_syncs.copy()
        hc["FAIL_RATE"] = hc["RECORDS_FAILED"] / hc["RECORDS_ATTEMPTED"].clip(lower=1)
        findings += det.threshold_breach(
            hc,
            date_col="SYNC_DATE",
            numerator_col="RECORDS_FAILED",
            denominator_col="RECORDS_ATTEMPTED",
            run_date=run_date,
            source_system=SourceSystem.HEALTH_CLOUD,
            metric_name="sync_failure_rate",
            threshold=settings.failure_rate_threshold,
            group_col="OBJECT_TYPE",
        )
        findings += det.zscore_anomalies(
            hc,
            date_col="SYNC_DATE",
            metric_col="RECORDS_FAILED",
            run_date=run_date,
            source_system=SourceSystem.HEALTH_CLOUD,
            metric_name="daily_sync_failures",
        )
    findings += det.failed_jobs(hc_jobs, run_date, SourceSystem.HEALTH_CLOUD)
    findings += det.missing_jobs(hc_jobs, run_date, SourceSystem.HEALTH_CLOUD)

    findings += reconciliation_mismatches(hc_recon, run_date)

    return findings


def _history_for(finding: Finding, history_by_source: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    return history_by_source.get(str(finding.source_system), [])[:5]


def enrich(
    findings: List[Finding],
    provider: LLMProvider,
    history_by_source: Optional[Dict[str, List[Dict[str, Any]]]] = None,
) -> List[Insight]:
    history_by_source = history_by_source or {}
    insights: List[Insight] = []
    for f in findings:
        try:
            summary = provider.summarize(f)
        except Exception as e:
            logger.warning("summarize failed (%s); using fallback text", e)
            from src.llm.fallback import FallbackProvider

            summary = FallbackProvider().summarize(f)
        try:
            cause = provider.suggest_root_cause(f, _history_for(f, history_by_source))
        except Exception as e:
            logger.warning("root cause failed (%s); using fallback text", e)
            from src.llm.fallback import FallbackProvider

            cause = FallbackProvider().suggest_root_cause(f, _history_for(f, history_by_source))
        insights.append(Insight.from_finding(f, summary, cause))
    return insights


def _load_raw(client: "SnowflakeClient", run_date: date, history_days: int) -> Dict[str, pd.DataFrame]:
    start = run_date - timedelta(days=history_days)
    queries = {
        "MC_EMAIL_SENDS": ("SELECT * FROM MC_EMAIL_SENDS WHERE SEND_DATE >= %s", (start,)),
        "MC_JOBS": ("SELECT * FROM MC_JOBS WHERE RUN_DATE >= %s", (start,)),
        "HC_RECORD_SYNCS": ("SELECT * FROM HC_RECORD_SYNCS WHERE SYNC_DATE >= %s", (start,)),
        "HC_JOBS": ("SELECT * FROM HC_JOBS WHERE RUN_DATE >= %s", (start,)),
        "HC_RECONCILIATION": ("SELECT * FROM HC_RECONCILIATION WHERE RECON_DATE >= %s", (start,)),
    }
    return {name: client.query_df(sql, params) for name, (sql, params) in queries.items()}


def _recent_history(client: "SnowflakeClient", run_date: date) -> Dict[str, List[Dict[str, Any]]]:
    start = run_date - timedelta(days=7)
    df = client.query_df(
        "SELECT RUN_DATE, SOURCE_SYSTEM, CATEGORY, SEVERITY, METRIC_NAME "
        "FROM OPS_INSIGHTS WHERE RUN_DATE >= %s ORDER BY DETECTED_AT DESC",
        (start,),
    )
    out: Dict[str, List[Dict[str, Any]]] = {}
    if df.empty:
        return out
    for src, sub in df.groupby("SOURCE_SYSTEM"):
        out[str(src)] = sub.to_dict(orient="records")
    return out


def run_pipeline(
    client: "SnowflakeClient",
    provider: Optional[LLMProvider] = None,
    run_date: Optional[date] = None,
) -> List[Insight]:
    settings = get_settings()
    run_date = run_date or date.today()
    provider = provider or get_provider()
    logger.info("Running OpsLens pipeline for %s with provider=%s", run_date, provider.name)

    raw = _load_raw(client, run_date, settings.history_days)
    findings = detect_all(
        run_date=run_date,
        mc_sends=raw["MC_EMAIL_SENDS"],
        mc_jobs=raw["MC_JOBS"],
        hc_syncs=raw["HC_RECORD_SYNCS"],
        hc_jobs=raw["HC_JOBS"],
        hc_recon=raw["HC_RECONCILIATION"],
    )
    logger.info("Detected %d findings", len(findings))

    history = _recent_history(client, run_date)
    insights = enrich(findings, provider, history)

    store = InsightStore(client)
    store.delete_for_date(run_date)
    store.write(insights)
    logger.info("Persisted %d insights to OPS_INSIGHTS", len(insights))
    return insights
