from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from core.utils import now_utc, redact_secrets, write_text

NOT_AVAILABLE = "N/A"
PENDING = "Pending"

# (label, metrics key, needs a real judge result on both sides)
COMPARISON_METRICS: tuple[tuple[str, str, bool], ...] = (
    ("retrieval_hit_rate", "retrieval_hit_rate", False),
    ("semantic_retrieval_hit_rate", "semantic_retrieval_hit_rate", False),
    ("exact_lookup_success_rate", "exact_lookup_success_rate", False),
    ("mean_token_f1", "mean_token_f1", False),
    ("judge_accuracy", "judge_accuracy", True),
    ("mean_judge_score", "mean_judge_score", True),
)

SEMANTIC_TOPIC_TYPE = "semantic_topic"
ROUTE_EXACT_LOOKUP = "exact_lookup"
ROUTE_SEMANTIC_SEARCH = "semantic_search"


# --- formatting ------------------------------------------------------------------------------


def _clean(value: Any) -> str:
    """Render free text safe for a markdown table cell, with credentials masked."""
    text = redact_secrets("" if value is None else str(value))
    return text.replace("|", r"\|").replace("\n", " ").replace("\r", " ").strip()


def _fmt(value: Any, digits: int = 4) -> str:
    """Render a metric. None stays N/A; it is never coerced to 0."""
    if value is None:
        return NOT_AVAILABLE
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, (list, tuple)):
        return ", ".join(_clean(item) for item in value) if value else "(none)"
    return _clean(value)


def _fmt_delta(new: Any, old: Any, digits: int = 4) -> str:
    if not isinstance(new, (int, float)) or not isinstance(old, (int, float)):
        return NOT_AVAILABLE
    if isinstance(new, bool) or isinstance(old, bool):
        return NOT_AVAILABLE
    return f"{float(new) - float(old):+.{digits}f}"


def _direction(new: Any, old: Any, higher_is_better: bool = True) -> str:
    if not isinstance(new, (int, float)) or not isinstance(old, (int, float)):
        return ""
    if new == old:
        return "unchanged"
    improved = new > old if higher_is_better else new < old
    return "improved" if improved else "degraded"


def _table(header: Iterable[str], rows: Iterable[Iterable[str]]) -> list[str]:
    header = list(header)
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join(["---"] * len(header)) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    return lines


def _kv_table(payload: Any, title_key: str = "Field", title_value: str = "Value") -> list[str]:
    """Render an arbitrary summary dict without assuming its shape."""
    if not isinstance(payload, dict) or not payload:
        return ["_Not supplied._"]
    rows = []
    for key, value in payload.items():
        if isinstance(value, dict):
            rendered = ", ".join(f"{k}={_clean(v)}" for k, v in value.items())
        elif isinstance(value, (list, tuple)):
            rendered = _fmt(list(value))
        else:
            rendered = _fmt(value)
        rows.append([f"`{_clean(key)}`", rendered])
    return _table([title_key, title_value], rows)


def _get(payload: Any, key: str, default: Any = None) -> Any:
    return payload.get(key, default) if isinstance(payload, dict) else default


def _quality_status(payload: Any) -> Any:
    summary = _get(payload, "summary")
    return _get(summary, "overall_status")


def _freshness_status(payload: Any) -> Any:
    return _get(payload, "status")


def _judge_has_result(metrics: Any) -> bool:
    return bool(_get(metrics, "judge_success_count", 0))


def _bullets(title: str, items: Any, empty: str) -> list[str]:
    lines = [f"### {title}", ""]
    if not items:
        lines.append(empty)
        lines.append("")
        return lines
    for item in items:
        if isinstance(item, dict):
            parts = ", ".join(f"{key}={_clean(value)}" for key, value in item.items())
            lines.append(f"- {parts}")
        else:
            lines.append(f"- {_clean(item)}")
    lines.append("")
    return lines


# --- phase 1 report ---------------------------------------------------------------------------


