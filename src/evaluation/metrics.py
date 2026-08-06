from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable
import json
import os
import re
import sys
import types

from pydantic import BaseModel, Field, ValidationError

from core.config import Settings, normalized_provider, require_llm_credentials
from core.utils import normalize_whitespace, now_utc, redact_secrets, write_json
from evaluation.testset import (
    QA_EXACT_LOOKUP_PATTERN,
    load_test_set,
    test_set_fingerprint,
    validate_test_set,
)

if TYPE_CHECKING:  # pragma: no cover
    from retrieval.index import LocalEmbeddingIndex

JUDGE_RUBRIC_VERSION = "role5-judge-v1"
JUDGE_SCORE_SCALE = "1-5"
JUDGE_CORRECT_THRESHOLD = 4
JUDGE_MAX_ATTEMPTS = 2

ROUTE_EXACT_LOOKUP = "exact_lookup"
ROUTE_SEMANTIC_SEARCH = "semantic_search"

TOKEN_F1_DEFINITION = (
    "Symmetric F1 over the set of unique whitespace-separated tokens of each side, after "
    "lowercasing and whitespace normalisation. Punctuation is not stripped and token "
    "repetition is ignored. Returns 0.0 when either side has no tokens."
)

_ERROR_TEXT_LIMIT = 400


class JudgeVerdict(BaseModel):
    score: int = Field(ge=1, le=5)
    correct: bool
    reasoning: str


class EvaluationError(RuntimeError):
    """Raised when evaluation cannot honestly run at all (empty test set, empty index)."""


class JudgeParseError(ValueError):
    """Raised when the judge reply cannot be turned into a valid JudgeVerdict."""


@dataclass(frozen=True)
class EvaluationBundle:
    summary: dict[str, Any]
    answers: list[dict[str, Any]]


@dataclass(frozen=True)
class JudgeRuntime:
    status: str  # "ready" | "unavailable" | "skipped"
    llm: Any | None
    error: str | None


@dataclass(frozen=True)
class JudgeOutcome:
    status: str  # "success" | "failed" | "unavailable" | "skipped"
    verdict: JudgeVerdict | None
    error: str | None
    attempts: int


# --- text and secret helpers ---------------------------------------------------------------


def _token_f1(reference: str, prediction: str) -> float:
    """Unchanged from the starter implementation; see TOKEN_F1_DEFINITION for the semantics.

    Deliberately left byte-for-byte identical so baseline, corrupted and repaired runs are
    scored by exactly the same function.
    """
    ref_tokens = normalize_whitespace(reference).lower().split()
    pred_tokens = normalize_whitespace(prediction).lower().split()
    if not ref_tokens or not pred_tokens:
        return 0.0
    ref_set = set(ref_tokens)
    pred_set = set(pred_tokens)
    overlap = len(ref_set & pred_set)
    if overlap == 0:
        return 0.0
    precision = overlap / len(pred_set)
    recall = overlap / len(ref_set)
    return 2 * precision * recall / (precision + recall)


def _sanitize_error(value: Any, settings: Settings) -> str:
    """Render an error for an artifact with any credential material stripped out."""
    text = f"{type(value).__name__}: {value}" if isinstance(value, BaseException) else str(value)
    for secret in (
        settings.openrouter_api_key,
        settings.openai_api_key,
        settings.google_api_key,
        settings.anthropic_api_key,
        settings.custom_llm_api_key,
    ):
        if secret and len(secret) >= 8:
            text = text.replace(secret, "***")
    text = normalize_whitespace(redact_secrets(text))
    if len(text) > _ERROR_TEXT_LIMIT:
        text = text[:_ERROR_TEXT_LIMIT] + "..."
    return text


def _mean(values: list[float]) -> float | None:
    """Mean over the supplied values, or None when there is nothing to average.

    None is deliberate: an absent measurement must not be reported as 0.0.
    """
    if not values:
        return None
    return sum(values) / len(values)


# --- retrieval route -----------------------------------------------------------------------


