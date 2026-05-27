"""Generate and load mock data into the Snowflake raw tables."""
from __future__ import annotations

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.mock_data.generate import generate_all  # noqa: E402
from src.snowflake_client import SnowflakeClient  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("load")


def main() -> int:
    client = SnowflakeClient()
    log.info("Generating mock data")
    data = generate_all()
    total = 0
    for table, df in data.items():
        log.info("Truncating and loading %s (%d rows)", table, len(df))
        client.write_df(df, table, truncate=True)
        total += len(df)
    log.info("Mock load complete: %d rows across %d tables.", total, len(data))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