def generate_phase1_report(
    report_path,
    source_summary: dict[str, Any],
    metrics: dict[str, Any],
    quality: dict[str, Any],
    freshness: dict[str, Any],
) -> None:
    """Render the baseline report straight from the artifacts handed in.

    Every number is read out of `metrics`, `quality` and `freshness`; nothing is recomputed
    or hard-coded, including the provider and model. A metric that is null is shown as N/A
    with the artifact's own warnings reproduced below, never as 0.
    """
    report_path = Path(report_path)
    lines: list[str] = [
        "# Phase 1 - Baseline Report",
        "",
        f"Generated at: {now_utc().isoformat()}",
        f"Evaluation state: `{_fmt(_get(metrics, 'state'))}`",
        "",
        "## 1. Source",
        "",
        *_kv_table(source_summary),
        "",
        "## 2. Dataset and index",
        "",
        *_table(
            ["Field", "Value"],
            [
                ["Dataset path", _fmt(_get(metrics, "dataset_path"))],
                ["Collection", _fmt(_get(metrics, "collection_name"))],
                ["Documents indexed", _fmt(_get(metrics, "index_document_count"))],
                ["Embedding model", _fmt(_get(metrics, "embedding_model"))],
                ["top_k", _fmt(_get(metrics, "top_k"))],
                ["Rows in quality run", _fmt(_get(quality, "dataset_rows"))],
                ["Clean schema version", _fmt(_get(quality, "schema_version"))],
            ],
        ),
        "",
        "## 3. Evaluation set",
        "",
        *_table(
            ["Field", "Value"],
            [
                ["Path", _fmt(_get(metrics, "evaluation_set_path"))],
                ["Fingerprint", f"`{_fmt(_get(metrics, 'evaluation_set_fingerprint'))}`"],
                ["Questions in file", _fmt(_get(metrics, "samples"))],
                ["Evaluated", _fmt(_get(metrics, "evaluated_questions"))],
                ["Failed", _fmt(_get(metrics, "failed_questions"))],
            ],
        ),
        "",
        "## 4. LLM provider",
        "",
        *_table(
            ["Field", "Value"],
            [
                ["Provider", _fmt(_get(metrics, "provider"))],
                ["Model", _fmt(_get(metrics, "model"))],
                ["Judge rubric version", _fmt(_get(metrics, "judge_rubric_version"))],
            ],
        ),
        "",
        "_No credential is recorded here; only the provider and model names are._",
        "",
        "## 5. Retrieval metrics",
        "",
        *_table(
            ["Metric", "Value", "Denominator"],
            [
                [
                    "retrieval_hit_rate",
                    _fmt(_get(metrics, "retrieval_hit_rate")),
                    f"{_fmt(_get(metrics, 'hit_count'))} / {_fmt(_get(metrics, 'evaluated_questions'))}",
                ],
                [
                    "semantic_retrieval_hit_rate",
                    _fmt(_get(metrics, "semantic_retrieval_hit_rate")),
                    f"{_fmt(_get(metrics, 'semantic_hit_count'))} / {_fmt(_get(metrics, 'semantic_samples'))}",
                ],
                [
                    "exact_lookup_success_rate",
                    _fmt(_get(metrics, "exact_lookup_success_rate")),
                    f"{_fmt(_get(metrics, 'exact_lookup_hit_count'))} / {_fmt(_get(metrics, 'exact_lookup_samples'))}",
                ],
            ],
        ),
        "",
        "`exact_lookup_success_rate` measures the exact-title shortcut in `retrieval.qa`, not "
        "semantic search; the two are reported apart on purpose.",
        "",
        "## 6. Answer quality",
        "",
        *_table(
            ["Metric", "Value"],
            [["mean_token_f1", _fmt(_get(metrics, "mean_token_f1"))]],
        ),
        "",
        f"Token F1 definition: {_clean(_get(metrics, 'token_f1_definition', 'not recorded'))}",
        "",
        "## 7. LLM-as-a-judge",
        "",
        *_table(
            ["Field", "Value"],
            [
                ["Status", _fmt(_get(metrics, "judge_status"))],
                ["Successful calls", _fmt(_get(metrics, "judge_success_count"))],
                ["Failed calls", _fmt(_get(metrics, "judge_failure_count"))],
                ["judge_accuracy", _fmt(_get(metrics, "judge_accuracy"))],
                [
                    "mean_judge_score",
                    f"{_fmt(_get(metrics, 'mean_judge_score'))} "
                    f"(scale {_fmt(_get(metrics, 'mean_judge_score_scale'))})",
                ],
                ["Initialisation error", _fmt(_get(metrics, "judge_init_error"))],
            ],
        ),
        "",
    ]

    if not _judge_has_result(metrics):
        lines += [
            "No judge call succeeded, so `judge_accuracy` and `mean_judge_score` are N/A. They "
            "are not substituted with token overlap or any other heuristic.",
            "",
        ]

    quality_summary = _get(quality, "summary", {}) or {}
    lines += [
        "## 8. Data quality",
        "",
        *_table(
            ["Field", "Value"],
            [
                ["Report", _fmt(_get(quality, "report_name"))],
                ["Overall status", _fmt(quality_summary.get("overall_status"))],
                ["Checks", _fmt(quality_summary.get("total"))],
                ["Passed", _fmt(quality_summary.get("passed"))],
                ["Warned", _fmt(quality_summary.get("warned"))],
                ["Failed", _fmt(quality_summary.get("failed"))],
            ],
        ),
        "",
    ]

    checks = _get(quality, "checks") or []
    if checks:
        lines += _table(
            ["Check", "Dimension", "Status", "Observed", "Expected", "Affected/Total"],
            [
                [
                    f"`{_clean(_get(check, 'check_name'))}`",
                    _fmt(_get(check, "quality_dimension")),
                    _fmt(_get(check, "status")),
                    _fmt(_get(check, "observed_value")),
                    _fmt(_get(check, "expected_condition")),
                    f"{_fmt(_get(check, 'affected_count'))}/{_fmt(_get(check, 'total_count'))}",
                ]
                for check in checks
            ],
        )
        lines.append("")

    lines += [
        "## 9. Freshness",
        "",
        *_table(
            ["Field", "Value"],
            [
                ["Status", _fmt(_freshness_status(freshness))],
                ["Measured from", _fmt(_get(freshness, "measured_from"))],
                ["Threshold (days)", _fmt(_get(freshness, "threshold_days"))],
                ["Rows", _fmt(_get(freshness, "row_count"))],
                ["Stale rows", _fmt(_get(freshness, "stale_rows"))],
                ["Rows without a usable date", _fmt(_get(freshness, "invalid_or_missing_date_rows"))],
                ["Rows without a usable age", _fmt(_get(freshness, "invalid_or_missing_age_rows"))],
                ["Latest published", _fmt(_get(freshness, "latest_published"))],
                ["Oldest published", _fmt(_get(freshness, "oldest_published"))],
                [
                    "age_days min/mean/max",
                    f"{_fmt(_get(freshness, 'min_age_days'))} / "
                    f"{_fmt(_get(freshness, 'mean_age_days'))} / "
                    f"{_fmt(_get(freshness, 'max_age_days'))}",
                ],
                ["Reason", _fmt(_get(freshness, "reason"))],
            ],
        ),
        "",
        "## 10. Artifacts",
        "",
        *_table(
            ["Artifact", "Path"],
            [
                ["Evaluation set", _fmt(_get(metrics, "evaluation_set_path"))],
                ["Dataset", _fmt(_get(metrics, "dataset_path"))],
                ["Quality report", _fmt(_get(quality, "report_path"))],
                ["Freshness report", _fmt(_get(freshness, "report_path"))],
                ["This report", _clean(report_path)],
            ],
        ),
        "",
        "## 11. Errors and warnings",
        "",
        *_bullets("Warnings", _get(metrics, "warnings"), "_No warning was recorded._"),
        *_bullets("Errors", _get(metrics, "errors"), "_No error was recorded._"),
        "## 12. Limitations",
        "",
        "- Metrics describe this dataset, index and evaluation set only; they are not a "
        "general statement about the retrieval stack.",
        "- Questions whose title resolves through the exact lookup in `retrieval.qa` bypass "
        "semantic ranking, so `retrieval_hit_rate` mixes two retrieval paths. Read "
        "`semantic_retrieval_hit_rate` for the semantic signal.",
        "- Token F1 rewards vocabulary overlap, not factual correctness.",
        "- Judge scores, when present, come from a single model at temperature 0 and are not "
        "calibrated against human grading.",
        "",
    ]

    write_text(report_path, "\n".join(lines).rstrip() + "\n")


