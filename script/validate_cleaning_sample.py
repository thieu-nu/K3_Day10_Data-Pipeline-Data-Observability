from __future__ import annotations

from datetime import UTC, datetime

from ingestion.cleaning import build_clean_dataframe
from ingestion.crossref import PaperRecord


def _record(
    paper_id: str,
    title: str,
    summary: str,
    *,
    authors: list[str] | None = None,
    categories: list[str] | None = None,
    published: str = "2026-01-01",
) -> PaperRecord:
    return PaperRecord(
        paper_id=paper_id,
        title=title,
        summary=summary,
        authors=authors or [],
        categories=categories or [],
        primary_category="",
        published=published,
        updated="",
        abs_url="https://doi.org/" + paper_id,
        pdf_url="",
        comment="",
    )


def main() -> None:
    long_summary = (
        "<jats:p>This paper presents a reproducible retrieval augmented generation "
        "pipeline and evaluates how data quality affects semantic search results "
        "across controlled experiments.</jats:p>"
    )
    records = [
        _record(
            "10.1000/clean-sample",
            "  <b>Reliable   RAG Pipelines</b>  ",
            long_summary,
            authors=[" Ada  Lovelace ", "", "Grace Hopper"],
            categories=["Machine Learning", "", "Data Quality", "Machine Learning"],
        ),
        _record("10.1000/clean-sample", "Duplicate title", long_summary),
        _record("10.1000/too-short", "Short abstract", "Too short."),
    ]

    run_date = datetime(2026, 1, 11, tzinfo=UTC)
    df = build_clean_dataframe(records, run_date=run_date)

    assert len(df) == 1, "Expected the duplicate and short-summary records to be removed."
    row = df.iloc[0]
    assert row["paper_id"] == "10.1000/clean-sample"
    assert row["title"] == "Reliable RAG Pipelines"
    assert "<" not in row["title"] and "<" not in row["summary"]
    assert row["authors_joined"] == "Ada Lovelace, Grace Hopper"
    assert row["categories_joined"] == "Machine Learning, Data Quality"
    assert row["published"] == "2026-01-01"
    assert int(row["age_days"]) == 10
    assert int(row["summary_chars"]) == len(row["summary"])
    assert row["text_for_embedding"] == (
        f"Title: {row['title']} | Authors: {row['authors_joined']} | Summary: {row['summary']}"
    )
    assert df["paper_id"].is_unique
    print("CP1 sample validation passed.")


if __name__ == "__main__":
    main()
