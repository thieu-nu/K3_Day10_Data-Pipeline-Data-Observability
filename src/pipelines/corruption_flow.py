from __future__ import annotations

from datetime import UTC, datetime
import pandas as pd

from core.config import load_settings
from core.utils import read_json, write_csv, write_json
from evaluation.metrics import evaluate_pipeline
from ingestion.cleaning import build_clean_dataframe
from ingestion.corruption import corrupt_clean_dataframe
from ingestion.crossref import load_raw_records
from observability.quality import build_freshness_report, run_data_quality_checks
from observability.reporting import generate_corruption_report
from retrieval.index import LocalEmbeddingIndex


def main() -> None:
    """Xây dựng corruption -> evaluate -> repair -> compare flow."""
    settings = load_settings()
    print("1. Loading baseline clean dataset and metrics...")
    clean_df = pd.read_csv(settings.paths.clean_csv)
    try:
        baseline_metrics = read_json(settings.paths.baseline_metrics)
    except Exception:
        baseline_metrics = {}

    print("2. Generating corrupted dataset...")
    corrupted_df = corrupt_clean_dataframe(clean_df, settings.paths.corruption_log)

    print("3. Saving corrupted artifacts...")
    write_csv(corrupted_df, settings.paths.corrupted_clean_csv)
    write_json(settings.paths.corrupted_clean_json, corrupted_df.to_dict(orient="records"))

    print("4. Building corrupted vector index & evaluating...")
    corrupted_index = LocalEmbeddingIndex.build(
        corrupted_df,
        settings,
        embeddings_output_path=settings.paths.corrupted_embeddings_json,
    )
    corrupted_eval = evaluate_pipeline(
        settings=settings,
        index=corrupted_index,
        test_set_path=settings.paths.eval_testset,
        metrics_output_path=settings.paths.corrupted_metrics,
        answers_output_path=settings.paths.corrupted_answers,
    )

    print("5. Running data quality & freshness checks on corrupted data...")
    corrupted_quality = run_data_quality_checks(corrupted_df, settings, report_name="corrupted_quality.json")
    corrupted_freshness = build_freshness_report(corrupted_df, settings, settings.paths.quality_dir / "corrupted_freshness.json")

    print("6. Repairing dataset from original raw source records (Source Re-ingestion)...")
    raw_records = load_raw_records(settings.paths.raw_records_json)
    repaired_df = build_clean_dataframe(raw_records, run_date=datetime.now(UTC))
    write_csv(repaired_df, settings.paths.repaired_clean_csv)
    write_json(settings.paths.repaired_clean_json, repaired_df.to_dict(orient="records"))

    print("7. Building repaired vector index & re-evaluating...")
    repaired_index = LocalEmbeddingIndex.build(
        repaired_df,
        settings,
        embeddings_output_path=settings.paths.repaired_embeddings_json,
    )
    repaired_eval = evaluate_pipeline(
        settings=settings,
        index=repaired_index,
        test_set_path=settings.paths.eval_testset,
        metrics_output_path=settings.paths.repaired_metrics,
        answers_output_path=settings.paths.repaired_answers,
    )
    repaired_quality = run_data_quality_checks(repaired_df, settings, report_name="repaired_quality.json")
    repaired_freshness = build_freshness_report(repaired_df, settings, settings.paths.quality_dir / "repaired_freshness.json")

    print("8. Generating Phase 2 Comparison Report...")
    generate_corruption_report(
        report_path=settings.paths.comparison_report,
        baseline_metrics=baseline_metrics,
        corrupted_metrics=corrupted_eval.summary,
        repaired_metrics=repaired_eval.summary,
        corrupted_quality=corrupted_quality,
        repaired_quality=repaired_quality,
        corrupted_freshness=corrupted_freshness,
        repaired_freshness=repaired_freshness,
    )
    print(f" -> Comparison report written to: {settings.paths.comparison_report}")
