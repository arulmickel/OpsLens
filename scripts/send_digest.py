"""Render and send the daily digest from today's OPS_INSIGHTS."""
from __future__ import annotations

import logging
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.email_digest.render import render_digest  # noqa: E402
from src.email_digest.send import send_digest  # noqa: E402
from src.insights.store import InsightStore  # noqa: E402
from src.snowflake_client import SnowflakeClient  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("digest")


def main() -> int:
    client = SnowflakeClient()
    store = InsightStore(client)
    today = date.today()
    insights_df = store.fetch_for_date(today)
    log.info("Loaded %d insights for %s", len(insights_df), today)
    rendered = render_digest(insights_df, digest_date=today)
    log.info("Subject: %s", rendered.subject)
    sent = send_digest(rendered)
    log.info("Digest sent: %s", sent)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
