from __future__ import annotations

import copy

import pytest

from conftest import FAKE_KEY, SECRET_PREFIX, fake_key
from observability.reporting import (
    NOT_AVAILABLE,
    PENDING,
    generate_corruption_report,
    generate_phase1_report,
)


def metrics_payload(state="baseline", **overrides):
    payload = {
        "state": state,
        "started_at": "2026-08-06T00:00:00+00:00",
        "completed_at": "2026-08-06T00:01:00+00:00",
        "evaluation_set_path": "data/eval/test_set.json",
        "evaluation_set_fingerprint": "fp-locked-0001",
        "dataset_path": "data/clean/papers_clean.csv",
        "collection_name": "papers-baseline",
        "index_document_count": 24,
        "provider": "openrouter",
        "model": "nvidia/nemotron-3-ultra-550b-a55b:free",
        "embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
        "top_k": 4,
        "samples": 12,
        "evaluated_questions": 12,
        "failed_questions": 0,
        "hit_count": 11,
        "retrieval_hit_rate": 0.9167,
        "semantic_samples": 3,
        "semantic_hit_count": 2,
        "semantic_retrieval_hit_rate": 0.6667,
        "exact_lookup_samples": 9,
        "exact_lookup_hit_count": 9,
        "exact_lookup_success_rate": 1.0,
        "mean_token_f1": 0.8123,
        "token_f1_definition": "Symmetric F1 over unique tokens.",
        "judge_status": "success",
        "judge_provider": "openrouter",
        "judge_model": "nvidia/nemotron-3-ultra-550b-a55b:free",
        "judge_rubric_version": "role5-judge-v1",
        "judge_success_count": 12,
        "judge_failure_count": 0,
        "judge_accuracy": 0.75,
        "mean_judge_score": 4.25,
        "mean_judge_score_scale": "1-5",
        "judge_init_error": None,
        "errors": [],
        "warnings": [],
        "ragas": {"skipped": "off"},
    }
    payload.update(overrides)
    return payload


def quality_payload(overall="pass", failed=0, rows=24, name="baseline_quality"):
    return {
        "report_name": name,
        "report_path": f"data/quality/{name}.json",
        "evaluated_at": "2026-08-06T00:00:00+00:00",
        "dataset_rows": rows,
        "schema_version": "clean-v1",
        "freshness_threshold_days": 180,
        "checks": [
            {
                "check_name": "paper_id_unique",
                "quality_dimension": "uniqueness",
                "status": "pass" if overall == "pass" else "fail",
                "observed_value": 0 if overall == "pass" else 3,
                "expected_condition": "duplicate_count == 0",
                "affected_count": 0 if overall == "pass" else 3,
                "total_count": rows,
                "message": "duplicates",
            }
        ],
        "summary": {
            "total": 1,
            "passed": 1 if overall == "pass" else 0,
            "failed": failed,
            "warned": 0,
            "overall_status": overall,
        },
    }


def freshness_payload(status="fresh", stale=0, max_age=120.0, oldest="2025-04-01T00:00:00+00:00"):
    return {
        "evaluated_at": "2026-08-06T00:00:00+00:00",
        "report_path": "data/quality/baseline_freshness.json",
        "dataset_path": None,
        "measured_from": ["published", "age_days"],
        "row_count": 24,
        "latest_published": "2025-07-01T00:00:00+00:00",
        "oldest_published": oldest,
        "min_age_days": 30.0,
        "mean_age_days": 75.0,
        "max_age_days": max_age,
        "threshold_days": 180,
        "stale_rows": stale,
        "stale_row_rate": 0.0,
        "invalid_or_missing_date_rows": 0,
        "invalid_or_missing_age_rows": 0,
        "future_dated_rows": 0,
        "status": status,
        "reason": "all rows within threshold",
    }