# --- corruption comparison ------------------------------------------------------------------------


def _answers_by_id(answers: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(answers, list):
        return {}
    return {
        str(item.get("id")): item
        for item in answers
        if isinstance(item, dict) and item.get("id") is not None
    }


def _semantic_topic_breakdown(answers: Any) -> dict[str, Any]:
    """Hit rate over the fixed semantic_topic questions.

    These never carry a quoted title, so they stay on the semantic route in every state and
    keep the same denominator - unlike the route-derived semantic slice, which grows when a
    corrupted title stops resolving through the exact lookup.
    """
    evaluated = [
        item
        for item in (answers or [])
        if isinstance(item, dict)
        and item.get("question_type") == SEMANTIC_TOPIC_TYPE
        and item.get("status") == "evaluated"
    ]
    if not evaluated:
        return {"samples": 0, "hit_count": 0, "hit_rate": None}
    hit_count = sum(1 for item in evaluated if item.get("retrieval_hit"))
    return {
        "samples": len(evaluated),
        "hit_count": hit_count,
        "hit_rate": hit_count / len(evaluated),
    }


def _route_counts(answers: Any) -> dict[str, int]:
    counts = {ROUTE_EXACT_LOOKUP: 0, ROUTE_SEMANTIC_SEARCH: 0}
    for item in answers or []:
        route = item.get("evaluation_route") if isinstance(item, dict) else None
        if route in counts:
            counts[route] += 1
    return counts


def _collect_corruption_records(payload: Any) -> list[dict[str, Any]]:
    """Walk an unknown-shaped corruption log and pull out anything carrying a paper_id.

    The log is produced by another role and its schema is not fixed here, so the walk stays
    structural rather than assuming particular keys.
    """
    found: list[dict[str, Any]] = []

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            if any(key in node for key in ("paper_id", "record_id", "id")):
                found.append(node)
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)

    visit(payload)
    return found