def _probe_exact_lookup(index: Any, question: str) -> tuple[bool, str | None]:
    """Replay the precondition of the exact lookup inside retrieval.qa.answer_question.

    qa.py pins a document at rank 0 when the first single-quoted span of the question
    resolves through index.lookup(). It does not report that on AnswerResult and is owned by
    another role, so the same read-only probe is repeated here to label the route. A
    question whose quoted title no longer resolves (for instance after corruption truncated
    it) legitimately falls back to the semantic route.
    """
    match = QA_EXACT_LOOKUP_PATTERN.search(question)
    if not match:
        return False, None
    try:
        record = index.lookup(match.group(1))
    except Exception:
        return False, None
    if not record:
        return False, None
    paper_id = record.get("paper_id") if isinstance(record, dict) else None
    return True, str(paper_id) if paper_id is not None else None


def _index_document_count(index: Any) -> int | None:
    documents = getattr(index, "documents", None)
    if documents is not None:
        try:
            return len(documents)
        except TypeError:
            pass
    collection = getattr(index, "collection", None)
    if collection is not None:
        try:
            return int(collection.count())
        except Exception:
            return None
    return None


# --- LLM judge -------------------------------------------------------------------------------


def _judge_prompt(question: str, reference: str, prediction: str) -> str:
    return f"""
You grade an automated answer about a corpus of scholarly papers.

Question: {question}
Reference answer: {reference}
Model answer: {prediction}

Score the model answer against the reference answer on this rubric:
5 - materially identical to the reference; nothing missing or wrong
4 - correct, with only wording or formatting differences or a trivial omission
3 - partially correct; some reference facts captured, others missed or garbled
2 - mostly wrong; only incidental overlap with the reference
1 - wrong, empty, or unrelated

Set "correct" to true only when the score is {JUDGE_CORRECT_THRESHOLD} or higher.

Reply with one JSON object and nothing else:
{{"score": <integer 1-5>, "correct": <true|false>, "reasoning": "<one short sentence>"}}
""".strip()


def _message_text(response: Any) -> str:
    content = getattr(response, "content", response)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and "text" in block:
                parts.append(str(block["text"]))
        return "\n".join(parts)
    return str(content)


def _parse_judge_response(text: str) -> JudgeVerdict:
    """Turn a free-text judge reply into a verdict, or raise.

    Written for plain chat completions on purpose: the group's model is served through
    OpenRouter and tool calling / structured output cannot be assumed to work there.
    """
    if not text or not text.strip():
        raise JudgeParseError("Judge returned an empty response.")
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[A-Za-z0-9_]*\s*", "", cleaned)
        cleaned = re.sub(r"\s*```\s*$", "", cleaned)
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        raise JudgeParseError("Judge response contained no JSON object.")
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise JudgeParseError(f"Judge response was not valid JSON: {exc.msg}.") from exc
    if not isinstance(payload, dict):
        raise JudgeParseError("Judge response JSON was not an object.")
    try:
        return JudgeVerdict.model_validate(payload)
    except ValidationError as exc:
        raise JudgeParseError(
            f"Judge JSON did not match the verdict schema ({exc.error_count()} field error(s))."
        ) from exc


def _build_judge_runtime(settings: Settings, judge_llm: Any | None, run_judge: bool) -> JudgeRuntime:
    if not run_judge:
        return JudgeRuntime(status="skipped", llm=None, error=None)
    if judge_llm is not None:
        return JudgeRuntime(status="ready", llm=judge_llm, error=None)
    try:
        require_llm_credentials(settings)
        from retrieval.llm import build_llm

        return JudgeRuntime(status="ready", llm=build_llm(settings=settings, temperature=0.0), error=None)
    except Exception as exc:
        return JudgeRuntime(status="unavailable", llm=None, error=_sanitize_error(exc, settings))