def answer(sample_id, **overrides):
    payload = {
        "id": sample_id,
        "question_type": "summary",
        "question": f"Summarize the paper titled 'Paper {sample_id}'.",
        "ground_truth": "A abstract sentence.",
        "ground_truth_doc_ids": [f"10.1234/{sample_id}"],
        "top_k": 4,
        "status": "evaluated",
        "error": None,
        "answer": "A abstract sentence.",
        "retrieved_doc_ids": [f"10.1234/{sample_id}"],
        "retrieved_contexts": ["ctx"],
        "retrieved_ranks": {f"10.1234/{sample_id}": 1},
        "hit_rank": 1,
        "retrieval_hit": True,
        "exact_lookup_used": True,
        "evaluation_route": "exact_lookup",
        "token_f1": 1.0,
        "judge": {"score": 5, "correct": True, "reasoning": "ok"},
        "judge_status": "success",
        "judge_error": None,
    }
    payload.update(overrides)
    return payload


def phase1(tmp_path, **overrides):
    path = tmp_path / "reports" / "phase1_report.md"
    generate_phase1_report(
        path,
        overrides.get("source_summary", {"source_api": "Crossref REST API", "records": 24}),
        overrides.get("metrics", metrics_payload()),
        overrides.get("quality", quality_payload()),
        overrides.get("freshness", freshness_payload()),
    )
    return path, path.read_text(encoding="utf-8")


# --- phase 1 report ------------------------------------------------------------------------


def test_phase1_report_is_written(tmp_path):
    path, text = phase1(tmp_path)
    assert path.exists()
    assert text.startswith("# Phase 1 - Baseline Report")


def test_phase1_parent_directory_is_created(tmp_path):
    path = tmp_path / "deep" / "nested" / "phase1_report.md"
    generate_phase1_report(path, {}, metrics_payload(), quality_payload(), freshness_payload())
    assert path.exists()


def test_phase1_reads_real_metrics_from_the_dict(tmp_path):
    _, text = phase1(tmp_path)
    assert "0.9167" in text  # retrieval_hit_rate
    assert "0.6667" in text  # semantic_retrieval_hit_rate
    assert "0.8123" in text  # mean_token_f1
    assert "4.2500" in text  # mean_judge_score
    assert "fp-locked-0001" in text


def test_phase1_does_not_hard_code_provider_or_model(tmp_path):
    _, default_text = phase1(tmp_path)
    assert "openrouter" in default_text
    assert "nvidia/nemotron-3-ultra-550b-a55b:free" in default_text

    _, other_text = phase1(
        tmp_path,
        metrics=metrics_payload(provider="ollama", model="llama3.2"),
    )
    assert "ollama" in other_text
    assert "llama3.2" in other_text
    assert "openrouter" not in other_text
    assert "nemotron" not in other_text


def test_phase1_renders_null_metrics_as_na_not_zero(tmp_path):
    _, text = phase1(
        tmp_path,
        metrics=metrics_payload(
            semantic_retrieval_hit_rate=None,
            judge_accuracy=None,
            mean_judge_score=None,
            judge_success_count=0,
            judge_failure_count=12,
            judge_status="failed",
            warnings=["LLM judge unavailable, judge metrics are null: TimeoutError"],
        ),
    )
    assert NOT_AVAILABLE in text
    assert "0.0000" not in text.split("## 7.")[1].split("## 8.")[0]
    assert "not substituted with token overlap" in text


def test_phase1_reproduces_warnings_and_errors(tmp_path):
    _, text = phase1(
        tmp_path,
        metrics=metrics_payload(
            warnings=["No question was routed through semantic search"],
            errors=[{"id": "s1", "stage": "judge", "error": "429 rate limit"}],
        ),
    )
    assert "No question was routed through semantic search" in text
    assert "429 rate limit" in text


def test_phase1_includes_quality_and_freshness(tmp_path):
    _, text = phase1(
        tmp_path,
        quality=quality_payload(overall="fail", failed=1),
        freshness=freshness_payload(status="stale", stale=7),
    )
    assert "fail" in text
    assert "stale" in text
    assert "paper_id_unique" in text


def test_phase1_handles_missing_keys_without_crashing(tmp_path):
    path = tmp_path / "r.md"
    generate_phase1_report(path, {}, {}, {}, {})
    text = path.read_text(encoding="utf-8")
    assert NOT_AVAILABLE in text


