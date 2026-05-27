"""Read/write helpers for the OPS_INSIGHTS table.

Pandas is the on-the-wire format. The wider system never sees raw SQL
strings outside this module and snowflake_client.
"""
from __future__ import annotations

import json
from datetime import date
from typing import Iterable, List, Optional

from typing import TYPE_CHECKING

import pandas as pd

from src.insights.models import Insight

if TYPE_CHECKING:
    from src.snowflake_client import SnowflakeClient


INSIGHT_COLUMNS = [
    "INSIGHT_ID",
    "DETECTED_AT",
    "RUN_DATE",
    "SOURCE_SYSTEM",
    "CATEGORY",
    "SEVERITY",
    "METRIC_NAME",
    "OBSERVED_VALUE",
    "EXPECTED_VALUE",
    "PLAIN_ENGLISH_SUMMARY",
    "SUGGESTED_ROOT_CAUSE",
    "EVIDENCE",
]


def insights_to_df(insights: Iterable[Insight]) -> pd.DataFrame:
    rows = []
    for ins in insights:
        rows.append(
            {
                "INSIGHT_ID": ins.insight_id,
                "DETECTED_AT": ins.detected_at,
                "RUN_DATE": ins.run_date,
                "SOURCE_SYSTEM": ins.source_system,
                "CATEGORY": ins.category,
                "SEVERITY": ins.severity,
                "METRIC_NAME": ins.metric_name,
                "OBSERVED_VALUE": ins.observed_value,
                "EXPECTED_VALUE": ins.expected_value,
                "PLAIN_ENGLISH_SUMMARY": ins.plain_english_summary,
                "SUGGESTED_ROOT_CAUSE": ins.suggested_root_cause,
                "EVIDENCE": json.dumps(ins.evidence, default=str),
            }
        )
    df = pd.DataFrame(rows, columns=INSIGHT_COLUMNS)
    return df


class InsightStore:
    def __init__(self, client: "SnowflakeClient") -> None:
        self.client = client

    def write(self, insights: List[Insight]) -> int:
        if not insights:
            return 0
        df = insights_to_df(insights)
        return self.client.write_df(df, "OPS_INSIGHTS")

    def delete_for_date(self, run_date: date) -> None:
        self.client.execute(
            "DELETE FROM OPS_INSIGHTS WHERE RUN_DATE = %s",
            (run_date,),
        )

    def fetch_for_date(self, run_date: date) -> pd.DataFrame:
        return self.client.query_df(
            "SELECT * FROM OPS_INSIGHTS WHERE RUN_DATE = %s ORDER BY SEVERITY, DETECTED_AT DESC",
            (run_date,),
        )

    def fetch_recent(self, days: int = 7) -> pd.DataFrame:
        return self.client.query_df(
            "SELECT * FROM OPS_INSIGHTS WHERE RUN_DATE >= DATEADD(day, %s, CURRENT_DATE()) "
            "ORDER BY DETECTED_AT DESC",
            (-abs(int(days)),),
        )

    def fetch_all(self, limit: Optional[int] = None) -> pd.DataFrame:
        sql = "SELECT * FROM OPS_INSIGHTS ORDER BY DETECTED_AT DESC"
        params: tuple = ()
        if limit is not None:
            sql += " LIMIT %s"
            params = (int(limit),)
        return self.client.query_df(sql, params)
