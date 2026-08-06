from __future__ import annotations

from datetime import datetime
from html import unescape
from pathlib import Path
import re
from typing import Any, Iterable

import pandas as pd

from core.utils import normalize_whitespace, write_csv, write_json
from ingestion.crossref import PaperRecord


MIN_SUMMARY_CHARS = 100

CLEAN_COLUMNS = [
    "paper_id",
    "title",
    "summary",
    "authors_joined",
    "categories_joined",
    "primary_category",
    "published",
    "updated",
    "age_days",
    "summary_chars",
    "text_for_embedding",
    "abs_url",
    "pdf_url",
    "comment",
]


def _clean_text(value: Any) -> str:
    """Remove Crossref JATS/HTML markup and normalize visible text."""
    if value is None:
        return ""
    text = unescape(str(value))
    text = re.sub(r"<[^>]+>", " ", text)
    return normalize_whitespace(unescape(text))


def _clean_list(values: Iterable[Any] | None) -> list[str]:
    """Normalize a list while preserving order and removing empty/duplicate values."""
    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        item = _clean_text(value)
        key = item.casefold()
        if not item or key in seen:
            continue
        seen.add(key)
        cleaned.append(item)
    return cleaned


def _parse_date(value: Any) -> str | None:
    """Return a stable ISO date, or None when the source value is invalid."""
    text = _clean_text(value)
    if not text:
        return None
    try:
        parsed = pd.to_datetime(text, errors="raise", utc=True)
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed.date().isoformat()


def build_clean_dataframe(records: list[PaperRecord], run_date: datetime) -> pd.DataFrame:
    """Clean raw paper records into the shared retrieval/evaluation schema.

    Filtering and deduplication counts are attached to ``df.attrs["cleaning_stats"]``
    so the pipeline can persist an auditable report without changing this function's
    starter signature.
    """
    run_day = run_date.date()
    stats = {
        "input_records": len(records),
        "output_records": 0,
        "filtered_missing_paper_id": 0,
        "filtered_missing_title": 0,
        "filtered_short_summary": 0,
        "filtered_invalid_published": 0,
        "deduplicated_paper_id": 0,
        "min_summary_chars": MIN_SUMMARY_CHARS,
    }
    rows: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for record in records:
        paper_id = _clean_text(record.paper_id)
        title = _clean_text(record.title)
        summary = _clean_text(record.summary)

        if not paper_id:
            stats["filtered_missing_paper_id"] += 1
            continue
        if not title:
            stats["filtered_missing_title"] += 1
            continue
        if len(summary) < MIN_SUMMARY_CHARS:
            stats["filtered_short_summary"] += 1
            continue

        published = _parse_date(record.published)
        if published is None:
            stats["filtered_invalid_published"] += 1
            continue

        stable_id = paper_id.casefold()
        if stable_id in seen_ids:
            stats["deduplicated_paper_id"] += 1
            continue
        seen_ids.add(stable_id)

        authors = _clean_list(record.authors)
        categories = _clean_list(record.categories)
        authors_joined = ", ".join(authors)
        categories_joined = ", ".join(categories)
        primary_category = _clean_text(record.primary_category)
        if not primary_category and categories:
            primary_category = categories[0]

        age_days = max(0, (run_day - datetime.fromisoformat(published).date()).days)
        text_for_embedding = (
            f"Title: {title} | Authors: {authors_joined} | Summary: {summary}"
        )
        rows.append(
            {
                "paper_id": paper_id,
                "title": title,
                "summary": summary,
                "authors_joined": authors_joined,
                "categories_joined": categories_joined,
                "primary_category": primary_category,
                "published": published,
                "updated": _parse_date(record.updated) or "",
                "age_days": age_days,
                "summary_chars": len(summary),
                "text_for_embedding": text_for_embedding,
                "abs_url": _clean_text(record.abs_url),
                "pdf_url": _clean_text(record.pdf_url),
                "comment": _clean_text(record.comment),
            }
        )

    dataframe = pd.DataFrame(rows, columns=CLEAN_COLUMNS)
    if not dataframe.empty:
        dataframe = dataframe.sort_values(
            by=["published", "paper_id"], ascending=[False, True], kind="stable"
        ).reset_index(drop=True)
    stats["output_records"] = len(dataframe)
    stats["filtered_total"] = stats["input_records"] - stats["output_records"]
    dataframe.attrs["cleaning_stats"] = stats
    return dataframe


def write_clean_artifacts(
    dataframe: pd.DataFrame,
    csv_path: Path,
    json_path: Path,
    report_path: Path,
) -> dict[str, Any]:
    """Persist clean CSV/JSON and the filter/deduplication counts."""
    stats = dict(dataframe.attrs.get("cleaning_stats", {}))
    write_csv(dataframe, csv_path)
    write_json(json_path, dataframe.to_dict(orient="records"))
    write_json(report_path, stats)
    return stats