def test_phase1_does_not_mutate_inputs(tmp_path):
    source, metrics = {"a": 1}, metrics_payload()
    quality, freshness = quality_payload(), freshness_payload()
    snapshot = copy.deepcopy((source, metrics, quality, freshness))
    generate_phase1_report(tmp_path / "r.md", source, metrics, quality, freshness)
    assert (source, metrics, quality, freshness) == snapshot


def test_phase1_report_is_utf8_readable(tmp_path):
    path, _ = phase1(tmp_path, source_summary={"query": "truy vấn tiếng Việt — dấu"})
    assert "truy vấn tiếng Việt — dấu" in path.read_text(encoding="utf-8")


def test_phase1_report_contains_no_secret(tmp_path):
    _, text = phase1(
        tmp_path,
        metrics=metrics_payload(
            judge_init_error=f"401 Unauthorized key={FAKE_KEY}",
            warnings=[f"HTTP 401 {{'Authorization': 'Bearer {fake_key('zzzzzzzzzzzzzz')}'}}"],
        ),
    )
    assert FAKE_KEY not in text
    assert SECRET_PREFIX not in text
    assert "***" in text


# --- corruption report, checkpoint 5 shape -----------------------------------------------------


def corruption(tmp_path, **kwargs):
    path = tmp_path / "reports" / "corruption_report.md"
    generate_corruption_report(
        path,
        kwargs.pop("baseline_metrics", metrics_payload()),
        kwargs.pop("corrupted_metrics", metrics_payload(state="corrupted")),
        kwargs.pop("repaired_metrics", None),
        kwargs.pop("corrupted_quality", quality_payload("fail", 1, 20, "corrupted_quality")),
        kwargs.pop("repaired_quality", None),
        kwargs.pop("corrupted_freshness", freshness_payload("stale", 6, 900.0, "2011-01-01T00:00:00+00:00")),
        kwargs.pop("repaired_freshness", None),
        **kwargs,
    )
    return path, path.read_text(encoding="utf-8")


def test_corruption_report_runs_with_repaired_none(tmp_path):
    path, text = corruption(tmp_path)
    assert path.exists()
    assert text.startswith("# Corruption Impact Report")


def test_repaired_shows_pending_at_checkpoint5(tmp_path):
    _, text = corruption(tmp_path)
    assert PENDING in text
    assert "repaired pending" in text


def test_backward_compatible_eight_positional_call(tmp_path):
    """The original signature must still work with no keyword arguments at all."""
    path = tmp_path / "r.md"
    generate_corruption_report(
        path,
        metrics_payload(),
        metrics_payload(state="corrupted"),
        metrics_payload(state="repaired"),
        quality_payload(name="corrupted_quality"),
        quality_payload(name="repaired_quality"),
        freshness_payload(),
        freshness_payload(),
    )
    assert path.exists()


def test_numeric_delta_is_corrupted_minus_baseline(tmp_path):
    _, text = corruption(
        tmp_path,
        baseline_metrics=metrics_payload(retrieval_hit_rate=0.9, mean_token_f1=0.8),
        corrupted_metrics=metrics_payload(
            state="corrupted", retrieval_hit_rate=0.5, mean_token_f1=0.6
        ),
    )
    assert "-0.4000" in text  # retrieval_hit_rate
    assert "-0.2000" in text  # mean_token_f1
    assert "degraded" in text


def test_positive_delta_is_signed(tmp_path):
    _, text = corruption(
        tmp_path,
        baseline_metrics=metrics_payload(retrieval_hit_rate=0.5),
        corrupted_metrics=metrics_payload(state="corrupted", retrieval_hit_rate=0.7),
    )
    assert "+0.2000" in text


def test_null_metric_never_becomes_zero_delta(tmp_path):
    _, text = corruption(
        tmp_path,
        baseline_metrics=metrics_payload(semantic_retrieval_hit_rate=None),
        corrupted_metrics=metrics_payload(state="corrupted", semantic_retrieval_hit_rate=0.5),
    )
    row = next(line for line in text.splitlines() if line.startswith("| semantic_retrieval_hit_rate"))
    assert NOT_AVAILABLE in row
    assert "+0.5000" not in row
    assert "-0.5000" not in row


