from __future__ import annotations

from pathlib import Path
import json

import pytest

from conftest import (
    FAKE_KEY,
    SECRET_PREFIX,
    FakeAnswerResult,
    FakeIndex,
    FakeLLM,
    always_raises,
    always_replies,
    fake_key,
)
from core.config import load_settings
from evaluation.metrics import (
    JUDGE_SCORE_SCALE,
    ROUTE_EXACT_LOOKUP,
    ROUTE_SEMANTIC_SEARCH,
    EvaluationError,
    JudgeParseError,
    _parse_judge_response,
    _probe_exact_lookup,
    _sanitize_error,
    _token_f1,
    evaluate_pipeline,
)
from core.utils import write_json

GOOD_VERDICT ='{"score": 5, "correct": true, "reasoning": "Matches the reference."}'


@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("LLM_MODEL", "nvidia/nemotron-3-ultra-550b-a55b:free")
    monkeypatch.setenv("OPENROUTER_API_KEY", FAKE_KEY)
    monkeypatch.delenv("RUN_RAGAS", raising=False)
    return load_settings(project_dir=tmp_path)


def sample(sample_id, question, ground_truth, doc_ids, question_type="summary"):
    return {
        "id": sample_id,
        "question_type": question_type,
        "question": question,
        "ground_truth": ground_truth,
        "ground_truth_doc_ids": list(doc_ids),
    }


def write_test_set(tmp_path: Path, samples) -> Path:
    path = tmp_path / "eval" / "test_set.json"
    write_json(path, samples)
    return path


def run(tmp_path, settings, samples, answers_by_question, *, index=None, **kwargs):
    """Drive evaluate_pipeline with a scripted answer function and a fake index."""
    test_set_path = write_test_set(tmp_path, samples)
    metrics_path = tmp_path / "results" / "metrics.json"
    answers_path = tmp_path / "results" / "answers.json"

    def answer_fn(question, settings, index, top_k=None):
        payload = answers_by_question[question]
        if isinstance(payload, BaseException):
            raise payload
        answer, doc_ids = payload
        return FakeAnswerResult(question, answer, doc_ids)

    kwargs.setdefault("answer_fn", answer_fn)
    kwargs.setdefault("run_judge", False)
    bundle = evaluate_pipeline(
        settings,
        index if index is not None else FakeIndex(),
        test_set_path,
        metrics_path,
        answers_path,
        **kwargs,
    )
    return bundle, metrics_path, answers_path


# --- token F1 (formula must stay unchanged) -----------------------------------------------


def test_token_f1_exact_match_is_one():
    assert _token_f1("neural retrieval models", "neural retrieval models") == 1.0


def test_token_f1_partial_match_is_between_zero_and_one():
    score = _token_f1("neural retrieval models", "neural retrieval")
    assert 0.0 < score < 1.0


def test_token_f1_disjoint_is_zero():
    assert _token_f1("neural retrieval", "quantum chemistry") == 0.0


def test_token_f1_empty_prediction_is_zero():
    assert _token_f1("neural retrieval", "") == 0.0
    assert _token_f1("neural retrieval", "   ") == 0.0


def test_token_f1_empty_reference_is_zero():
    assert _token_f1("", "neural retrieval") == 0.0


def test_token_f1_ignores_case_and_whitespace_only():
    assert _token_f1("Neural   Retrieval", "neural retrieval") == 1.0


def test_token_f1_does_not_strip_punctuation():
    """Documented behaviour of the starter formula, pinned so it is not changed by accident."""
    assert _token_f1("retrieval", "retrieval.") == 0.0


# --- exact lookup probe --------------------------------------------------------------------


def test_probe_detects_a_resolvable_quoted_title():
    index = FakeIndex(lookup_hits={"a real title": "10.1234/paper.001"})
    used, paper_id = _probe_exact_lookup(index, "Who authored the paper titled 'A Real Title'?")
    assert used is True
    assert paper_id == "10.1234/paper.001"


def test_probe_reports_semantic_when_the_quoted_title_does_not_resolve():
    index = FakeIndex(lookup_hits={})
    used, paper_id = _probe_exact_lookup(index, "Who authored the paper titled 'Truncated Ti'?")
    assert used is False
    assert paper_id is None


