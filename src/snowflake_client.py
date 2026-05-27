"""Thin Snowflake wrapper.

All queries are parameterized. The connector handles type binding so we
never need to format SQL with user input. Connections are short-lived
context managers so we do not leak sessions.
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Iterable, Iterator, List, Optional, Sequence

import pandas as pd
import snowflake.connector
from snowflake.connector.pandas_tools import write_pandas

from src.config import Settings, get_settings

logger = logging.getLogger(__name__)


class SnowflakeClient:
    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()
        if not self.settings.snowflake_configured():
            raise RuntimeError(
                "Snowflake is not configured. Set SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER, "
                "and SNOWFLAKE_PASSWORD in .env"
            )

    @contextmanager
    def connect(self) -> Iterator[snowflake.connector.SnowflakeConnection]:
        conn = snowflake.connector.connect(
            account=self.settings.snowflake_account,
            user=self.settings.snowflake_user,
            password=self.settings.snowflake_password,
            warehouse=self.settings.snowflake_warehouse,
            database=self.settings.snowflake_database,
            schema=self.settings.snowflake_schema,
            role=self.settings.snowflake_role,
            client_session_keep_alive=False,
        )
        try:
            yield conn
        finally:
            conn.close()

    def execute(self, sql: str, params: Optional[Sequence[Any]] = None) -> None:
        with self.connect() as conn:
            cur = conn.cursor()
            try:
                cur.execute(sql, params or ())
            finally:
                cur.close()

    def execute_many(self, statements: Iterable[str]) -> None:
        with self.connect() as conn:
            cur = conn.cursor()
            try:
                for stmt in statements:
                    if stmt.strip():
                        cur.execute(stmt)
            finally:
                cur.close()

    def query_df(self, sql: str, params: Optional[Sequence[Any]] = None) -> pd.DataFrame:
        with self.connect() as conn:
            cur = conn.cursor()
            try:
                cur.execute(sql, params or ())
                df = cur.fetch_pandas_all()
                df.columns = [c.upper() for c in df.columns]
                return df
            finally:
                cur.close()

    def write_df(
        self,
        df: pd.DataFrame,
        table: str,
        truncate: bool = False,
    ) -> int:
        if df.empty:
            return 0
        df = df.copy()
        df.columns = [c.upper() for c in df.columns]
        with self.connect() as conn:
            if truncate:
                cur = conn.cursor()
                try:
                    cur.execute(f"TRUNCATE TABLE IF EXISTS {table}")
                finally:
                    cur.close()
            success, _nchunks, nrows, _ = write_pandas(
                conn,
                df,
                table.upper(),
                auto_create_table=False,
                overwrite=False,
                quote_identifiers=False,
            )
            if not success:
                raise RuntimeError(f"write_pandas failed for table {table}")
            return nrows

    def ensure_database_and_schema(self) -> None:
        ddl = [
            f"CREATE DATABASE IF NOT EXISTS {self.settings.snowflake_database}",
            f"USE DATABASE {self.settings.snowflake_database}",
            f"CREATE SCHEMA IF NOT EXISTS {self.settings.snowflake_schema}",
            f"USE SCHEMA {self.settings.snowflake_schema}",
        ]
        self.execute_many(ddl)