def _judge_answer(
    runtime: JudgeRuntime,
    settings: Settings,
    question: str,
    reference: str,
    prediction: str,
) -> JudgeOutcome:
    """Ask the configured judge for a verdict. A provider failure stays a failure.

    There is no heuristic fallback: scoring a broken judge call from token overlap would
    publish a number under the name of an LLM judge that never answered.
    """
    if runtime.status == "skipped":
        return JudgeOutcome(status="skipped", verdict=None, error=None, attempts=0)
    if runtime.status != "ready" or runtime.llm is None:
        return JudgeOutcome(
            status="unavailable",
            verdict=None,
            error=runtime.error or "Judge model was not initialised.",
            attempts=0,
        )

    prompt = _judge_prompt(question, reference, prediction)
    last_error: str | None = None
    for attempt in range(1, JUDGE_MAX_ATTEMPTS + 1):
        try:
            response = runtime.llm.invoke(prompt)
            verdict = _parse_judge_response(_message_text(response))
            return JudgeOutcome(status="success", verdict=verdict, error=None, attempts=attempt)
        except Exception as exc:
            last_error = _sanitize_error(exc, settings)
    return JudgeOutcome(status="failed", verdict=None, error=last_error, attempts=JUDGE_MAX_ATTEMPTS)


def _overall_judge_status(runtime: JudgeRuntime, success_count: int, failure_count: int) -> str:
    if runtime.status == "skipped":
        return "skipped"
    if runtime.status == "unavailable":
        return "unavailable"
    if success_count and not failure_count:
        return "success"
    if success_count and failure_count:
        return "partial"
    if failure_count:
        return "failed"
    return "not_run"


# --- optional Ragas pass ------------------------------------------------------------------------


def _run_ragas(settings: Settings, answers: list[dict[str, Any]]) -> dict[str, Any]:
    if os.getenv("RUN_RAGAS", "").lower() not in {"1", "true", "yes"}:
        return {"skipped": "Set RUN_RAGAS=1 to enable the slower Ragas pass."}
    scored = [item for item in answers if item.get("status") == "evaluated"]
    if not scored:
        return {"skipped": "No successfully evaluated answer to score."}
    try:
        if "langchain_community.chat_models.vertexai" not in sys.modules:
            shim = types.ModuleType("langchain_community.chat_models.vertexai")
            shim.ChatVertexAI = type("ChatVertexAI", (), {})
            sys.modules["langchain_community.chat_models.vertexai"] = shim
        from datasets import Dataset
        from ragas import evaluate
        from ragas.metrics import answer_relevancy, context_precision, context_recall, faithfulness

        from retrieval.embeddings import MiniLMEmbeddings
        from retrieval.llm import build_llm

        dataset = Dataset.from_dict(
            {
                "question": [item["question"] for item in scored],
                "answer": [item["answer"] for item in scored],
                "ground_truth": [item["ground_truth"] for item in scored],
                "contexts": [item["retrieved_contexts"] for item in scored],
            }
        )
        result = evaluate(
            dataset,
            metrics=[answer_relevancy, context_precision, context_recall, faithfulness],
            llm=build_llm(settings=settings, temperature=0.0),
            embeddings=MiniLMEmbeddings(settings.embedding_model),
        )
        return dict(result)
    except Exception as exc:  # pragma: no cover
        return {"error": f"Ragas evaluation failed: {_sanitize_error(exc, settings)}"}


# --- pipeline ---------------------------------------------------------------------------------