def test_probe_reports_semantic_when_there_is_no_quoted_span():
    index = FakeIndex(lookup_hits={"anything": "10.1234/paper.001"})
    used, _ = _probe_exact_lookup(index, "Which paper discusses graph based retrieval?")
    assert used is False


def test_probe_survives_a_raising_index():
    class Boom(FakeIndex):
        def lookup(self, value):
            raise RuntimeError("chroma exploded")

    used, _ = _probe_exact_lookup(Boom(), "Summarize the paper titled 'X Y Z'.")
    assert used is False


def test_probe_agrees_with_the_real_qa_module(settings):
    """Cross-check the mirror against retrieval.qa itself.

    Skipped until the heavy retrieval dependencies are installed, then it proves the probe
    labels a question exactly the way qa.answer_question actually resolved it.
    """
    qa = pytest.importorskip("retrieval.qa", reason="needs langchain/sentence-transformers")

    class QaIndex(FakeIndex):
        """lookup() as in FakeIndex, plus the search() that qa.answer_question calls."""

        def __init__(self, lookup_hits):
            super().__init__(lookup_hits=lookup_hits)
            self.documents_by_paper_id = {}

        def lookup(self, value):
            paper_id = self.lookup_hits.get(value.strip().lower())
            if paper_id is None:
                return None
            return {
                "paper_id": paper_id,
                "title": value,
                "content": "exact content",
                "metadata": {
                    "paper_id": paper_id,
                    "title": value,
                    "summary": "Exact summary sentence. Second sentence.",
                    "authors_joined": "Ada Lovelace",
                    "published": "2025-01-01",
                    "categories_joined": "Computer Science",
                },
            }

        def search(self, query, top_k=None):
            from retrieval.index import SearchResult

            return [
                SearchResult(
                    paper_id="p-other",
                    title="Other",
                    score=0.5,
                    content="other content",
                    metadata={
                        "paper_id": "p-other",
                        "title": "Other",
                        "summary": "Other summary sentence.",
                        "authors_joined": "Someone Else",
                        "published": "2024-01-01",
                        "categories_joined": "Other",
                    },
                )
            ]

    resolving = "Who authored the paper titled 'A Real Title'?"
    missing = "Who authored the paper titled 'A Truncated Ti'?"
    index = QaIndex({"a real title": "p-target"})

    result = qa.answer_question(resolving, settings=settings, index=index)
    used, paper_id = _probe_exact_lookup(index, resolving)
    assert used is True
    assert paper_id == "p-target"
    assert result.retrieved_doc_ids[0] == "p-target", "qa pins the exact hit at rank 0"

    result = qa.answer_question(missing, settings=settings, index=index)
    used, _ = _probe_exact_lookup(index, missing)
    assert used is False
    assert result.retrieved_doc_ids[0] != "p-target"


# --- retrieval routes and aggregates ----------------------------------------------------------


def test_exact_route_hit_is_recorded_and_aggregated(tmp_path, settings):
    samples = [sample("s1", "Summarize the paper titled 'Alpha'.", "Alpha abstract.", ["p1"])]
    index = FakeIndex(lookup_hits={"alpha": "p1"})
    bundle, _, _ = run(
        tmp_path, settings, samples, {samples[0]["question"]: ("Alpha abstract.", ["p1", "p2"])}, index=index
    )
    answer = bundle.answers[0]
    assert answer["exact_lookup_used"] is True
    assert answer["evaluation_route"] == ROUTE_EXACT_LOOKUP
    assert answer["retrieval_hit"] is True
    assert answer["retrieved_ranks"] == {"p1": 1}
    assert answer["hit_rank"] == 1
    assert answer["top_k"] == settings.top_k
    assert bundle.summary["exact_lookup_samples"] == 1
    assert bundle.summary["exact_lookup_hit_count"] == 1
    assert bundle.summary["exact_lookup_success_rate"] == 1.0
    assert bundle.summary["semantic_samples"] == 0
    assert bundle.summary["semantic_retrieval_hit_rate"] is None