def _corruption_index(corruption_log: Any) -> dict[str, list[dict[str, Any]]]:
    index: dict[str, list[dict[str, Any]]] = {}
    for record in _collect_corruption_records(corruption_log):
        for key in ("paper_id", "record_id", "id"):
            value = record.get(key)
            if value is None:
                continue
            index.setdefault(str(value).strip(), []).append(record)
            break
    return index


def _describe_corruption_record(record: dict[str, Any]) -> str:
    interesting = [
        key
        for key in ("corruption_type", "type", "scenario", "field", "affected_field", "action", "reason")
        if key in record
    ]
    if not interesting:
        return ", ".join(f"{key}={_clean(value)}" for key, value in list(record.items())[:4])
    return ", ".join(f"{key}={_clean(record[key])}" for key in interesting)


def _degradation_candidates(
    baseline_answers: Any, corrupted_answers: Any
) -> list[dict[str, Any]]:
    """Pair samples by id and score how much each one got worse."""
    baseline_by_id = _answers_by_id(baseline_answers)
    corrupted_by_id = _answers_by_id(corrupted_answers)
    candidates: list[dict[str, Any]] = []

    for sample_id, before in baseline_by_id.items():
        after = corrupted_by_id.get(sample_id)
        if after is None:
            continue
        if before.get("status") != "evaluated" or after.get("status") != "evaluated":
            continue

        signals: list[str] = []
        severity = 0.0

        before_hit, after_hit = before.get("retrieval_hit"), after.get("retrieval_hit")
        if before_hit and not after_hit:
            signals.append("retrieval hit lost")
            severity += 100

        before_rank, after_rank = before.get("hit_rank"), after.get("hit_rank")
        if isinstance(before_rank, int) and isinstance(after_rank, int) and after_rank > before_rank:
            signals.append(f"hit rank {before_rank} -> {after_rank}")
            severity += 20 + (after_rank - before_rank)

        before_f1, after_f1 = before.get("token_f1"), after.get("token_f1")
        if isinstance(before_f1, (int, float)) and isinstance(after_f1, (int, float)) and after_f1 < before_f1:
            signals.append(f"token F1 {before_f1:.4f} -> {after_f1:.4f}")
            severity += 10 * (before_f1 - after_f1)

        before_route, after_route = before.get("evaluation_route"), after.get("evaluation_route")
        if before_route == ROUTE_EXACT_LOOKUP and after_route == ROUTE_SEMANTIC_SEARCH:
            signals.append("exact lookup no longer resolves; fell back to semantic search")
            severity += 50

        before_answer = (before.get("answer") or "").strip()
        after_answer = (after.get("answer") or "").strip()
        if before_answer and not after_answer:
            signals.append("answer became empty")
            severity += 40

        before_judge, after_judge = before.get("judge"), after.get("judge")
        if isinstance(before_judge, dict) and isinstance(after_judge, dict):
            before_score, after_score = before_judge.get("score"), after_judge.get("score")
            if isinstance(before_score, int) and isinstance(after_score, int) and after_score < before_score:
                signals.append(f"judge score {before_score} -> {after_score}")
                severity += 15 * (before_score - after_score)

        if signals:
            candidates.append(
                {
                    "id": sample_id,
                    "severity": severity,
                    "signals": signals,
                    "baseline": before,
                    "corrupted": after,
                }
            )

    candidates.sort(key=lambda item: (-item["severity"], item["id"]))
    return candidates


