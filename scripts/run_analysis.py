"""Run the engine pipeline and persist to OPS_INSIGHTS."""
from __future__ import annotations

import logging
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.engine.pipeline import run_pipeline  # noqa: E402
from src.snowflake_client import SnowflakeClient  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("analyze")


def main() -> int:
    client = SnowflakeClient()
    insights = run_pipeline(client)
    sev_counts = Counter(str(i.severity) for i in insights)
    log.info(
        "Run complete. Total=%d Critical=%d High=%d Medium=%d Low=%d",
        len(insights),
        sev_counts.get("CRITICAL", 0),
        sev_counts.get("HIGH", 0),
        sev_counts.get("MEDIUM", 0),
        sev_counts.get("LOW", 0),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