def test_semantic_route_hit_is_recorded(tmp_path, settings):
    samples = [sample("s1", "Which paper discusses graph retrieval?", "Graph abstract.", ["p1"], "semantic_topic")]
    bundle, _, _ = run(
        tmp_path, settings, samples, {samples[0]["question"]: ("Graph abstract.", ["p3", "p1"])}
    )
    answer = bundle.answers[0]
    assert answer["exact_lookup_used"] is False
    assert answer["evaluation_route"] == ROUTE_SEMANTIC_SEARCH
    assert answer["retrieval_hit"] is True
    assert answer["retrieved_ranks"] == {"p1": 2}
    assert answer["hit_rank"] == 2
    assert bundle.summary["semantic_retrieval_hit_rate"] == 1.0
    assert bundle.summary["exact_lookup_samples"] == 0
    assert bundle.summary["exact_lookup_success_rate"] is None


def test_semantic_miss_is_recorded(tmp_path, settings):
    samples = [sample("s1", "Which paper discusses graph retrieval?", "Graph abstract.", ["p1"], "semantic_topic")]
    bundle, _, _ = run(
        tmp_path, settings, samples, {samples[0]["question"]: ("Wrong abstract.", ["p7", "p8"])}
    )
    answer = bundle.answers[0]
    assert answer["retrieval_hit"] is False
    assert answer["retrieved_ranks"] == {"p1": None}
    assert answer["hit_rank"] is None
    assert bundle.summary["semantic_retrieval_hit_rate"] == 0.0
    assert bundle.summary["semantic_hit_count"] == 0


def test_mixed_routes_are_aggregated_separately(tmp_path, settings):
    samples = [
        sample("e1", "Summarize the paper titled 'Alpha'.", "Alpha abstract.", ["p1"]),
        sample("e2", "Summarize the paper titled 'Beta'.", "Beta abstract.", ["p2"]),
        sample("s1", "Which paper discusses graph retrieval?", "Graph abstract.", ["p3"], "semantic_topic"),
        sample("s2", "Which paper discusses token pruning?", "Pruning abstract.", ["p4"], "semantic_topic"),
    ]
    index = FakeIndex(lookup_hits={"alpha": "p1", "beta": "p2"})
    answers = {
        samples[0]["question"]: ("Alpha abstract.", ["p1"]),
        samples[1]["question"]: ("Beta abstract.", ["p2"]),
        samples[2]["question"]: ("Graph abstract.", ["p3"]),
        samples[3]["question"]: ("Nope.", ["p9"]),
    }
    bundle, _, _ = run(tmp_path, settings, samples, answers, index=index)
    summary = bundle.summary
    assert summary["exact_lookup_samples"] == 2
    assert summary["exact_lookup_success_rate"] == 1.0
    assert summary["semantic_samples"] == 2
    assert summary["semantic_hit_count"] == 1
    assert summary["semantic_retrieval_hit_rate"] == 0.5
    assert summary["hit_count"] == 3
    assert summary["retrieval_hit_rate"] == 0.75


def test_no_semantic_sample_warns_instead_of_reporting_zero(tmp_path, settings):
    samples = [sample("e1", "Summarize the paper titled 'Alpha'.", "Alpha abstract.", ["p1"])]
    index = FakeIndex(lookup_hits={"alpha": "p1"})
    bundle, _, _ = run(
        tmp_path, settings, samples, {samples[0]["question"]: ("Alpha abstract.", ["p1"])}, index=index
    )
    assert bundle.summary["semantic_retrieval_hit_rate"] is None
    assert any("semantic_retrieval_hit_rate is" in w for w in bundle.summary["warnings"])


def test_exact_lookup_success_rate_is_not_labelled_as_semantic(tmp_path, settings):
    samples = [sample("e1", "Summarize the paper titled 'Alpha'.", "Alpha abstract.", ["p1"])]
    index = FakeIndex(lookup_hits={"alpha": "p1"})
    bundle, metrics_path, _ = run(
        tmp_path, settings, samples, {samples[0]["question"]: ("Alpha abstract.", ["p1"])}, index=index
    )
    payload = json.loads(metrics_path.read_text(encoding="utf-8"))
    assert payload["exact_lookup_success_rate"] == 1.0
    assert payload["semantic_retrieval_hit_rate"] is None
    assert payload["retrieval_hit_rate"] == 1.0


# --- refusals and per-question resilience -------------------------------------------------------


