"""Reconciliation checks: exported vs loaded counts.

A small mismatch can be normal noise. We only flag mismatches above a
small ratio so the dashboard does not get spammed with near-zero drift.
"""
from __future__ import annotations

from datetime import date
from typing import List

import pandas as pd

from src.insights.models import Category, Finding, Severity, SourceSystem

MIN_MISMATCH_RATIO = 0.01


def reconciliation_mismatches(
    recon_df: pd.DataFrame,
    run_date: date,
) -> List[Finding]:
    if recon_df.empty:
        return []
    df = recon_df.copy()
    df["RECON_DATE"] = pd.to_datetime(df["RECON_DATE"]).dt.date
    today = df[df["RECON_DATE"] == run_date]
    findings: List[Finding] = []
    for _, row in today.iterrows():
        exported = float(row["EXPORTED_COUNT"] or 0)
        loaded = float(row["LOADED_COUNT"] or 0)
        if exported <= 0:
            continue
        ratio = abs(exported - loaded) / exported
        if ratio < MIN_MISMATCH_RATIO:
            continue
        if ratio >= 0.10:
            severity = Severity.CRITICAL
        elif ratio >= 0.05:
            severity = Severity.HIGH
        else:
            severity = Severity.MEDIUM
        system = SourceSystem(row.get("SOURCE_SYSTEM", "HEALTH_CLOUD"))
        findings.append(
            Finding(
                run_date=run_date,
                source_system=system,
                category=Category.RECONCILIATION,
                severity=severity,
                metric_name=f"reconciliation:{row['OBJECT_TYPE']}",
                observed_value=loaded,
                expected_value=exported,
                evidence={
                    "object_type": row["OBJECT_TYPE"],
                    "exported_count": int(exported),
                    "loaded_count": int(loaded),
                    "mismatch_count": int(exported - loaded),
                    "mismatch_ratio": round(ratio, 4),
                },
            )
        )
    return findings
