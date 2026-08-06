from __future__ import annotations

from datetime import UTC, datetime

from core.clean_contract import (
    ValidatedCleanSnapshot,
    enforce_clean_contract,
    persist_cleaning_summary,
)
from core.config import Settings, load_settings
from core.utils import write_csv, write_json


def _load_or_fetch_raw_records(settings: Settings):
    from ingestion.crossref import fetch_source_records, load_raw_records

    if settings.paths.raw_records_json.is_file() and not settings.refresh_source:
        return load_raw_records(settings.paths.raw_records_json)
    return fetch_source_records(settings)


def _clean_and_persist(settings: Settings, records):
    from ingestion.cleaning import build_clean_dataframe

    clean_df = build_clean_dataframe(records, run_date=datetime.now(UTC))
    write_csv(clean_df, settings.paths.clean_csv)
    write_json(settings.paths.clean_json, clean_df.to_dict(orient="records"))
    persist_cleaning_summary(settings, raw_count=len(records), clean_df=clean_df)
    return clean_df


def _build_index_and_test_set_after_gate(
    settings: Settings,
    *,
    gate=enforce_clean_contract,
    index_builder=None,
    testset_builder=None,
):
    """Build downstream artifacts only from a validated clean snapshot.

    The gate call intentionally precedes resolving or invoking either downstream
    builder. When the contract is STOP, CleanContractError propagates and both
    the test-set and index call counts remain zero.
    """

    snapshot: ValidatedCleanSnapshot = gate(settings)

    if index_builder is None:
        from retrieval.index import LocalEmbeddingIndex

        index_builder = LocalEmbeddingIndex.build
    index = index_builder(
        snapshot.dataframe,
        settings,
        embeddings_output_path=settings.paths.embeddings_json,
    )

    if settings.refresh_test_set or not settings.paths.eval_testset.is_file():
        if testset_builder is None:
            from evaluation.testset import build_test_set

            testset_builder = build_test_set
        testset_builder(snapshot.dataframe, settings.paths.eval_testset)

    return snapshot, index


def main() -> None:
    """Run the baseline pipeline with a fail-closed clean-data handoff."""

    settings = load_settings()
    records = _load_or_fetch_raw_records(settings)
    _clean_and_persist(settings, records)

    # Contract boundary: neither index nor test set is called before this returns GO.
    snapshot, index = _build_index_and_test_set_after_gate(settings)

    from evaluation.metrics import evaluate_pipeline
    from observability.quality import build_freshness_report, run_data_quality_checks
    from observability.reporting import generate_phase1_report

    evaluation = evaluate_pipeline(
        settings=settings,
        index=index,
        test_set_path=settings.paths.eval_testset,
        metrics_output_path=settings.paths.baseline_metrics,
        answers_output_path=settings.paths.baseline_answers,
    )
    quality = run_data_quality_checks(
        snapshot.dataframe,
        settings,
        report_name="baseline_quality.json",
    )
    freshness = build_freshness_report(
        snapshot.dataframe,
        settings,
        settings.paths.freshness_report,
    )
    generate_phase1_report(
        report_path=settings.paths.baseline_report,
        source_summary={
            "source": settings.source_api,
            "query": settings.source_query,
            "filter": settings.source_filter,
            "raw_count": snapshot.report.counts["raw_count"],
            "clean_count": snapshot.report.counts["clean_json_count"],
            "clean_contract": "clean-v1",
            "clean_snapshot_sha256": snapshot.report.clean_snapshot_sha256,
            "clean_gate_report": str(settings.paths.clean_gate_report),
        },
        metrics=evaluation.summary,
        quality=quality,
        freshness=freshness,
    )