def test_empty_test_set_is_refused(tmp_path, settings):
    from evaluation.testset import TestSetValidationError

    with pytest.raises(TestSetValidationError, match="empty"):
        run(tmp_path, settings, [], {})


def test_empty_index_is_refused(tmp_path, settings):
    samples = [sample("s1", "Which paper discusses graph retrieval?", "Graph.", ["p1"], "semantic_topic")]
    with pytest.raises(EvaluationError, match="index is empty"):
        run(tmp_path, settings, samples, {}, index=FakeIndex(documents=[]))


def test_no_artifact_is_written_when_the_run_is_refused(tmp_path, settings):
    samples = [sample("s1", "Which paper discusses graph retrieval?", "Graph.", ["p1"], "semantic_topic")]
    with pytest.raises(EvaluationError):
        run(tmp_path, settings, samples, {}, index=FakeIndex(documents=[]))
    assert not (tmp_path / "results" / "metrics.json").exists()


def test_unknown_index_size_warns_but_proceeds(tmp_path, settings):
    class SizelessIndex:
        collection_name = "papers-test"

        def lookup(self, value):
            return None

    samples = [sample("s1", "Which paper discusses graph retrieval?", "Graph.", ["p1"], "semantic_topic")]
    bundle, _, _ = run(
        tmp_path,
        settings,
        samples,
        {samples[0]["question"]: ("Graph.", ["p1"])},
        index=SizelessIndex(),
    )
    assert bundle.summary["index_document_count"] is None
    assert any("empty-index guard" in w for w in bundle.summary["warnings"])


def test_one_failing_question_does_not_lose_the_others(tmp_path, settings):
    samples = [
        sample("s1", "Which paper discusses graph retrieval?", "Graph.", ["p1"], "semantic_topic"),
        sample("s2", "Which paper discusses token pruning?", "Pruning.", ["p2"], "semantic_topic"),
        sample("s3", "Which paper discusses sparse attention?", "Sparse.", ["p3"], "semantic_topic"),
    ]
    answers = {
        samples[0]["question"]: ("Graph.", ["p1"]),
        samples[1]["question"]: RuntimeError("chroma query timed out"),
        samples[2]["question"]: ("Sparse.", ["p3"]),
    }
    bundle, _, answers_path = run(tmp_path, settings, samples, answers)
    summary = bundle.summary
    assert summary["samples"] == 3
    assert summary["evaluated_questions"] == 2
    assert summary["failed_questions"] == 1
    assert summary["retrieval_hit_rate"] == 1.0  # denominator excludes the failure
    assert summary["hit_count"] == 2
    assert [error["stage"] for error in summary["errors"]] == ["answer"]
    assert "chroma query timed out" in summary["errors"][0]["error"]

    persisted = json.loads(answers_path.read_text(encoding="utf-8"))
    failed = next(item for item in persisted if item["id"] == "s2")
    assert failed["status"] == "failed"
    assert failed["retrieval_hit"] is None  # not silently counted as a miss
    assert failed["token_f1"] is None


def test_all_questions_failing_gives_null_rates_not_zero(tmp_path, settings):
    samples = [sample("s1", "Which paper discusses graph retrieval?", "Graph.", ["p1"], "semantic_topic")]
    bundle, _, _ = run(
        tmp_path, settings, samples, {samples[0]["question"]: RuntimeError("boom")}
    )
    assert bundle.summary["retrieval_hit_rate"] is None
    assert bundle.summary["mean_token_f1"] is None
    assert bundle.summary["failed_questions"] == 1


# --- judge -----------------------------------------------------------------------------------


def test_judge_success_populates_metrics(tmp_path, settings):
    samples = [sample("s1", "Which paper discusses graph retrieval?", "Graph.", ["p1"], "semantic_topic")]
    llm = FakeLLM(always_replies(GOOD_VERDICT))
    bundle, _, _ = run(
        tmp_path,
        settings,
        samples,
        {samples[0]["question"]: ("Graph.", ["p1"])},
        run_judge=True,
        judge_llm=llm,
    )
    summary = bundle.summary
    assert summary["judge_status"] == "success"
    assert summary["judge_success_count"] == 1
    assert summary["judge_failure_count"] == 0
    assert summary["judge_accuracy"] == 1.0
    assert summary["mean_judge_score"] == 5.0
    assert summary["mean_judge_score_scale"] == JUDGE_SCORE_SCALE
    assert bundle.answers[0]["judge"] == {"score": 5, "correct": True, "reasoning": "Matches the reference."}