def test_judge_metrics_are_not_compared_without_a_real_verdict(tmp_path):
    _, text = corruption(
        tmp_path,
        corrupted_metrics=metrics_payload(
            state="corrupted",
            judge_status="failed",
            judge_success_count=0,
            judge_failure_count=12,
            judge_accuracy=None,
            mean_judge_score=None,
        ),
    )
    row = next(line for line in text.splitlines() if line.startswith("| judge_accuracy"))
    assert "no successful judge call" in row
    assert NOT_AVAILABLE in row


def test_judge_failure_never_yields_a_substitute_score(tmp_path):
    _, text = corruption(
        tmp_path,
        baseline_metrics=metrics_payload(
            judge_status="failed",
            judge_success_count=0,
            judge_accuracy=None,
            mean_judge_score=None,
        ),
        corrupted_metrics=metrics_payload(
            state="corrupted",
            judge_status="failed",
            judge_success_count=0,
            judge_accuracy=None,
            mean_judge_score=None,
        ),
    )
    assert "token overlap is never substituted" in text
    judge_rows = [line for line in text.splitlines() if line.startswith(("| judge_accuracy", "| mean_judge_score"))]
    assert judge_rows
    for row in judge_rows:
        assert NOT_AVAILABLE in row


def test_quality_and_freshness_status_transitions_are_shown(tmp_path):
    _, text = corruption(
        tmp_path,
        baseline_quality=quality_payload("pass"),
        baseline_freshness=freshness_payload("fresh"),
    )
    quality_row = next(line for line in text.splitlines() if line.startswith("| quality status"))
    freshness_row = next(line for line in text.splitlines() if line.startswith("| freshness status"))
    assert "pass -> fail" in quality_row
    assert "fresh -> stale" in freshness_row


def test_missing_baseline_quality_is_flagged_not_faked(tmp_path):
    _, text = corruption(tmp_path)
    quality_row = next(line for line in text.splitlines() if line.startswith("| quality status"))
    assert NOT_AVAILABLE in quality_row
    assert "Pass `baseline_quality=`" in text


def test_mismatched_fingerprints_raise_a_warning(tmp_path):
    _, text = corruption(
        tmp_path,
        corrupted_metrics=metrics_payload(state="corrupted", evaluation_set_fingerprint="fp-other"),
    )
    assert "fingerprints do not all match" in text


def test_matching_fingerprints_are_confirmed(tmp_path):
    _, text = corruption(tmp_path)
    assert "same locked evaluation set" in text


def test_semantic_denominator_shift_is_warned(tmp_path):
    _, text = corruption(
        tmp_path,
        baseline_metrics=metrics_payload(semantic_samples=3, semantic_retrieval_hit_rate=0.66),
        corrupted_metrics=metrics_payload(
            state="corrupted", semantic_samples=7, semantic_retrieval_hit_rate=0.30
        ),
    )
    row = next(line for line in text.splitlines() if line.startswith("| semantic_retrieval_hit_rate"))
    assert "different denominators" in row
    assert "n=3" in row and "n=7" in row


# --- degradation evidence -------------------------------------------------------------------------


def test_degradation_case_is_found_and_detailed(tmp_path):
    baseline_answers = [answer("s1"), answer("s2"), answer("s3")]
    corrupted_answers = [
        answer("s1"),
        answer(
            "s2",
            retrieved_doc_ids=["10.9999/other"],
            retrieved_ranks={"10.1234/s2": None},
            hit_rank=None,
            retrieval_hit=False,
            exact_lookup_used=False,
            evaluation_route="semantic_search",
            token_f1=0.1,
            answer="Something unrelated.",
        ),
        answer("s3"),
    ]
    _, text = corruption(
        tmp_path,
        baseline_answers=baseline_answers,
        corrupted_answers=corrupted_answers,
        corruption_log={"scenarios": [{"paper_id": "10.1234/s2", "corruption_type": "truncate_title"}]},
    )
    assert "1 question(s) got worse" in text
    assert "s2" in text
    assert "retrieval hit lost" in text
    assert "exact lookup no longer resolves" in text
    assert "10.9999/other" in text
    assert "truncate_title" in text


