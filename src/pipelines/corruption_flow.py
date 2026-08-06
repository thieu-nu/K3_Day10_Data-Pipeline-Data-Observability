from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from core.config import Settings, load_settings
from core.utils import read_json, write_csv, write_json


class CorruptionFlowError(RuntimeError):
    """Raised when the flow cannot run honestly against the baseline it is comparing to."""


def _require(path: Path, what: str) -> Path:
    if not path.is_file():
        raise CorruptionFlowError(
            f"{what} is missing at {path}. Run `python script/run_phase1.py` first; "
            "the corruption flow only compares against a real baseline."
        )
    return path


def _load_locked_test_set(settings: Settings, baseline_metrics: dict[str, Any]) -> str:
    """Return the fingerprint of the baseline evaluation set, refusing any drift.

    The corrupted and repaired states must be scored on exactly the questions and ground
    truth the baseline was scored on. If the file changed since the baseline ran, the deltas
    would be meaningless, so the flow stops rather than producing a comparison.
    """
    from evaluation.testset import load_test_set, test_set_fingerprint, validate_test_set

    test_set = load_test_set(settings.paths.eval_testset)
    validate_test_set(test_set)  # structure only; documents go missing on purpose downstream
    fingerprint = test_set_fingerprint(test_set)

    recorded = baseline_metrics.get("evaluation_set_fingerprint")
    if recorded and recorded != fingerprint:
        raise CorruptionFlowError(
            "The evaluation set no longer matches the one the baseline was scored on "
            f"(baseline={recorded}, current={fingerprint}). Refusing to build a comparison "
            "across two different question sets. Restore data/eval/test_set.json or re-run "
            "the baseline."
        )
    return fingerprint


def _persist_dataframe(df: pd.DataFrame, csv_path: Path, json_path: Path) -> None:
    write_csv(df, csv_path)
    write_json(json_path, df.to_dict(orient="records"))


def _evaluate_state(
    settings: Settings,
    df: pd.DataFrame,
    *,
    state: str,
    embeddings_path: Path,
    dataset_path: Path,
    metrics_path: Path,
    answers_path: Path,
    quality_report_name: str,
    freshness_name: str,
) -> dict[str, Any]:
    """Index, evaluate and profile one dataset state with the locked evaluation set."""
    from evaluation.metrics import evaluate_pipeline
    from observability.quality import build_freshness_report, freshness_report_path, run_data_quality_checks
    from retrieval.index import LocalEmbeddingIndex

    index = LocalEmbeddingIndex.build(df, settings, embeddings_output_path=embeddings_path)
    evaluation = evaluate_pipeline(
        settings,
        index,
        settings.paths.eval_testset,
        metrics_path,
        answers_path,
        state=state,
        dataset_path=dataset_path,
    )
    quality = run_data_quality_checks(df, settings, quality_report_name)
    freshness = build_freshness_report(df, settings, freshness_report_path(settings, freshness_name))
    return {
        "metrics": evaluation.summary,
        "answers": evaluation.answers,
        "quality": quality,
        "freshness": freshness,
    }


def _read_baseline_observability(settings: Settings) -> tuple[dict | None, dict | None]:
    """Baseline quality/freshness written by phase 1, if the files are there."""
    from observability.quality import quality_report_path

    quality_path = quality_report_path(settings, "baseline_quality")
    freshness_path = settings.paths.freshness_report
    quality = read_json(quality_path) if quality_path.is_file() else None
    freshness = read_json(freshness_path) if freshness_path.is_file() else None
    return quality, freshness


def main() -> None:
    """Corrupt the clean corpus, measure the impact, repair from source, then compare.

    Runs only after a real baseline exists, reuses the locked evaluation set for all three
    states, and repairs by rebuilding from the raw Crossref snapshot rather than by undoing
    the corruption - a repair that reversed its own damage would prove nothing.
    """
    from ingestion.cleaning import build_clean_dataframe
    from ingestion.corruption import corrupt_clean_dataframe
    from ingestion.crossref import load_raw_records
    from observability.reporting import generate_corruption_report

    settings = load_settings()

    _require(settings.paths.baseline_metrics, "Baseline metrics")
    _require(settings.paths.eval_testset, "The evaluation set")
    _require(settings.paths.clean_json, "The cleaned dataset")
    _require(settings.paths.raw_records_json, "The raw Crossref snapshot")

    baseline_metrics = read_json(settings.paths.baseline_metrics)
    baseline_answers = (
        read_json(settings.paths.baseline_answers)
        if settings.paths.baseline_answers.is_file()
        else None
    )
    fingerprint = _load_locked_test_set(settings, baseline_metrics)
    baseline_quality, baseline_freshness = _read_baseline_observability(settings)

    clean_df = pd.DataFrame(read_json(settings.paths.clean_json))
    print(f"[corruption-flow] baseline rows={len(clean_df)} fingerprint={fingerprint}")

    # --- corrupted -------------------------------------------------------------------
    corrupted_df = corrupt_clean_dataframe(clean_df, settings.paths.corruption_log)
    _persist_dataframe(corrupted_df, settings.paths.corrupted_clean_csv, settings.paths.corrupted_clean_json)
    print(f"[corruption-flow] corrupted rows={len(corrupted_df)} log={settings.paths.corruption_log}")

    corrupted = _evaluate_state(
        settings,
        corrupted_df,
        state="corrupted",
        embeddings_path=settings.paths.corrupted_embeddings_json,
        dataset_path=settings.paths.corrupted_clean_csv,
        metrics_path=settings.paths.corrupted_metrics,
        answers_path=settings.paths.corrupted_answers,
        quality_report_name="corrupted_quality",
        freshness_name="corrupted_freshness",
    )

    # --- repaired: rebuilt from the raw snapshot, not from the corrupted frame ---------
    repaired_df = build_clean_dataframe(
        load_raw_records(settings.paths.raw_records_json), run_date=datetime.now(UTC)
    )
    _persist_dataframe(repaired_df, settings.paths.repaired_clean_csv, settings.paths.repaired_clean_json)
    print(f"[corruption-flow] repaired rows={len(repaired_df)} (rebuilt from raw records)")

    repaired = _evaluate_state(
        settings,
        repaired_df,
        state="repaired",
        embeddings_path=settings.paths.repaired_embeddings_json,
        dataset_path=settings.paths.repaired_clean_csv,
        metrics_path=settings.paths.repaired_metrics,
        answers_path=settings.paths.repaired_answers,
        quality_report_name="repaired_quality",
        freshness_name="repaired_freshness",
    )

    # --- comparison --------------------------------------------------------------------
    generate_corruption_report(
        settings.paths.comparison_report,
        baseline_metrics,
        corrupted["metrics"],
        repaired["metrics"],
        corrupted["quality"],
        repaired["quality"],
        corrupted["freshness"],
        repaired["freshness"],
        baseline_quality=baseline_quality,
        baseline_freshness=baseline_freshness,
        corruption_log=read_json(settings.paths.corruption_log),
        baseline_answers=baseline_answers,
        corrupted_answers=corrupted["answers"],
        repaired_answers=repaired["answers"],
    )
    print(f"[corruption-flow] comparison report -> {settings.paths.comparison_report}")