def test_judge_accepts_a_fenced_json_reply(tmp_path, settings):
    samples = [sample("s1", "Which paper discusses graph retrieval?", "Graph.", ["p1"], "semantic_topic")]
    fenced = f"```json\n{GOOD_VERDICT}\n```"
    bundle, _, _ = run(
        tmp_path,
        settings,
        samples,
        {samples[0]["question"]: ("Graph.", ["p1"])},
        run_judge=True,
        judge_llm=FakeLLM(always_replies(fenced)),
    )
    assert bundle.summary["judge_success_count"] == 1


def test_judge_malformed_output_fails_without_inventing_a_score(tmp_path, settings):
    samples = [sample("s1", "Which paper discusses graph retrieval?", "Graph.", ["p1"], "semantic_topic")]
    bundle, _, _ = run(
        tmp_path,
        settings,
        samples,
        {samples[0]["question"]: ("Graph.", ["p1"])},
        run_judge=True,
        judge_llm=FakeLLM(always_replies("Sure! The answer looks about right to me.")),
    )
    summary = bundle.summary
    assert summary["judge_status"] == "failed"
    assert summary["judge_success_count"] == 0
    assert summary["judge_accuracy"] is None
    assert summary["mean_judge_score"] is None
    assert bundle.answers[0]["judge"] is None
    assert "no JSON object" in bundle.answers[0]["judge_error"]


def test_judge_out_of_range_score_is_rejected(tmp_path, settings):
    samples = [sample("s1", "Which paper discusses graph retrieval?", "Graph.", ["p1"], "semantic_topic")]
    bundle, _, _ = run(
        tmp_path,
        settings,
        samples,
        {samples[0]["question"]: ("Graph.", ["p1"])},
        run_judge=True,
        judge_llm=FakeLLM(always_replies('{"score": 11, "correct": true, "reasoning": "great"}')),
    )
    assert bundle.summary["judge_success_count"] == 0
    assert bundle.summary["mean_judge_score"] is None


def test_judge_provider_error_keeps_retrieval_and_token_f1(tmp_path, settings):
    samples = [sample("s1", "Which paper discusses graph retrieval?", "Graph.", ["p1"], "semantic_topic")]
    bundle, _, _ = run(
        tmp_path,
        settings,
        samples,
        {samples[0]["question"]: ("Graph.", ["p1"])},
        run_judge=True,
        judge_llm=FakeLLM(always_raises(lambda: TimeoutError("read timeout after 60s"))),
    )
    summary = bundle.summary
    assert summary["judge_status"] == "failed"
    assert summary["judge_accuracy"] is None
    assert summary["mean_judge_score"] is None
    assert summary["retrieval_hit_rate"] == 1.0
    assert summary["mean_token_f1"] == 1.0
    assert "read timeout" in summary["errors"][0]["error"]


def test_judge_failure_never_produces_a_default_score(tmp_path, settings):
    """A perfect token overlap must not be laundered into a judge score."""
    samples = [sample("s1", "Which paper discusses graph retrieval?", "Graph.", ["p1"], "semantic_topic")]
    bundle, _, answers_path = run(
        tmp_path,
        settings,
        samples,
        {samples[0]["question"]: ("Graph.", ["p1"])},
        run_judge=True,
        judge_llm=FakeLLM(always_raises(lambda: RuntimeError("429 rate limit"))),
    )
    assert bundle.summary["mean_token_f1"] == 1.0
    persisted = json.loads(answers_path.read_text(encoding="utf-8"))
    assert persisted[0]["judge"] is None
    assert persisted[0]["judge_status"] == "failed"
    blob = json.dumps(bundle.summary)
    assert "heuristic" not in blob.lower()


