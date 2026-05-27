"""Create the database, schema, and tables idempotently."""
from __future__ import annotations

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.mock_data.schemas import TABLES  # noqa: E402
from src.snowflake_client import SnowflakeClient  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("setup")


def main() -> int:
    client = SnowflakeClient()
    log.info("Ensuring database and schema exist")
    client.ensure_database_and_schema()
    created = 0
    for name, ddl in TABLES.items():
        log.info("Creating table if missing: %s", name)
        client.execute(ddl)
        created += 1
    log.info("Setup complete. %d table definitions ensured.", created)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
