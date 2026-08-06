from __future__ import annotations

from pathlib import Path
from typing import Any
import random

import pandas as pd

from core.utils import now_utc, write_json

CORRUPTION_SEED = 20251110

# How many rows each scenario touches. Kept small and explicit so the corruption stays
# auditable: every affected paper_id is written to the log and can be matched back from the
# comparison report.
DROP_LATEST_ROWS = 3
BLANK_SUMMARY_ROWS = 3
NOISE_ROWS = 3
TRUNCATE_TITLE_ROWS = 3
STALE_DATE_ROWS = 3
DUPLICATE_ROWS = 2

TRUNCATED_TITLE_CHARS = 12
STALE_SHIFT_DAYS = 2200

# Mojibake and filler of the kind a broken scrape or a bad encoding round-trip leaves behind.
NOISE_FRAGMENTS = (
    "Ã¢â‚¬â„¢ Ã¯Â¿Â½",
    "### N/A N/A N/A ###",
    "lorem ipsum dolor sit amet consectetur adipiscing",
)

TEXT_TEMPLATE = "Title: {title} | Authors: {authors} | Summary: {summary}"


def _rebuild_derived_columns(row: dict[str, Any]) -> dict[str, Any]:
    """Keep the derived columns consistent with the fields the corruption touched.

    cleaning.build_clean_dataframe composes these; a corruption that changed a title or a
    summary without refreshing them would leave the row internally inconsistent for reasons
    that have nothing to do with the scenario being simulated.
    """
    summary = str(row.get("summary") or "")
    row["summary_chars"] = len(summary)
    row["text_for_embedding"] = TEXT_TEMPLATE.format(
        title=row.get("title") or "",
        authors=row.get("authors_joined") or "",
        summary=summary,
    )
    return row


def _shift_published(value: Any, days: int) -> str:
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return str(value or "")
    return (parsed - pd.Timedelta(days=days)).date().isoformat()


def corrupt_clean_dataframe(df: pd.DataFrame, output_log_path) -> pd.DataFrame:
    """Apply a fixed set of data faults to a clean dataframe and log every one of them.

    Deterministic: the same clean input always produces the same corrupted output and the
    same log, so the corrupted evaluation can be re-run and compared.

    The input frame is never modified. Which rows a scenario hits is decided by a seeded
    shuffle over the eligible rows, not by looking at the evaluation set - targeting the
    questions would manufacture the degradation the report is supposed to measure.
    """
    output_log_path = Path(output_log_path)
    if df is None or len(df) == 0:
        raise ValueError("Cannot corrupt an empty clean dataframe.")

    records: list[dict[str, Any]] = [dict(row) for row in df.to_dict(orient="records")]
    input_rows = len(records)
    events: list[dict[str, Any]] = []

    def log(paper_id: Any, corruption_type: str, affected_field: str, detail: str) -> None:
        events.append(
            {
                "paper_id": str(paper_id),
                "corruption_type": corruption_type,
                "affected_field": affected_field,
                "detail": detail,
            }
        )

    # 1. Drop the newest records. build_clean_dataframe sorts by published descending, so the
    #    head of the frame is the freshest slice: losing it is what a stalled ingest looks like.
    drop_count = min(DROP_LATEST_ROWS, max(0, len(records) - 1))
    for row in records[:drop_count]:
        log(row.get("paper_id"), "drop_latest_records", "row", "newest record removed from the corpus")
    survivors = records[drop_count:]

    # Disjoint row assignment for the remaining scenarios, so one row is not blanked and
    # noised at once and each signal stays attributable.
    order = list(range(len(survivors)))
    random.Random(f"{CORRUPTION_SEED}:assign").shuffle(order)
    cursor = 0

    def take(count: int) -> list[int]:
        nonlocal cursor
        chosen = order[cursor : cursor + count]
        cursor += len(chosen)
        return chosen

    for position in take(BLANK_SUMMARY_ROWS):
        row = survivors[position]
        log(row.get("paper_id"), "blank_summary", "summary", "summary emptied")
        row["summary"] = ""
        _rebuild_derived_columns(row)

    noise_rng = random.Random(f"{CORRUPTION_SEED}:noise")
    for position in take(NOISE_ROWS):
        row = survivors[position]
        summary = str(row.get("summary") or "")
        fragment = noise_rng.choice(NOISE_FRAGMENTS)
        words = summary.split()
        midpoint = len(words) // 2
        row["summary"] = " ".join(words[:midpoint] + [fragment] + words[midpoint:])
        log(row.get("paper_id"), "inject_noise", "summary", f"inserted {fragment!r} mid-summary")
        _rebuild_derived_columns(row)

    for position in take(TRUNCATE_TITLE_ROWS):
        row = survivors[position]
        original = str(row.get("title") or "")
        row["title"] = original[:TRUNCATED_TITLE_CHARS]
        log(
            row.get("paper_id"),
            "truncate_title",
            "title",
            f"title cut to {TRUNCATED_TITLE_CHARS} characters",
        )
        _rebuild_derived_columns(row)

    for position in take(STALE_DATE_ROWS):
        row = survivors[position]
        row["published"] = _shift_published(row.get("published"), STALE_SHIFT_DAYS)
        if row.get("updated"):
            row["updated"] = _shift_published(row.get("updated"), STALE_SHIFT_DAYS)
        try:
            row["age_days"] = int(row.get("age_days") or 0) + STALE_SHIFT_DAYS
        except (TypeError, ValueError):
            row["age_days"] = STALE_SHIFT_DAYS
        log(
            row.get("paper_id"),
            "stale_published",
            "published",
            f"publication date moved back {STALE_SHIFT_DAYS} days",
        )

    # 6. Duplicate whole rows: a re-ingest that ran twice. Breaks paper_id uniqueness and
    #    full-row uniqueness at the same time.
    duplicate_positions = take(DUPLICATE_ROWS)
    duplicates = []
    for position in duplicate_positions:
        row = survivors[position]
        duplicates.append(dict(row))
        log(row.get("paper_id"), "duplicate_row", "row", "record appended a second time")

    corrupted = pd.DataFrame(survivors + duplicates, columns=list(df.columns))

    scenario_counts: dict[str, int] = {}
    for event in events:
        scenario_counts[event["corruption_type"]] = scenario_counts.get(event["corruption_type"], 0) + 1

    write_json(
        output_log_path,
        {
            "generated_at": now_utc().isoformat(),
            "seed": CORRUPTION_SEED,
            "input_rows": input_rows,
            "output_rows": int(len(corrupted)),
            "rows_removed": drop_count,
            "rows_added": len(duplicates),
            "scenario_counts": scenario_counts,
            "affected_paper_ids": sorted({event["paper_id"] for event in events}),
            # `events` is the single record of what happened; the scenario entries only roll
            # it up by type and reference paper ids, so nothing reading this log structurally
            # sees the same event twice.
            "scenarios": [
                {
                    "corruption_type": name,
                    "affected_count": count,
                    "affected_paper_ids": [
                        event["paper_id"] for event in events if event["corruption_type"] == name
                    ],
                }
                for name, count in scenario_counts.items()
            ],
            "events": events,
        },
    )
    return corrupted
