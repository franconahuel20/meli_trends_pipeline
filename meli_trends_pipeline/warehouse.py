"""Small PostgreSQL helpers: typed DDL, bulk COPY loads and reads into pandas."""

from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Sequence

import pandas as pd
from psycopg2 import sql


@dataclass(frozen=True)
class Column:
    name: str
    sql_type: str
    nullable: bool = True

    def ddl(self) -> sql.Composable:
        constraint = sql.SQL("") if self.nullable else sql.SQL(" NOT NULL")
        return sql.SQL("{} {}{}").format(sql.Identifier(self.name), sql.SQL(self.sql_type), constraint)


def qualified(schema: str, table: str) -> sql.Composable:
    return sql.SQL("{}.{}").format(sql.Identifier(schema), sql.Identifier(table))


def read_dataframe(conn, query: str | sql.Composable, params: Sequence | None = None) -> pd.DataFrame:
    with conn.cursor() as cur:
        cur.execute(query, params)
        columns = [d.name for d in cur.description]
        return pd.DataFrame(cur.fetchall(), columns=columns)


def table_columns(cur, schema: str, table: str) -> list[str]:
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = %s AND table_name = %s
        ORDER BY ordinal_position
        """,
        (schema, table),
    )
    return [row[0] for row in cur.fetchall()]


def create_table(cur, schema: str, table: str, columns: Sequence[Column]) -> None:
    cur.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(schema)))
    cur.execute(
        sql.SQL("CREATE TABLE {} ({})").format(
            qualified(schema, table), sql.SQL(", ").join(c.ddl() for c in columns)
        )
    )


def ensure_table(cur, schema: str, table: str, columns: Sequence[Column]) -> str | None:
    """Create the table if missing; if its columns differ, keep the old one as a backup.

    Returns the backup table name when an incompatible table was set aside.
    """
    existing = table_columns(cur, schema, table)
    if existing == [c.name for c in columns]:
        return None
    backup = None
    if existing:
        backup = f"{table}_backup_{datetime.now(timezone.utc):%Y%m%d%H%M%S}"
        cur.execute(
            sql.SQL("ALTER TABLE {} RENAME TO {}").format(
                qualified(schema, table), sql.Identifier(backup)
            )
        )
    create_table(cur, schema, table, columns)
    return backup


def copy_dataframe(cur, schema: str, table: str, df: pd.DataFrame) -> int:
    """Bulk-load ``df`` with COPY; missing values become NULL."""
    buffer = io.StringIO()
    df.to_csv(buffer, index=False, header=False, na_rep="")
    buffer.seek(0)
    statement = sql.SQL("COPY {} ({}) FROM STDIN WITH (FORMAT csv)").format(
        qualified(schema, table), sql.SQL(", ").join(sql.Identifier(c) for c in df.columns)
    )
    cur.copy_expert(statement.as_string(cur), buffer)
    return len(df)
