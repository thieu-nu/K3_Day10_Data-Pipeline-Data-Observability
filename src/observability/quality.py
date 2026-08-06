from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from core.config import Settings
from core.utils import write_json


def run_data_quality_checks(df: pd.DataFrame, settings: Settings, report_name: str) -> dict[str, Any]:
    """Tạo bộ data quality checks cho dataframe đã làm sạch."""
    total_rows = int(len(df))

    if total_rows == 0 or "paper_id" not in df:
        null_ids = total_rows
        unique_ids = 0
    else:
        null_ids = int(df["paper_id"].isna().sum() + (df["paper_id"].astype(str).str.strip() == "").sum())
        unique_ids = int(df["paper_id"].nunique())

    is_unique = (unique_ids == total_rows) and (total_rows > 0)
    null_titles = int(df["title"].isna().sum() + (df["title"].astype(str).str.strip() == "").sum()) if "title" in df and total_rows > 0 else total_rows
    mean_summary_len = float(df["summary"].astype(str).str.len().mean()) if "summary" in df and total_rows > 0 else 0.0

    stale_rows = int((df["age_days"] > settings.freshness_threshold_days).sum()) if "age_days" in df and total_rows > 0 else 0
    passed = (null_ids == 0) and is_unique and (null_titles == 0) and (total_rows > 0)

    payload = {
        "total_rows": total_rows,
        "null_ids": null_ids,
        "unique_ids": unique_ids,
        "is_unique": is_unique,
        "null_titles": null_titles,
        "mean_summary_length": round(mean_summary_len, 2),
        "stale_rows": stale_rows,
        "freshness_threshold_days": settings.freshness_threshold_days,
        "passed": passed,
    }

    report_path = settings.paths.quality_dir / report_name
    write_json(report_path, payload)
    return payload


def build_freshness_report(df: pd.DataFrame, settings: Settings, report_path: Path | str) -> dict[str, Any]:
    """Tổng hợp freshness report."""
    total_rows = int(len(df))
    if total_rows > 0 and "published" in df:
        latest_published = str(df["published"].max())
        oldest_published = str(df["published"].min())
    else:
        latest_published = ""
        oldest_published = ""

    if total_rows > 0 and "age_days" in df:
        stale_rows = int((df["age_days"] > settings.freshness_threshold_days).sum())
    else:
        stale_rows = 0

    is_fresh = (stale_rows == 0) and (total_rows > 0)

    payload = {
        "latest_published": latest_published,
        "oldest_published": oldest_published,
        "stale_rows": stale_rows,
        "total_rows": total_rows,
        "is_fresh": is_fresh,
        "threshold_days": settings.freshness_threshold_days,
    }

    write_json(Path(report_path), payload)
    return payload