def test_answers_are_matched_by_sample_id_not_position(tmp_path):
    baseline_answers = [answer("s1"), answer("s2")]
    corrupted_answers = [
        answer("s2", retrieval_hit=False, hit_rank=None, token_f1=0.0),
        answer("s1"),
    ]
    _, text = corruption(
        tmp_path, baseline_answers=baseline_answers, corrupted_answers=corrupted_answers
    )
    assert "1 question(s) got worse" in text
    degraded_rows = [line for line in text.splitlines() if "`s2`" in line]
    assert degraded_rows
    assert not [line for line in text.splitlines() if "`s1`" in line]


def test_no_degradation_is_reported_honestly(tmp_path):
    answers = [answer("s1"), answer("s2")]
    _, text = corruption(
        tmp_path, baseline_answers=answers, corrupted_answers=copy.deepcopy(answers)
    )
    assert "No degraded case was found" in text
    assert "no example is invented" in text


def test_unmatched_corruption_log_is_called_an_association(tmp_path):
    baseline_answers = [answer("s1")]
    corrupted_answers = [answer("s1", retrieval_hit=False, hit_rank=None, token_f1=0.0)]
    _, text = corruption(
        tmp_path,
        baseline_answers=baseline_answers,
        corrupted_answers=corrupted_answers,
        corruption_log={"scenarios": [{"paper_id": "10.5555/untouched", "type": "blank_summary"}]},
    )
    assert "association" in text
    assert "not a demonstrated cause" in text


def test_absent_corruption_log_is_called_an_observation(tmp_path):
    baseline_answers = [answer("s1")]
    corrupted_answers = [answer("s1", retrieval_hit=False, hit_rank=None, token_f1=0.0)]
    _, text = corruption(
        tmp_path, baseline_answers=baseline_answers, corrupted_answers=corrupted_answers
    )
    assert "observation" in text


def test_semantic_topic_breakdown_uses_the_fixed_question_set(tmp_path):
    baseline_answers = [
        answer("t1", question_type="semantic_topic", evaluation_route="semantic_search", exact_lookup_used=False),
        answer("t2", question_type="semantic_topic", evaluation_route="semantic_search", exact_lookup_used=False),
        answer("e1"),
    ]
    corrupted_answers = [
        answer(
            "t1",
            question_type="semantic_topic",
            evaluation_route="semantic_search",
            exact_lookup_used=False,
            retrieval_hit=False,
            hit_rank=None,
        ),
        answer("t2", question_type="semantic_topic", evaluation_route="semantic_search", exact_lookup_used=False),
        answer("e1", evaluation_route="semantic_search", exact_lookup_used=False),
    ]
    _, text = corruption(
        tmp_path, baseline_answers=baseline_answers, corrupted_answers=corrupted_answers
    )
    row = next(line for line in text.splitlines() if "semantic_topic hit rate" in line)
    assert "1.0000" in row  # baseline 2/2
    assert "0.5000" in row  # corrupted 1/2
    assert "resolved through the exact lookup at baseline no longer do so" in text


def test_route_counts_are_reported_separately(tmp_path):
    baseline_answers = [answer("e1"), answer("e2")]
    corrupted_answers = [
        answer("e1"),
        answer("e2", evaluation_route="semantic_search", exact_lookup_used=False),
    ]
    _, text = corruption(
        tmp_path, baseline_answers=baseline_answers, corrupted_answers=corrupted_answers
    )
    exact_row = next(line for line in text.splitlines() if line.startswith("| route = exact_lookup"))
    assert "| 2 | 1 |" in exact_row


# --- evidence chain -----------------------------------------------------------------------------


def test_quality_moved_but_metrics_unchanged_does_not_claim_rag_dropped(tmp_path):
    same = metrics_payload()
    _, text = corruption(
        tmp_path,
        baseline_metrics=same,
        corrupted_metrics=metrics_payload(state="corrupted"),
        baseline_quality=quality_payload("pass"),
        baseline_freshness=freshness_payload("fresh"),
    )
    assert "no evidence here that RAG quality dropped" in text


def test_full_chain_is_stated_when_both_moved(tmp_path):
    _, text = corruption(
        tmp_path,
        baseline_metrics=metrics_payload(retrieval_hit_rate=0.9),
        corrupted_metrics=metrics_payload(state="corrupted", retrieval_hit_rate=0.4),
        baseline_quality=quality_payload("pass"),
        baseline_freshness=freshness_payload("fresh"),
    )
    assert "The chain holds on this evaluation set." in text