def evaluate_pipeline(
    settings: Settings,
    index: "LocalEmbeddingIndex",
    test_set_path,
    metrics_output_path,
    answers_output_path,
    *,
    state: str = "baseline",
    dataset_path=None,
    top_k: int | None = None,
    run_judge: bool = True,
    answer_fn: Callable[..., Any] | None = None,
    judge_llm: Any | None = None,
) -> EvaluationBundle:
    """Evaluate one dataset state against the locked evaluation set.

    Positional parameters are unchanged. The keyword-only ones all default to the previous
    behaviour: `state`/`dataset_path` only label the artifact, `answer_fn` defaults to
    retrieval.qa.answer_question and `judge_llm` to the provider from settings.

    `answer_fn` and `judge_llm` are test seams. Production pipelines must leave both unset so
    the real QA path and the configured provider are exercised; a run that passes a
    substitute is not evidence about the pipeline.

    Refuses to produce metrics for an empty test set or an empty index. A failure on one
    question is recorded on that question and excluded from every denominator; it never
    discards the questions that did run and never silently counts as a retrieval miss.
    """
    started_at = now_utc()
    test_set_path = Path(test_set_path)

    test_set = load_test_set(test_set_path)
    validate_test_set(test_set)  # structure only; documents may be missing after corruption
    fingerprint = test_set_fingerprint(test_set)

    resolved_top_k = int(top_k if top_k is not None else settings.top_k)
    warnings: list[str] = []
    errors: list[dict[str, Any]] = []

    document_count = _index_document_count(index)
    if document_count == 0:
        raise EvaluationError(
            "The retrieval index is empty; refusing to report evaluation metrics for a corpus "
            "with zero documents."
        )
    if document_count is None:
        warnings.append("Index document count could not be read; the empty-index guard was skipped.")

    if answer_fn is None:
        from retrieval.qa import answer_question as answer_fn

    judge_runtime = _build_judge_runtime(settings, judge_llm, run_judge)
    if judge_runtime.status == "unavailable":
        warnings.append(f"LLM judge unavailable, judge metrics are null: {judge_runtime.error}")
    elif judge_runtime.status == "skipped":
        warnings.append("LLM judge was disabled for this run; judge metrics are null.")

    answers: list[dict[str, Any]] = []
    for item in test_set:
        record: dict[str, Any] = {
            "id": item["id"],
            "question_type": item["question_type"],
            "question": item["question"],
            "ground_truth": item["ground_truth"],
            "ground_truth_doc_ids": item["ground_truth_doc_ids"],
            "top_k": resolved_top_k,
        }

        try:
            result = answer_fn(item["question"], settings=settings, index=index, top_k=resolved_top_k)
        except Exception as exc:
            message = _sanitize_error(exc, settings)
            record.update(
                {
                    "status": "failed",
                    "error": message,
                    "answer": None,
                    "retrieved_doc_ids": [],
                    "retrieved_contexts": [],
                    "retrieved_ranks": {},
                    "hit_rank": None,
                    "retrieval_hit": None,
                    "exact_lookup_used": None,
                    "evaluation_route": None,
                    "token_f1": None,
                    "judge": None,
                    "judge_status": "not_run",
                    "judge_error": None,
                }
            )
            errors.append({"id": item["id"], "stage": "answer", "error": message})
            answers.append(record)
            continue

        exact_lookup_used, _ = _probe_exact_lookup(index, item["question"])
        retrieved_doc_ids = [str(doc_id).strip() for doc_id in result.retrieved_doc_ids]
        ground_truth_doc_ids = [str(doc_id).strip() for doc_id in item["ground_truth_doc_ids"]]
        retrieved_ranks = {
            doc_id: (retrieved_doc_ids.index(doc_id) + 1 if doc_id in retrieved_doc_ids else None)
            for doc_id in ground_truth_doc_ids
        }
        hit_ranks = [rank for rank in retrieved_ranks.values() if rank is not None]

        judge_outcome = _judge_answer(
            judge_runtime, settings, item["question"], item["ground_truth"], result.answer
        )
        if judge_outcome.error:
            errors.append({"id": item["id"], "stage": "judge", "error": judge_outcome.error})

        record.update(
            {
                "status": "evaluated",
                "error": None,
                "answer": result.answer,
                "retrieved_doc_ids": retrieved_doc_ids,
                "retrieved_contexts": list(result.retrieved_contexts),
                "retrieved_ranks": retrieved_ranks,
                "hit_rank": min(hit_ranks) if hit_ranks else None,
                "retrieval_hit": bool(hit_ranks),
                "exact_lookup_used": exact_lookup_used,
                "evaluation_route": ROUTE_EXACT_LOOKUP if exact_lookup_used else ROUTE_SEMANTIC_SEARCH,
                "token_f1": _token_f1(item["ground_truth"], result.answer),
                "judge": judge_outcome.verdict.model_dump() if judge_outcome.verdict else None,
                "judge_status": judge_outcome.status,
                "judge_error": judge_outcome.error,
            }
        )
        answers.append(record)

    evaluated = [item for item in answers if item["status"] == "evaluated"]
    failed = [item for item in answers if item["status"] == "failed"]
    semantic = [item for item in evaluated if item["evaluation_route"] == ROUTE_SEMANTIC_SEARCH]
    exact = [item for item in evaluated if item["evaluation_route"] == ROUTE_EXACT_LOOKUP]

    if not evaluated:
        warnings.append("No question could be evaluated; every retrieval metric is null.")
    if not semantic:
        warnings.append(
            "No question was routed through semantic search, so semantic_retrieval_hit_rate is "
            "null. Every evaluated question resolved through the exact lookup in retrieval.qa."
        )
    if not exact:
        warnings.append("No question was routed through the exact lookup; exact_lookup_success_rate is null.")

    judge_success = [item for item in evaluated if item["judge_status"] == "success"]
    judge_failed = [item for item in evaluated if item["judge_status"] in {"failed", "unavailable"}]

    summary: dict[str, Any] = {
        "state": state,
        "started_at": started_at.isoformat(),
        "completed_at": None,
        "evaluation_set_path": str(test_set_path),
        "evaluation_set_fingerprint": fingerprint,
        "dataset_path": str(dataset_path) if dataset_path is not None else None,
        "collection_name": getattr(index, "collection_name", None),
        "index_document_count": document_count,
        "provider": normalized_provider(settings),
        "model": settings.model_name,
        "embedding_model": settings.embedding_model,
        "top_k": resolved_top_k,
        "samples": len(answers),
        "evaluated_questions": len(evaluated),
        "failed_questions": len(failed),
        "hit_count": sum(1 for item in evaluated if item["retrieval_hit"]),
        "retrieval_hit_rate": _mean([1.0 if item["retrieval_hit"] else 0.0 for item in evaluated]),
        "semantic_samples": len(semantic),
        "semantic_hit_count": sum(1 for item in semantic if item["retrieval_hit"]),
        "semantic_retrieval_hit_rate": _mean([1.0 if item["retrieval_hit"] else 0.0 for item in semantic]),
        "exact_lookup_samples": len(exact),
        "exact_lookup_hit_count": sum(1 for item in exact if item["retrieval_hit"]),
        "exact_lookup_success_rate": _mean([1.0 if item["retrieval_hit"] else 0.0 for item in exact]),
        "mean_token_f1": _mean([float(item["token_f1"]) for item in evaluated]),
        "token_f1_definition": TOKEN_F1_DEFINITION,
        "judge_status": _overall_judge_status(judge_runtime, len(judge_success), len(judge_failed)),
        "judge_provider": normalized_provider(settings),
        "judge_model": settings.model_name,
        "judge_rubric_version": JUDGE_RUBRIC_VERSION,
        "judge_success_count": len(judge_success),
        "judge_failure_count": len(judge_failed),
        "judge_accuracy": _mean([1.0 if item["judge"]["correct"] else 0.0 for item in judge_success]),
        "mean_judge_score": _mean([float(item["judge"]["score"]) for item in judge_success]),
        "mean_judge_score_scale": JUDGE_SCORE_SCALE,
        "judge_init_error": judge_runtime.error,
        "errors": errors,
        "warnings": warnings,
    }
    summary["ragas"] = _run_ragas(settings, answers)
    summary["completed_at"] = now_utc().isoformat()

    bundle = EvaluationBundle(summary=summary, answers=answers)
    write_json(Path(metrics_output_path), summary)
    write_json(Path(answers_output_path), answers)
    return bundle
