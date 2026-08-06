"""Run the tool-using LLM agent over real evaluation questions and score what it answers.

The evaluation pipeline scores `retrieval.qa.answer_question`, which resolves answers from
document metadata by keyword and never calls a model. This module exercises the other path -
the LangChain agent in `retrieval.agent`, which decides for itself whether to search or look
up - and grades it against the same locked ground truth with the same token F1, so the two
are directly comparable.

Nothing here is simulated. If the provider refuses the call the item records the sanitized
error and counts as a failure; it is never given a score.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable
import time

from core.config import Settings, load_settings, normalized_provider
from core.utils import now_utc, read_json, write_json

DEFAULT_QUESTION_COUNT = 4


def _extract_final_answer(messages: list[Any]) -> str:
    """Same final-message rule as retrieval.agent.run_agent_question."""
    if not messages:
        return ""
    final = messages[-1]
    return getattr(final, "content", str(final))


def _extract_tool_calls(messages: list[Any]) -> list[str]:
    """Which tools the agent chose to call, in order.

    Read from the message trace rather than assumed, so the demo shows what the agent
    actually did instead of what it is supposed to do.
    """
    names: list[str] = []
    for message in messages:
        for call in getattr(message, "tool_calls", None) or []:
            name = call.get("name") if isinstance(call, dict) else getattr(call, "name", None)
            if name:
                names.append(str(name))
        if getattr(message, "type", None) == "tool" and getattr(message, "name", None):
            names.append(str(message.name))
    # preserve order, drop repeats introduced by the call/result pairing
    seen: set[str] = set()
    ordered = []
    for name in names:
        if name not in seen:
            seen.add(name)
            ordered.append(name)
    return ordered


def select_demo_questions(settings: Settings, count: int = DEFAULT_QUESTION_COUNT) -> list[dict[str, Any]]:
    """Take the first questions of the locked evaluation set, one per question_type first.

    Drawn from the real test set rather than written here, so the demo is graded against
    ground truth that the evaluation already uses.
    """
    from evaluation.testset import load_test_set, validate_test_set

    samples = load_test_set(settings.paths.eval_testset)
    validate_test_set(samples)

    chosen: list[dict[str, Any]] = []
    seen_types: set[str] = set()
    for sample in samples:  # one of each type first, so the demo covers the whole contract
        if sample["question_type"] not in seen_types:
            seen_types.add(sample["question_type"])
            chosen.append(sample)
        if len(chosen) >= count:
            return chosen
    for sample in samples:
        if sample not in chosen:
            chosen.append(sample)
        if len(chosen) >= count:
            break
    return chosen


def run_agent_demo(
    settings: Settings | None = None,
    *,
    state: str = "baseline",
    count: int = DEFAULT_QUESTION_COUNT,
    questions: list[dict[str, Any]] | None = None,
    output_path: Path | None = None,
    agent_runner: Callable[[str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Ask the agent `count` real questions, score both paths, and persist the transcript.

    `agent_runner` is a test seam. Left unset, the real LangChain agent from
    `retrieval.agent` is built against the requested state's index.
    """
    from evaluation.metrics import _sanitize_error, _token_f1

    settings = settings or load_settings()
    output_path = Path(output_path or settings.paths.demo_answers)
    started_at = now_utc()

    embeddings_path = {
        "baseline": settings.paths.embeddings_json,
        "corrupted": settings.paths.corrupted_embeddings_json,
        "repaired": settings.paths.repaired_embeddings_json,
    }.get(state)
    if embeddings_path is None:
        raise ValueError(f"Unknown state {state!r}; expected baseline, corrupted or repaired.")
    if not Path(embeddings_path).is_file():
        raise FileNotFoundError(
            f"No index manifest for state {state!r} at {embeddings_path}. "
            "Run the pipeline for that state first."
        )

    selected = questions if questions is not None else select_demo_questions(settings, count)

    index = None
    collection_name = None
    qa_answer = None
    if agent_runner is None:
        from retrieval.agent import build_agent
        from retrieval.index import LocalEmbeddingIndex
        from retrieval.qa import answer_question

        index = LocalEmbeddingIndex.load(settings, Path(embeddings_path))
        collection_name = index.collection_name
        agent = build_agent(settings=settings, index=index)
        qa_answer = answer_question

        def agent_runner(question: str) -> dict[str, Any]:  # noqa: F811
            result = agent.invoke({"messages": [{"role": "user", "content": question}]})
            messages = result.get("messages", [])
            return {
                "answer": _extract_final_answer(messages),
                "tool_calls": _extract_tool_calls(messages),
                "message_count": len(messages),
            }

    items: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for sample in selected:
        question = sample["question"]
        reference = sample.get("ground_truth", "")
        record: dict[str, Any] = {
            "id": sample.get("id"),
            "question_type": sample.get("question_type"),
            "question": question,
            "ground_truth": reference,
            "ground_truth_doc_ids": sample.get("ground_truth_doc_ids", []),
        }

        # The deterministic path the evaluation scores, for side-by-side comparison.
        if qa_answer is not None and index is not None:
            try:
                qa_result = qa_answer(question, settings=settings, index=index)
                record["qa_answer"] = qa_result.answer
                record["qa_retrieved_doc_ids"] = list(qa_result.retrieved_doc_ids)
                record["qa_token_f1"] = _token_f1(reference, qa_result.answer)
            except Exception as exc:
                record["qa_answer"] = None
                record["qa_token_f1"] = None
                record["qa_error"] = _sanitize_error(exc, settings)

        started = time.perf_counter()
        try:
            outcome = agent_runner(question)
            answer = outcome.get("answer") or ""
            record.update(
                {
                    "status": "answered",
                    "agent_answer": answer,
                    "agent_token_f1": _token_f1(reference, answer),
                    "tool_calls": outcome.get("tool_calls", []),
                    "message_count": outcome.get("message_count"),
                    "error": None,
                }
            )
        except Exception as exc:
            message = _sanitize_error(exc, settings)
            record.update(
                {
                    "status": "failed",
                    "agent_answer": None,
                    "agent_token_f1": None,
                    "tool_calls": [],
                    "message_count": None,
                    "error": message,
                }
            )
            errors.append({"id": record["id"], "error": message})
        record["duration_ms"] = round((time.perf_counter() - started) * 1000, 1)
        items.append(record)

    answered = [item for item in items if item["status"] == "answered"]
    agent_scores = [item["agent_token_f1"] for item in answered if item["agent_token_f1"] is not None]
    qa_scores = [item.get("qa_token_f1") for item in items if item.get("qa_token_f1") is not None]

    payload = {
        "state": state,
        "started_at": started_at.isoformat(),
        "completed_at": now_utc().isoformat(),
        "provider": normalized_provider(settings),
        "model": settings.model_name,
        "collection_name": collection_name,
        "evaluation_set_path": str(settings.paths.eval_testset),
        "questions": len(items),
        "answered": len(answered),
        "failed": len(items) - len(answered),
        # None, not 0.0: no successful call means the agent was not measured.
        "mean_agent_token_f1": (sum(agent_scores) / len(agent_scores)) if agent_scores else None,
        "mean_qa_token_f1": (sum(qa_scores) / len(qa_scores)) if qa_scores else None,
        "items": items,
        "errors": errors,
    }
    if settings.paths.eval_testset.is_file():
        from evaluation.testset import test_set_fingerprint

        payload["evaluation_set_fingerprint"] = test_set_fingerprint(read_json(settings.paths.eval_testset))

    write_json(output_path, payload)
    return payload


def main() -> None:
    settings = load_settings()
    payload = run_agent_demo(settings)
    print(
        f"[agent-demo] {payload['answered']}/{payload['questions']} answered "
        f"({payload['failed']} failed) -> {settings.paths.demo_answers}"
    )
    if payload["failed"]:
        print(f"[agent-demo] first error: {payload['errors'][0]['error'][:200]}")