def test_judge_retries_then_succeeds(tmp_path, settings):
    samples = [sample("s1", "Which paper discusses graph retrieval?", "Graph.", ["p1"], "semantic_topic")]
    llm = FakeLLM([RuntimeError("transient 503"), GOOD_VERDICT])
    bundle, _, _ = run(
        tmp_path,
        settings,
        samples,
        {samples[0]["question"]: ("Graph.", ["p1"])},
        run_judge=True,
        judge_llm=llm,
    )
    assert bundle.summary["judge_success_count"] == 1
    assert len(llm.prompts) == 2


def test_partial_judge_failure_is_labelled_partial(tmp_path, settings):
    samples = [
        sample("s1", "Which paper discusses graph retrieval?", "Graph.", ["p1"], "semantic_topic"),
        sample("s2", "Which paper discusses token pruning?", "Pruning.", ["p2"], "semantic_topic"),
    ]
    # first question succeeds on attempt 1; second fails both attempts
    llm = FakeLLM([GOOD_VERDICT, RuntimeError("boom"), RuntimeError("boom")])
    bundle, _, _ = run(
        tmp_path,
        settings,
        samples,
        {
            samples[0]["question"]: ("Graph.", ["p1"]),
            samples[1]["question"]: ("Pruning.", ["p2"]),
        },
        run_judge=True,
        judge_llm=llm,
    )
    summary = bundle.summary
    assert summary["judge_status"] == "partial"
    assert summary["judge_success_count"] == 1
    assert summary["judge_failure_count"] == 1
    assert summary["judge_accuracy"] == 1.0  # denominator is the successful call only


