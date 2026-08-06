from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import pandas as pd

from core.clean_contract import persist_cleaning_summary
from core.config import Settings
from ingestion.crossref import PaperRecord


def build_clean_dataframe(records: list[PaperRecord], run_date: datetime) -> pd.DataFrame:
    """TODO(student): clean raw records thanh dataframe san sang de embed.

    Pseudo-code:
    1. Normalize title, summary, authors, categories.
    2. Parse published/updated date.
    3. Tinh age_days.
    4. Tao cot helper:
       - authors_joined
       - categories_joined
       - summary_chars
       - text_for_embedding
    5. Drop duplicates va filter row xau.
    6. Sort dataframe va return.
    """
    from html import unescape
    import re

    def clean_text(value) -> str:
        if value is None:
            return ""
        text = unescape(str(value))
        text = re.sub(r"<[^>]+>", " ", text)
        return re.sub(r"\s+", " ", unescape(text)).strip()

    def clean_list(values) -> list[str]:
        cleaned: list[str] = []
        seen: set[str] = set()
        for value in values or []:
            item = clean_text(value)
            key = item.casefold()
            if item and key not in seen:
                seen.add(key)
                cleaned.append(item)
        return cleaned

    def parse_date(value) -> str | None:
        text = clean_text(value)
        if not text:
            return None
        try:
            return pd.to_datetime(text, errors="raise", utc=True).date().isoformat()
        except (TypeError, ValueError, OverflowError):
            return None

    stats = {
        "input_records": len(records),
        "filtered_missing_paper_id": 0,
        "filtered_missing_title": 0,
        "filtered_short_summary": 0,
        "filtered_invalid_published": 0,
        "deduplicated_paper_id": 0,
    }
    rows = []
    seen_ids: set[str] = set()

    for record in records:
        paper_id = clean_text(record.paper_id)
        title = clean_text(record.title)
        summary = clean_text(record.summary)

        if not paper_id:
            stats["filtered_missing_paper_id"] += 1
            continue
        if not title:
            stats["filtered_missing_title"] += 1
            continue
        if len(summary) < 100:
            stats["filtered_short_summary"] += 1
            continue

        published = parse_date(record.published)
        if published is None:
            stats["filtered_invalid_published"] += 1
            continue

        stable_id = paper_id.casefold()
        if stable_id in seen_ids:
            stats["deduplicated_paper_id"] += 1
            continue
        seen_ids.add(stable_id)

        authors = clean_list(record.authors)
        categories = clean_list(record.categories)
        authors_joined = ", ".join(authors)
        categories_joined = ", ".join(categories)
        primary_category = clean_text(record.primary_category)
        if not primary_category and categories:
            primary_category = categories[0]

        published_date = datetime.fromisoformat(published).date()
        age_days = max(0, (run_date.date() - published_date).days)
        rows.append(
            {
                "paper_id": paper_id,
                "title": title,
                "summary": summary,
                "authors_joined": authors_joined,
                "categories_joined": categories_joined,
                "primary_category": primary_category,
                "published": published,
                "updated": parse_date(record.updated) or "",
                "age_days": age_days,
                "summary_chars": len(summary),
                "text_for_embedding": (
                    f"Title: {title} | Authors: {authors_joined} | Summary: {summary}"
                ),
                "abs_url": clean_text(record.abs_url),
                "pdf_url": clean_text(record.pdf_url),
                "comment": clean_text(record.comment),
            }
        )

    columns = [
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
    dataframe = pd.DataFrame(rows, columns=columns)
    if not dataframe.empty:
        dataframe = dataframe.sort_values(
            ["published", "paper_id"], ascending=[False, True], kind="stable"
        ).reset_index(drop=True)

    stats["output_records"] = len(dataframe)
    stats["filtered_total"] = len(records) - len(dataframe)
    dataframe.attrs["cleaning_stats"] = stats

    filtered_reasons = {
        "missing_paper_id": stats.get("filtered_missing_paper_id", 0),
        "missing_title": stats.get("filtered_missing_title", 0),
        "short_summary": stats.get("filtered_short_summary", 0),
        "invalid_published": stats.get("filtered_invalid_published", 0),
    }
    dedup_reasons = {
        "duplicate_paper_id": stats.get("deduplicated_paper_id", 0),
    }
    filtered_count = sum(filtered_reasons.values())
    deduplicated_count = sum(dedup_reasons.values())

    dataframe.attrs["cleaning_summary"] = {
        "filtered_count": filtered_count,
        "deduplicated_count": deduplicated_count,
        "reason_counts": {
            "filtered": {k: v for k, v in filtered_reasons.items() if v > 0},
            "deduplicated": {k: v for k, v in dedup_reasons.items() if v > 0},
        },
    }

    return dataframe


def save_clean_data(dataframe: pd.DataFrame, settings: Settings, raw_count: int | None = None) -> None:
    """Luu clean dataframe ra CSV va JSON tai settings.paths, dong thoi persist cleaning summary."""
    paths = settings.paths
    paths.clean_csv.parent.mkdir(parents=True, exist_ok=True)
    paths.clean_json.parent.mkdir(parents=True, exist_ok=True)
    paths.cleaning_summary.parent.mkdir(parents=True, exist_ok=True)

    # Lưu ra CSV
    dataframe.to_csv(paths.clean_csv, index=False)

    # Lưu ra JSON records
    records = dataframe.to_dict(orient="records")
    paths.clean_json.write_text(
        json.dumps(records, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )

    if raw_count is None:
        raw_count = dataframe.attrs.get("cleaning_stats", {}).get("input_records", len(dataframe))

    persist_cleaning_summary(settings, raw_count=raw_count, clean_df=dataframe)
