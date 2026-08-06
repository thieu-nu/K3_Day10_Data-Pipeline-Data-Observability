from __future__ import annotations

from pathlib import Path
from typing import Any


def generate_phase1_report(
    report_path: Path | str,
    source_summary: dict[str, Any],
    metrics: dict[str, Any],
    quality: dict[str, Any],
    freshness: dict[str, Any],
) -> None:
    """Viết markdown report cho baseline phase."""
    lines = [
        "# Phase 1 Baseline Report",
        "",
        "## 1. Source Summary",
        f"- **Source API**: {source_summary.get('source', 'N/A')}",
        f"- **Query**: {source_summary.get('query', 'N/A')}",
        f"- **Filter**: {source_summary.get('filter', 'N/A')}",
        f"- **Raw Records Count**: {source_summary.get('raw_count', 0)}",
        f"- **Cleaned Records Count**: {source_summary.get('clean_count', 0)}",
        f"- **Clean Contract Status**: {source_summary.get('clean_contract', 'GO')} (SHA256: `{str(source_summary.get('clean_snapshot_sha256', ''))[:12]}...`)",
        "",
        "## 2. Evaluation Metrics",
        f"- **Total Test Samples**: {metrics.get('samples', 0)}",
        f"- **Retrieval Hit Rate**: {metrics.get('retrieval_hit_rate', 0.0) * 100:.1f}%",
        f"- **Mean Token F1 Score**: {metrics.get('mean_token_f1', 0.0):.4f}",
        f"- **Judge Accuracy**: {metrics.get('judge_accuracy', 0.0) * 100:.1f}%",
        f"- **Mean Judge Score**: {metrics.get('mean_judge_score', 0.0):.2f} / 5.0",
        "",
        "## 3. Data Quality & Freshness",
        f"- **Quality Check Status**: {'PASSED' if quality.get('passed', False) else 'FAILED'}",
        f"- **Total Rows Verified**: {quality.get('total_rows', 0)} (Null IDs: {quality.get('null_ids', 0)}, Null Titles: {quality.get('null_titles', 0)})",
        f"- **Is Fresh**: {'Yes' if freshness.get('is_fresh', False) else 'No'} (Stale Rows: {freshness.get('stale_rows', 0)} / {freshness.get('total_rows', 0)})",
        f"- **Date Range**: {freshness.get('oldest_published', 'N/A')} to {freshness.get('latest_published', 'N/A')}",
        "",
        "---",
        "*Report generated automatically by Antigravity RAG Pipeline.*",
    ]

    out_file = Path(report_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text("\n".join(lines), encoding="utf-8")


def generate_corruption_report(
    report_path: Path | str,
    baseline_metrics: dict[str, Any],
    corrupted_metrics: dict[str, Any],
    repaired_metrics: dict[str, Any],
    corrupted_quality: dict[str, Any],
    repaired_quality: dict[str, Any],
    corrupted_freshness: dict[str, Any],
    repaired_freshness: dict[str, Any],
) -> None:
    """Viết markdown report so sánh baseline/corrupted/repaired."""
    lines = [
        "# Corruption Comparison Report (Phase 2)",
        "",
        "| Metric | Baseline | Corrupted | Repaired |",
        "| :--- | :---: | :---: | :---: |",
        f"| **Retrieval Hit Rate** | {baseline_metrics.get('retrieval_hit_rate', 0.0)*100:.1f}% | {corrupted_metrics.get('retrieval_hit_rate', 0.0)*100:.1f}% | {repaired_metrics.get('retrieval_hit_rate', 0.0)*100:.1f}% |",
        f"| **Mean Token F1** | {baseline_metrics.get('mean_token_f1', 0.0):.4f} | {corrupted_metrics.get('mean_token_f1', 0.0):.4f} | {repaired_metrics.get('mean_token_f1', 0.0):.4f} |",
        f"| **Judge Accuracy** | {baseline_metrics.get('judge_accuracy', 0.0)*100:.1f}% | {corrupted_metrics.get('judge_accuracy', 0.0)*100:.1f}% | {repaired_metrics.get('judge_accuracy', 0.0)*100:.1f}% |",
        "",
        "## Quality Summary",
        f"- Corrupted Passed: `{corrupted_quality.get('passed', False)}` | Repaired Passed: `{repaired_quality.get('passed', False)}`",
        f"- Corrupted Freshness: `{corrupted_freshness.get('is_fresh', False)}` | Repaired Freshness: `{repaired_freshness.get('is_fresh', False)}`",
    ]

    out_file = Path(report_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text("\n".join(lines), encoding="utf-8")