def test_missing_credentials_make_the_judge_unavailable(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("LLM_MODEL", "nvidia/nemotron-3-ultra-550b-a55b:free")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("RUN_RAGAS", raising=False)
    local_settings = load_settings(project_dir=tmp_path)

    samples = [sample("s1", "Which paper discusses graph retrieval?", "Graph.", ["p1"], "semantic_topic")]
    bundle, _, _ = run(
        tmp_path,
        local_settings,
        samples,
        {samples[0]["question"]: ("Graph.", ["p1"])},
        run_judge=True,
    )
    summary = bundle.summary
    assert summary["judge_status"] == "unavailable"
    assert summary["judge_accuracy"] is None
    assert summary["mean_judge_score"] is None
    assert summary["retrieval_hit_rate"] == 1.0
    assert "OPENROUTER_API_KEY" in summary["judge_init_error"]


def test_disabled_judge_is_labelled_skipped(tmp_path, settings):
    samples = [sample("s1", "Which paper discusses graph retrieval?", "Graph.", ["p1"], "semantic_topic")]
    bundle, _, _ = run(tmp_path, settings, samples, {samples[0]["question"]: ("Graph.", ["p1"])})
    assert bundle.summary["judge_status"] == "skipped"
    assert bundle.summary["judge_accuracy"] is None


# --- judge parser unit cases ---------------------------------------------------------------------


def test_parser_accepts_prose_wrapped_json():
    verdict = _parse_judge_response('Here is my grade:\n{"score": 4, "correct": true, "reasoning": "ok"}')
    assert verdict.score == 4


def test_parser_rejects_empty_reply():
    with pytest.raises(JudgeParseError, match="empty"):
        _parse_judge_response("   ")


def test_parser_rejects_broken_json():
    with pytest.raises(JudgeParseError, match="not valid JSON"):
        _parse_judge_response('{"score": 4, "correct": true,}')


def test_parser_rejects_missing_fields():
    with pytest.raises(JudgeParseError, match="verdict schema"):
        _parse_judge_response('{"score": 4}')


# --- secret hygiene ---------------------------------------------------------------------------------


def test_sanitizer_removes_the_configured_key(settings):
    text = _sanitize_error(RuntimeError(f"401 from https://openrouter.ai key={FAKE_KEY}"), settings)
    assert FAKE_KEY not in text
    assert "***" in text


def test_sanitizer_removes_authorization_headers(settings):
    leaked = fake_key("zzzzzzzzzzzz")
    text = _sanitize_error(f"HTTP 401 {{'Authorization': 'Bearer {leaked}'}}", settings)
    assert leaked not in text


def test_artifacts_never_contain_the_api_key(tmp_path, settings):
    samples = [sample("s1", "Which paper discusses graph retrieval?", "Graph.", ["p1"], "semantic_topic")]
    bundle, metrics_path, answers_path = run(
        tmp_path,
        settings,
        samples,
        {samples[0]["question"]: ("Graph.", ["p1"])},
        run_judge=True,
        judge_llm=FakeLLM(always_raises(lambda: RuntimeError(f"401 Unauthorized, key={FAKE_KEY}"))),
    )
    for path in (metrics_path, answers_path):
        blob = path.read_text(encoding="utf-8")
        assert FAKE_KEY not in blob
        assert SECRET_PREFIX not in blob
    assert "***" in bundle.answers[0]["judge_error"]


def test_metrics_record_provider_and_model_but_no_credentials(tmp_path, settings):
    samples = [sample("s1", "Which paper discusses graph retrieval?", "Graph.", ["p1"], "semantic_topic")]
    _, metrics_path, _ = run(tmp_path, settings, samples, {samples[0]["question"]: ("Graph.", ["p1"])})
    payload = json.loads(metrics_path.read_text(encoding="utf-8"))
    assert payload["provider"] == "openrouter"
    assert payload["model"] == "nvidia/nemotron-3-ultra-550b-a55b:free"
    assert payload["embedding_model"] == settings.embedding_model
    assert "api_key" not in json.dumps(payload).lower()


# --- artifact shape ------------------------------------------------------------------------------------


def test_metrics_record_the_test_set_path_and_fingerprint(tmp_path, settings):
    from evaluation.testset import test_set_fingerprint

    samples = [sample("s1", "Which paper discusses graph retrieval?", "Graph.", ["p1"], "semantic_topic")]
    bundle, metrics_path, _ = run(
        tmp_path, settings, samples, {samples[0]["question"]: ("Graph.", ["p1"])}
    )
    payload = json.loads(metrics_path.read_text(encoding="utf-8"))
    assert payload["evaluation_set_fingerprint"] == test_set_fingerprint(samples)
    assert payload["evaluation_set_path"].endswith("test_set.json")
    assert payload["state"] == "baseline"
    assert payload["started_at"] and payload["completed_at"]
    assert payload == bundle.summary


def test_state_and_dataset_path_are_recorded(tmp_path, settings):
    samples = [sample("s1", "Which paper discusses graph retrieval?", "Graph.", ["p1"], "semantic_topic")]
    bundle, _, _ = run(
        tmp_path,
        settings,
        samples,
        {samples[0]["question"]: ("Graph.", ["p1"])},
        state="corrupted",
        dataset_path="data/clean/papers_clean_corrupted.csv",
    )
    assert bundle.summary["state"] == "corrupted"
    assert bundle.summary["dataset_path"] == "data/clean/papers_clean_corrupted.csv"
    assert bundle.summary["collection_name"] == "papers-test"


def test_both_artifacts_reload_as_json(tmp_path, settings):
    samples = [sample("s1", "Which paper discusses graph retrieval?", "Graph.", ["p1"], "semantic_topic")]
    bundle, metrics_path, answers_path = run(
        tmp_path, settings, samples, {samples[0]["question"]: ("Graph.", ["p1"])}
    )
    assert json.loads(metrics_path.read_text(encoding="utf-8")) == bundle.summary
    assert json.loads(answers_path.read_text(encoding="utf-8")) == bundle.answers


def test_ragas_is_skipped_by_default(tmp_path, settings):
    samples = [sample("s1", "Which paper discusses graph retrieval?", "Graph.", ["p1"], "semantic_topic")]
    bundle, _, _ = run(tmp_path, settings, samples, {samples[0]["question"]: ("Graph.", ["p1"])})
    assert "skipped" in bundle.summary["ragas"]


def test_top_k_override_is_recorded_and_passed_through(tmp_path, settings):
    seen = {}

    def answer_fn(question, settings, index, top_k=None):
        seen["top_k"] = top_k
        return FakeAnswerResult(question, "Graph.", ["p1"])

    samples = [sample("s1", "Which paper discusses graph retrieval?", "Graph.", ["p1"], "semantic_topic")]
    bundle, _, _ = run(
        tmp_path, settings, samples, {}, answer_fn=answer_fn, top_k=9
    )
    assert seen["top_k"] == 9
    assert bundle.summary["top_k"] == 9
    assert bundle.answers[0]["top_k"] == 9