def _degradation_section(
    baseline_answers: Any, corrupted_answers: Any, corruption_log: Any
) -> list[str]:
    lines = ["## 5. Degradation evidence", ""]

    if not baseline_answers or not corrupted_answers:
        lines += [
            "_Baseline and corrupted answer artifacts were not both supplied, so no per-question "
            "comparison could be made._",
            "",
        ]
        return lines

    candidates = _degradation_candidates(baseline_answers, corrupted_answers)
    if not candidates:
        lines += [
            "**No degraded case was found on the current evaluation set.**",
            "",
            "Every paired question kept its retrieval hit, rank, token F1 and route. This is "
            "reported as measured; no example is invented. Plausible explanations, each "
            "checkable against the artifacts:",
            "",
            "- the corruption did not touch any document referenced by "
            "`ground_truth_doc_ids`;",
            "- the corrupted documents were touched in fields that do not drive retrieval for "
            "these questions;",
            "- top-k is wide enough that the target document still ranks inside it.",
            "",
        ]
        return lines

    worst = candidates[0]
    before, after = worst["baseline"], worst["corrupted"]
    corruption_map = _corruption_index(corruption_log)
    doc_ids = [str(doc_id) for doc_id in (before.get("ground_truth_doc_ids") or [])]
    matched = [(doc_id, corruption_map[doc_id]) for doc_id in doc_ids if doc_id in corruption_map]

    lines += [
        f"{len(candidates)} question(s) got worse. The most affected one:",
        "",
        *_table(
            ["Field", "Baseline", "Corrupted"],
            [
                ["Sample id", f"`{_clean(worst['id'])}`", ""],
                ["Question type", _fmt(before.get("question_type")), ""],
                ["Question", _clean(before.get("question")), ""],
                ["Ground truth doc ids", _fmt(doc_ids), ""],
                [
                    "Retrieved doc ids",
                    _fmt(before.get("retrieved_doc_ids")),
                    _fmt(after.get("retrieved_doc_ids")),
                ],
                ["Retrieval hit", _fmt(before.get("retrieval_hit")), _fmt(after.get("retrieval_hit"))],
                ["Hit rank", _fmt(before.get("hit_rank")), _fmt(after.get("hit_rank"))],
                ["Route", _fmt(before.get("evaluation_route")), _fmt(after.get("evaluation_route"))],
                ["token_f1", _fmt(before.get("token_f1")), _fmt(after.get("token_f1"))],
                [
                    "Judge score",
                    _fmt(_get(before.get("judge"), "score")),
                    _fmt(_get(after.get("judge"), "score")),
                ],
            ],
        ),
        "",
        "Signals detected: " + "; ".join(_clean(signal) for signal in worst["signals"]) + ".",
        "",
    ]

    if matched:
        lines.append("Matching corruption-log entries for this question's ground-truth documents:")
        lines.append("")
        lines += _table(
            ["paper_id", "Corruption record"],
            [
                [f"`{_clean(doc_id)}`", _clean(_describe_corruption_record(record))]
                for doc_id, records in matched
                for record in records
            ],
        )
        lines.append("")
    elif corruption_log:
        lines += [
            "No corruption-log entry could be matched to this question's ground-truth "
            "documents. The change is therefore an **association**, not a demonstrated cause.",
            "",
        ]
    else:
        lines += [
            "No corruption log was supplied, so the change cannot be tied to a specific "
            "corruption record. Treat it as an **observation**, not a demonstrated cause.",
            "",
        ]

    if len(candidates) > 1:
        lines.append("All degraded questions:")
        lines.append("")
        lines += _table(
            ["Sample id", "Type", "Signals"],
            [
                [
                    f"`{_clean(item['id'])}`",
                    _fmt(item["baseline"].get("question_type")),
                    "; ".join(_clean(signal) for signal in item["signals"]),
                ]
                for item in candidates
            ],
        )
        lines.append("")

    return lines


def _comparison_rows(
    baseline_metrics: Any,
    corrupted_metrics: Any,
    repaired_metrics: Any,
) -> list[list[str]]:
    rows: list[list[str]] = []
    baseline_judge = _judge_has_result(baseline_metrics)
    corrupted_judge = _judge_has_result(corrupted_metrics)
    repaired_judge = _judge_has_result(repaired_metrics)

    for label, key, judge_gated in COMPARISON_METRICS:
        base = _get(baseline_metrics, key)
        corrupt = _get(corrupted_metrics, key)
        repaired = _get(repaired_metrics, key)

        note = ""
        if judge_gated and not (baseline_judge and corrupted_judge):
            corruption_delta = NOT_AVAILABLE
            note = (
                "not compared: no successful judge call on "
                + ("baseline" if not baseline_judge else "corrupted")
            )
        else:
            corruption_delta = _fmt_delta(corrupt, base)
            note = _direction(corrupt, base)

        if repaired_metrics is None:
            repaired_cell = PENDING
            recovery = PENDING
        elif judge_gated and not (repaired_judge and corrupted_judge):
            repaired_cell = _fmt(repaired)
            recovery = NOT_AVAILABLE
        else:
            repaired_cell = _fmt(repaired)
            recovery = _fmt_delta(repaired, corrupt)

        if key == "semantic_retrieval_hit_rate":
            base_n = _get(baseline_metrics, "semantic_samples")
            corrupt_n = _get(corrupted_metrics, "semantic_samples")
            if base_n != corrupt_n:
                note = (
                    f"WARNING different denominators (baseline n={_fmt(base_n)}, "
                    f"corrupted n={_fmt(corrupt_n)}); route membership shifted, so this delta is "
                    "not a like-for-like comparison"
                ) + (f"; {note}" if note else "")

        rows.append(
            [label, _fmt(base), _fmt(corrupt), repaired_cell, corruption_delta, recovery, note or "-"]
        )
    return rows


def _status_row(
    label: str,
    baseline_value: Any,
    corrupted_value: Any,
    repaired_value: Any,
    repaired_supplied: bool,
) -> list[str]:
    note = "no numeric delta for a status value"
    if baseline_value is not None and corrupted_value is not None:
        note = (
            f"{_clean(baseline_value)} -> {_clean(corrupted_value)}"
            if baseline_value != corrupted_value
            else "unchanged"
        )
    return [
        label,
        _fmt(baseline_value),
        _fmt(corrupted_value),
        PENDING if not repaired_supplied else _fmt(repaired_value),
        "-",
        PENDING if not repaired_supplied else "-",
        note,
    ]