# --- checkpoint 6 shape ---------------------------------------------------------------------------


def test_full_three_state_report(tmp_path):
    path = tmp_path / "r.md"
    generate_corruption_report(
        path,
        metrics_payload(retrieval_hit_rate=0.90),
        metrics_payload(state="corrupted", retrieval_hit_rate=0.40),
        metrics_payload(state="repaired", retrieval_hit_rate=0.88),
        quality_payload("fail", 1, 20, "corrupted_quality"),
        quality_payload("pass", 0, 24, "repaired_quality"),
        freshness_payload("stale", 6),
        freshness_payload("fresh", 0),
        baseline_quality=quality_payload("pass"),
        baseline_freshness=freshness_payload("fresh"),
    )
    text = path.read_text(encoding="utf-8")
    assert PENDING not in text
    assert "-0.5000" in text  # corruption delta
    assert "+0.4800" in text  # recovery delta
    assert "repaired" in text


# --- hygiene ------------------------------------------------------------------------------------


def test_corruption_report_contains_no_secret(tmp_path):
    _, text = corruption(
        tmp_path,
        baseline_metrics=metrics_payload(
            warnings=[f"judge failed: 401 key={FAKE_KEY}"],
        ),
        corrupted_metrics=metrics_payload(
            state="corrupted",
            warnings=[f"HTTP 401 {{'Authorization': 'Bearer {fake_key('qqqqqqqqqqqq')}'}}"],
        ),
    )
    assert FAKE_KEY not in text
    assert SECRET_PREFIX not in text
    assert "***" in text


def test_authorization_header_is_sanitized(tmp_path):
    _, text = corruption(
        tmp_path,
        corrupted_metrics=metrics_payload(
            state="corrupted",
            errors=[{"id": "s1", "stage": "judge", "error": "Authorization: Bearer topsecretvalue123"}],
        ),
    )
    assert "topsecretvalue123" not in text


def test_corruption_report_does_not_mutate_inputs(tmp_path):
    payloads = {
        "baseline_metrics": metrics_payload(),
        "corrupted_metrics": metrics_payload(state="corrupted"),
        "corrupted_quality": quality_payload(name="corrupted_quality"),
        "corrupted_freshness": freshness_payload(),
        "baseline_answers": [answer("s1")],
        "corrupted_answers": [answer("s1", retrieval_hit=False)],
        "corruption_log": {"scenarios": [{"paper_id": "10.1234/s1"}]},
    }
    snapshot = copy.deepcopy(payloads)
    generate_corruption_report(
        tmp_path / "r.md",
        payloads["baseline_metrics"],
        payloads["corrupted_metrics"],
        None,
        payloads["corrupted_quality"],
        None,
        payloads["corrupted_freshness"],
        None,
        baseline_answers=payloads["baseline_answers"],
        corrupted_answers=payloads["corrupted_answers"],
        corruption_log=payloads["corruption_log"],
    )
    assert payloads == snapshot


def test_corruption_report_parent_directory_is_created(tmp_path):
    path = tmp_path / "a" / "b" / "c.md"
    generate_corruption_report(
        path, metrics_payload(), metrics_payload(), None, quality_payload(), None, freshness_payload(), None
    )
    assert path.exists()


def test_corruption_report_is_utf8_readable(tmp_path):
    _, text = corruption(
        tmp_path,
        corrupted_metrics=metrics_payload(state="corrupted", warnings=["dữ liệu bị hỏng — cảnh báo"]),
    )
    assert "dữ liệu bị hỏng — cảnh báo" in text


def test_pipe_characters_do_not_break_the_table(tmp_path):
    _, text = corruption(
        tmp_path,
        corrupted_metrics=metrics_payload(state="corrupted", collection_name="papers|corrupted"),
    )
    assert r"papers\|corrupted" in text


def test_report_handles_empty_dicts_without_crashing(tmp_path):
    path = tmp_path / "r.md"
    generate_corruption_report(path, {}, {}, None, {}, None, {}, None)
    assert NOT_AVAILABLE in path.read_text(encoding="utf-8")
