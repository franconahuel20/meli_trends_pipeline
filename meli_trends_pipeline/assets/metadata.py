"""Helpers to render asset metadata shown in the Dagster UI."""

from __future__ import annotations

import pandas as pd


def markdown_table(df: pd.DataFrame, max_rows: int = 10) -> str:
    """Render the first rows of ``df`` as a Markdown table (no extra dependencies)."""
    if df.empty:
        return "_no rows_"
    head = df.head(max_rows)

    def cell(value: object) -> str:
        text = "" if pd.isna(value) else str(value)
        return text.replace("|", "\\|").replace("\n", " ")

    lines = [
        "| " + " | ".join(cell(c) for c in head.columns) + " |",
        "| " + " | ".join("---" for _ in head.columns) + " |",
    ]
    lines += ["| " + " | ".join(cell(v) for v in row) + " |" for row in head.itertuples(index=False)]
    return "\n".join(lines)
