"""Table definitions for the mock data and the insights store.

Snowflake DDL only. The CREATE TABLE statements are idempotent so the
setup script can run repeatedly without manual cleanup.
"""
from __future__ import annotations

TABLES: dict[str, str] = {
    "MC_EMAIL_SENDS": """
        CREATE TABLE IF NOT EXISTS MC_EMAIL_SENDS (
            SEND_ID            STRING,
            SEND_DATE          DATE,
            CAMPAIGN_ID        STRING,
            CAMPAIGN_NAME      STRING,
            AUDIENCE_SIZE      NUMBER,
            DELIVERED          NUMBER,
            BOUNCED            NUMBER,
            FAILED             NUMBER,
            OPENS              NUMBER,
            CLICKS             NUMBER,
            STATUS             STRING
        )
    """,
    "MC_JOBS": """
        CREATE TABLE IF NOT EXISTS MC_JOBS (
            JOB_ID             STRING,
            JOB_NAME           STRING,
            RUN_DATE           DATE,
            STATUS             STRING,
            DURATION_SECONDS   NUMBER,
            RECORDS_PROCESSED  NUMBER,
            ERROR_MESSAGE      STRING
        )
    """,
    "HC_RECORD_SYNCS": """
        CREATE TABLE IF NOT EXISTS HC_RECORD_SYNCS (
            SYNC_ID            STRING,
            SYNC_DATE          DATE,
            OBJECT_TYPE        STRING,
            RECORDS_ATTEMPTED  NUMBER,
            RECORDS_SUCCEEDED  NUMBER,
            RECORDS_FAILED     NUMBER,
            STATUS             STRING
        )
    """,
    "HC_JOBS": """
        CREATE TABLE IF NOT EXISTS HC_JOBS (
            JOB_ID             STRING,
            JOB_NAME           STRING,
            RUN_DATE           DATE,
            STATUS             STRING,
            DURATION_SECONDS   NUMBER,
            ERROR_MESSAGE      STRING
        )
    """,
    "HC_RECONCILIATION": """
        CREATE TABLE IF NOT EXISTS HC_RECONCILIATION (
            RECON_DATE         DATE,
            SOURCE_SYSTEM      STRING,
            OBJECT_TYPE        STRING,
            EXPORTED_COUNT     NUMBER,
            LOADED_COUNT       NUMBER,
            MISMATCH_COUNT     NUMBER
        )
    """,
    "OPS_INSIGHTS": """
        CREATE TABLE IF NOT EXISTS OPS_INSIGHTS (
            INSIGHT_ID              STRING,
            DETECTED_AT             TIMESTAMP_NTZ,
            RUN_DATE                DATE,
            SOURCE_SYSTEM           STRING,
            CATEGORY                STRING,
            SEVERITY                STRING,
            METRIC_NAME             STRING,
            OBSERVED_VALUE          FLOAT,
            EXPECTED_VALUE          FLOAT,
            PLAIN_ENGLISH_SUMMARY   STRING,
            SUGGESTED_ROOT_CAUSE    STRING,
            EVIDENCE                STRING
        )
    """,
}

RAW_TABLES = [t for t in TABLES if t != "OPS_INSIGHTS"]
INSIGHTS_TABLE = "OPS_INSIGHTS"