def generate_corruption_report(
    report_path,
    baseline_metrics: dict[str, Any],
    corrupted_metrics: dict[str, Any],
    repaired_metrics: dict[str, Any],
    corrupted_quality: dict[str, Any],
    repaired_quality: dict[str, Any],
    corrupted_freshness: dict[str, Any],
    repaired_freshness: dict[str, Any],
    *,
    baseline_quality: dict[str, Any] | None = None,
    baseline_freshness: dict[str, Any] | None = None,
    corruption_log: Any | None = None,
    baseline_answers: list[dict[str, Any]] | None = None,
    corrupted_answers: list[dict[str, Any]] | None = None,
    repaired_answers: list[dict[str, Any]] | None = None,
) -> None:
    """Render the state comparison from artifacts only.

    Positional parameters and their order are unchanged. Everything added is keyword-only
    with a `None` default, so an existing eight-argument call still works: pass
    `baseline_quality`/`baseline_freshness` to fill the baseline column of the two status
    rows, and the answer artifacts plus `corruption_log` to get the per-question evidence.

    Repaired inputs may be `None` at checkpoint 5; those cells render as "Pending" and no
    number is invented for them.
    """
    report_path = Path(report_path)
    repaired_supplied = repaired_metrics is not None
    states = ["baseline", "corrupted"] + (["repaired"] if repaired_supplied else [])

    baseline_fp = _get(baseline_metrics, "evaluation_set_fingerprint")
    corrupted_fp = _get(corrupted_metrics, "evaluation_set_fingerprint")
    repaired_fp = _get(repaired_metrics, "evaluation_set_fingerprint")
    fingerprints = [baseline_fp, corrupted_fp] + ([repaired_fp] if repaired_supplied else [])
    same_fingerprint = len({fp for fp in fingerprints if fp is not None}) == 1 and all(
        fp is not None for fp in fingerprints
    )

    lines: list[str] = [
        "# Corruption Impact Report",
        "",
        f"Generated at: {now_utc().isoformat()}",
        f"States covered: {', '.join(states)}"
        + ("" if repaired_supplied else "  (repaired pending)"),
        "",
        "## 1. Run identity",
        "",
        *_table(
            ["Field", "Baseline", "Corrupted", "Repaired"],
            [
                [
                    "Evaluation set fingerprint",
                    f"`{_fmt(baseline_fp)}`",
                    f"`{_fmt(corrupted_fp)}`",
                    f"`{_fmt(repaired_fp)}`" if repaired_supplied else PENDING,
                ],
                [
                    "Evaluation set path",
                    _fmt(_get(baseline_metrics, "evaluation_set_path")),
                    _fmt(_get(corrupted_metrics, "evaluation_set_path")),
                    _fmt(_get(repaired_metrics, "evaluation_set_path")) if repaired_supplied else PENDING,
                ],
                [
                    "Dataset",
                    _fmt(_get(baseline_metrics, "dataset_path")),
                    _fmt(_get(corrupted_metrics, "dataset_path")),
                    _fmt(_get(repaired_metrics, "dataset_path")) if repaired_supplied else PENDING,
                ],
                [
                    "Collection",
                    _fmt(_get(baseline_metrics, "collection_name")),
                    _fmt(_get(corrupted_metrics, "collection_name")),
                    _fmt(_get(repaired_metrics, "collection_name")) if repaired_supplied else PENDING,
                ],
                [
                    "Documents indexed",
                    _fmt(_get(baseline_metrics, "index_document_count")),
                    _fmt(_get(corrupted_metrics, "index_document_count")),
                    _fmt(_get(repaired_metrics, "index_document_count")) if repaired_supplied else PENDING,
                ],
                [
                    "Provider / model",
                    f"{_fmt(_get(baseline_metrics, 'provider'))} / {_fmt(_get(baseline_metrics, 'model'))}",
                    f"{_fmt(_get(corrupted_metrics, 'provider'))} / {_fmt(_get(corrupted_metrics, 'model'))}",
                    (
                        f"{_fmt(_get(repaired_metrics, 'provider'))} / "
                        f"{_fmt(_get(repaired_metrics, 'model'))}"
                        if repaired_supplied
                        else PENDING
                    ),
                ],
                [
                    "Embedding model",
                    _fmt(_get(baseline_metrics, "embedding_model")),
                    _fmt(_get(corrupted_metrics, "embedding_model")),
                    _fmt(_get(repaired_metrics, "embedding_model")) if repaired_supplied else PENDING,
                ],
                [
                    "top_k",
                    _fmt(_get(baseline_metrics, "top_k")),
                    _fmt(_get(corrupted_metrics, "top_k")),
                    _fmt(_get(repaired_metrics, "top_k")) if repaired_supplied else PENDING,
                ],
            ],
        ),
        "",
    ]

    if same_fingerprint:
        lines += ["All states were evaluated against the same locked evaluation set.", ""]
    else:
        lines += [
            "**WARNING: the evaluation-set fingerprints do not all match.** The states below "
            "were not scored against the same questions, so the deltas are not comparable.",
            "",
        ]

    lines += [
        "## 2. Comparison",
        "",
        *_table(
            [
                "Metric/signal",
                "Baseline",
                "Corrupted",
                "Repaired",
                "Corruption delta",
                "Recovery",
                "Note",
            ],
            _comparison_rows(baseline_metrics, corrupted_metrics, repaired_metrics)
            + [
                _status_row(
                    "quality status",
                    _quality_status(baseline_quality),
                    _quality_status(corrupted_quality),
                    _quality_status(repaired_quality),
                    repaired_supplied or repaired_quality is not None,
                ),
                _status_row(
                    "freshness status",
                    _freshness_status(baseline_freshness),
                    _freshness_status(corrupted_freshness),
                    _freshness_status(repaired_freshness),
                    repaired_supplied or repaired_freshness is not None,
                ),
            ],
        ),
        "",
        "Corruption delta is `corrupted - baseline`; recovery is `repaired - corrupted`. A null "
        "metric stays N/A and is never treated as 0.",
        "",
    ]

    if baseline_quality is None or baseline_freshness is None:
        lines += [
            "_Baseline quality and/or freshness artifacts were not passed in, so those baseline "
            "cells are N/A. Pass `baseline_quality=` and `baseline_freshness=` to fill them._",
            "",
        ]

    # --- semantic breakdown ---
    baseline_topic = _semantic_topic_breakdown(baseline_answers)
    corrupted_topic = _semantic_topic_breakdown(corrupted_answers)
    repaired_topic = _semantic_topic_breakdown(repaired_answers)
    baseline_routes = _route_counts(baseline_answers)
    corrupted_routes = _route_counts(corrupted_answers)

    lines += [
        "## 3. Semantic retrieval, split by how the route was reached",
        "",
        "`semantic_topic` questions never carry a quoted title, so they stay on the semantic "
        "route in every state and keep a stable denominator. The route-derived semantic slice "
        "in section 2 also absorbs questions whose quoted title stopped resolving, which is "
        "itself a corruption signal but moves the denominator.",
        "",
        *_table(
            ["Slice", "Baseline", "Corrupted", "Repaired"],
            [
                [
                    "semantic_topic hit rate (fixed set)",
                    _fmt(baseline_topic["hit_rate"]),
                    _fmt(corrupted_topic["hit_rate"]),
                    _fmt(repaired_topic["hit_rate"]) if repaired_supplied else PENDING,
                ],
                [
                    "semantic_topic samples",
                    _fmt(baseline_topic["samples"]),
                    _fmt(corrupted_topic["samples"]),
                    _fmt(repaired_topic["samples"]) if repaired_supplied else PENDING,
                ],
                [
                    "route = exact_lookup",
                    _fmt(baseline_routes[ROUTE_EXACT_LOOKUP]),
                    _fmt(corrupted_routes[ROUTE_EXACT_LOOKUP]),
                    PENDING if not repaired_supplied else _fmt(_route_counts(repaired_answers)[ROUTE_EXACT_LOOKUP]),
                ],
                [
                    "route = semantic_search",
                    _fmt(baseline_routes[ROUTE_SEMANTIC_SEARCH]),
                    _fmt(corrupted_routes[ROUTE_SEMANTIC_SEARCH]),
                    PENDING if not repaired_supplied else _fmt(_route_counts(repaired_answers)[ROUTE_SEMANTIC_SEARCH]),
                ],
            ],
        ),
        "",
    ]

    lost_lookups = baseline_routes[ROUTE_EXACT_LOOKUP] - corrupted_routes[ROUTE_EXACT_LOOKUP]
    if baseline_answers and corrupted_answers and lost_lookups > 0:
        lines += [
            f"{lost_lookups} question(s) that resolved through the exact lookup at baseline no "
            "longer do so after corruption, which is consistent with titles being altered.",
            "",
        ]

    # --- quality and freshness detail ---
    lines += [
        "## 4. Quality and freshness detail",
        "",
        *_table(
            ["Signal", "Baseline", "Corrupted", "Repaired"],
            [
                [
                    "quality overall_status",
                    _fmt(_quality_status(baseline_quality)),
                    _fmt(_quality_status(corrupted_quality)),
                    _fmt(_quality_status(repaired_quality)),
                ],
                [
                    "quality failed checks",
                    _fmt(_get(_get(baseline_quality, "summary"), "failed")),
                    _fmt(_get(_get(corrupted_quality, "summary"), "failed")),
                    _fmt(_get(_get(repaired_quality, "summary"), "failed")),
                ],
                [
                    "quality dataset rows",
                    _fmt(_get(baseline_quality, "dataset_rows")),
                    _fmt(_get(corrupted_quality, "dataset_rows")),
                    _fmt(_get(repaired_quality, "dataset_rows")),
                ],
                [
                    "freshness status",
                    _fmt(_freshness_status(baseline_freshness)),
                    _fmt(_freshness_status(corrupted_freshness)),
                    _fmt(_freshness_status(repaired_freshness)),
                ],
                [
                    "stale rows",
                    _fmt(_get(baseline_freshness, "stale_rows")),
                    _fmt(_get(corrupted_freshness, "stale_rows")),
                    _fmt(_get(repaired_freshness, "stale_rows")),
                ],
                [
                    "oldest published",
                    _fmt(_get(baseline_freshness, "oldest_published")),
                    _fmt(_get(corrupted_freshness, "oldest_published")),
                    _fmt(_get(repaired_freshness, "oldest_published")),
                ],
                [
                    "max age_days",
                    _fmt(_get(baseline_freshness, "max_age_days")),
                    _fmt(_get(corrupted_freshness, "max_age_days")),
                    _fmt(_get(repaired_freshness, "max_age_days")),
                ],
            ],
        ),
        "",
    ]

    failing_checks = [
        check
        for check in (_get(corrupted_quality, "checks") or [])
        if _get(check, "status") in {"fail", "warning"}
    ]
    if failing_checks:
        lines.append("Corrupted-state checks that did not pass:")
        lines.append("")
        lines += _table(
            ["Check", "Dimension", "Status", "Observed", "Affected/Total"],
            [
                [
                    f"`{_clean(_get(check, 'check_name'))}`",
                    _fmt(_get(check, "quality_dimension")),
                    _fmt(_get(check, "status")),
                    _fmt(_get(check, "observed_value")),
                    f"{_fmt(_get(check, 'affected_count'))}/{_fmt(_get(check, 'total_count'))}",
                ]
                for check in failing_checks
            ],
        )
        lines.append("")

    lines += _degradation_section(baseline_answers, corrupted_answers, corruption_log)

    # --- evidence chain ---
    quality_moved = (
        _quality_status(baseline_quality) is not None
        and _quality_status(corrupted_quality) is not None
        and _quality_status(baseline_quality) != _quality_status(corrupted_quality)
    )
    freshness_moved = (
        _freshness_status(baseline_freshness) is not None
        and _freshness_status(corrupted_freshness) is not None
        and _freshness_status(baseline_freshness) != _freshness_status(corrupted_freshness)
    )
    metric_moved = any(
        isinstance(_get(baseline_metrics, key), (int, float))
        and isinstance(_get(corrupted_metrics, key), (int, float))
        and _get(corrupted_metrics, key) != _get(baseline_metrics, key)
        for _, key, _gated in COMPARISON_METRICS
    )

    lines += ["## 6. Evidence chain", ""]
    if (quality_moved or freshness_moved) and metric_moved:
        lines.append(
            "corruption -> observability signal moved "
            f"(quality changed: {'yes' if quality_moved else 'no'}, freshness changed: "
            f"{'yes' if freshness_moved else 'no'}) -> at least one retrieval/answer metric "
            "moved. The chain holds on this evaluation set."
        )
    elif (quality_moved or freshness_moved) and not metric_moved:
        lines.append(
            "corruption -> observability signal moved, but **no retrieval or answer metric "
            "changed**. The data got worse and the monitoring caught it; there is no evidence "
            "here that RAG quality dropped, and none is claimed."
        )
    elif metric_moved and not (quality_moved or freshness_moved):
        lines.append(
            "At least one metric moved while quality and freshness status stayed the same. "
            "Recorded as an association; the cause is not established by these artifacts."
        )
    else:
        lines.append(
            "Neither the observability signals nor the metrics changed between baseline and "
            "corrupted on this evaluation set. Reported as measured."
        )
    lines.append("")

    lines += [
        "## 7. Limitations",
        "",
        "- Conclusions cover this corpus, this evaluation set and this top_k only.",
        "- A metric moving alongside a corruption is evidence of association; causation is "
        "claimed only where a corruption-log record matches the affected document.",
        "- Judge metrics are compared only where both states produced a real judge verdict; "
        "token overlap is never substituted for a missing judge score.",
        "- `retrieval_hit_rate` blends the exact-lookup and semantic routes; read section 3 "
        "before attributing a change to embedding quality.",
        "",
        *_bullets(
            "Baseline warnings", _get(baseline_metrics, "warnings"), "_No warning was recorded._"
        ),
        *_bullets(
            "Corrupted warnings", _get(corrupted_metrics, "warnings"), "_No warning was recorded._"
        ),
    ]
    if repaired_supplied:
        lines += _bullets(
            "Repaired warnings", _get(repaired_metrics, "warnings"), "_No warning was recorded._"
        )

    write_text(report_path, "\n".join(lines).rstrip() + "\n")
