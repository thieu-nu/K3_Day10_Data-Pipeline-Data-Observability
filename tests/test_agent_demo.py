from __future__ import annotations

import json

import pytest

from conftest import FAKE_KEY, SECRET_PREFIX, make_clean_df
from core.config import load_settings
from core.utils import write_json
from evaluation.testset import build_test_set
from pipelines.agent_demo import run_agent_demo, select_demo_questions


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    """A project tree with a locked test set and a stand-in index manifest."""
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("LLM_MODEL", "nvidia/nemotron-3-ultra-550b-a55b:free")
    monkeypatch.setenv("OPENROUTER_API_KEY", FAKE_KEY)
    settings = load_settings(project_dir=tmp_path)
    samples = build_test_set(make_clean_df(24), settings.paths.eval_testset)
    write_json(settings.paths.embeddings_json, {"collection_name": "papers-baseline", "documents": []})
    return settings, samples


def test_questions_come_from_the_locked_test_set(prepared):
    settings, samples = prepared
    chosen = select_demo_questions(settings, count=4)
    assert len(chosen) == 4
    ids = {s["id"] for s in samples}
    assert all(item["id"] in ids for item in chosen)


def test_question_types_are_spread_before_repeating(prepared):
    settings, _ = prepared
    chosen = select_demo_questions(settings, count=4)
    assert len({item["question_type"] for item in chosen}) == 4


def test_successful_run_scores_the_agent_against_ground_truth(prepared):
    settings, _ = prepared

    def runner(question: str):
        sample = next(s for s in select_demo_questions(settings, 4) if s["question"] == question)
        return {"answer": sample["ground_truth"], "tool_calls": ["semantic_search_papers"], "message_count": 3}

    payload = run_agent_demo(settings, count=4, agent_runner=runner)
    assert payload["answered"] == 4
    assert payload["failed"] == 0
    assert payload["mean_agent_token_f1"] == 1.0
    assert all(item["tool_calls"] == ["semantic_search_papers"] for item in payload["items"])


def test_partial_answer_scores_between_zero_and_one(prepared):
    settings, _ = prepared
    payload = run_agent_demo(
        settings,
        count=2,
        agent_runner=lambda q: {"answer": "retrieval augmented generation", "tool_calls": []},
    )
    for item in payload["items"]:
        assert 0.0 <= item["agent_token_f1"] <= 1.0


def test_provider_failure_is_recorded_not_scored(prepared):
    settings, _ = prepared

    def boom(question: str):
        raise RuntimeError("Error code: 429 - rate limit exceeded: free-models-per-day")

    payload = run_agent_demo(settings, count=3, agent_runner=boom)
    assert payload["answered"] == 0
    assert payload["failed"] == 3
    assert payload["mean_agent_token_f1"] is None  # never 0.0
    assert len(payload["errors"]) == 3
    assert "429" in payload["errors"][0]["error"]
    for item in payload["items"]:
        assert item["status"] == "failed"
        assert item["agent_answer"] is None
        assert item["agent_token_f1"] is None


def test_partial_failure_averages_only_the_answered_questions(prepared):
    settings, _ = prepared
    calls = {"n": 0}

    def flaky(question: str):
        calls["n"] += 1
        if calls["n"] % 2 == 0:
            raise TimeoutError("upstream timeout")
        return {"answer": "", "tool_calls": []}

    payload = run_agent_demo(settings, count=4, agent_runner=flaky)
    assert payload["answered"] == 2
    assert payload["failed"] == 2
    assert payload["mean_agent_token_f1"] == 0.0  # measured as 0, unlike the unmeasured case


def test_errors_are_sanitized_before_being_written(prepared):
    settings, _ = prepared

    def leaky(question: str):
        raise RuntimeError(f"401 Unauthorized, Authorization: Bearer {FAKE_KEY}")

    payload = run_agent_demo(settings, count=1, agent_runner=leaky)
    blob = json.dumps(payload)
    assert FAKE_KEY not in blob
    assert SECRET_PREFIX not in blob
    assert "***" in payload["errors"][0]["error"]


def test_artifact_is_written_and_reloads(prepared):
    settings, _ = prepared
    payload = run_agent_demo(settings, count=2, agent_runner=lambda q: {"answer": "x", "tool_calls": []})
    path = settings.paths.demo_answers
    assert path.is_file()
    assert json.loads(path.read_text(encoding="utf-8")) == payload
    assert payload["provider"] == "openrouter"
    assert payload["model"] == "nvidia/nemotron-3-ultra-550b-a55b:free"
    assert payload["evaluation_set_fingerprint"]


def test_unknown_state_is_refused(prepared):
    settings, _ = prepared
    with pytest.raises(ValueError, match="Unknown state"):
        run_agent_demo(settings, state="sideways", agent_runner=lambda q: {"answer": "x"})


def test_missing_index_manifest_is_refused(prepared):
    settings, _ = prepared
    with pytest.raises(FileNotFoundError, match="No index manifest"):
        run_agent_demo(settings, state="corrupted", agent_runner=lambda q: {"answer": "x"})
