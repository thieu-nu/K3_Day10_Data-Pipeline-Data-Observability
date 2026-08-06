from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from typing import Any, Callable
import json
import random
import re

import pandas as pd

from core.utils import (
    first_sentence,
    is_blank,
    normalize_whitespace,
    now_utc,
    read_json,
    safe_slug,
    write_json,
)

TEST_SET_SEED = 20251110
QUESTIONS_PER_TYPE = 3
MIN_DOCUMENTS = 5
MIN_SUMMARY_CHARS = 40
MIN_GROUND_TRUTH_CHARS = 3

SEMANTIC_TOPIC_TYPE = "semantic_topic"
QUESTION_TYPES = ("summary", "authors", "date", "categories", SEMANTIC_TOPIC_TYPE)
REQUIRED_COLUMNS = ("paper_id", "title", "summary", "authors_joined", "categories_joined", "published")
SAMPLE_KEYS = ("id", "question_type", "question", "ground_truth", "ground_truth_doc_ids")

# Mirror of the keyword dispatch in retrieval.qa._extract_answer. That module is owned by
# another role and must not be edited here, so the generated wording is checked against
# these literals instead: a question whose wording routes to the wrong metadata field
# would measure the dispatcher, not the data quality.
AUTHOR_TRIGGERS = ("who authored", "list the authors")
DATE_TRIGGERS = ("when was", "publication date", "published on")
CATEGORY_TRIGGERS = ("what categories",)

# Mirror of the exact-lookup trigger in retrieval.qa.answer_question: the first
# single-quoted span is fed to index.lookup() and, on a hit, pinned at rank 0. Kept here as
# the single definition so evaluation.metrics can reuse it instead of writing a second copy.
QA_EXACT_LOOKUP_PATTERN = re.compile(r"'([^']+)'")

# retrieval.qa answers a semantic_topic question off the top-1 document's summary, exactly
# like a plain summary question; only the retrieval path differs.
QA_ROUTED_TYPE = {
    "summary": "summary",
    "authors": "authors",
    "date": "date",
    "categories": "categories",
    SEMANTIC_TOPIC_TYPE: "summary",
}

# Topic phrases are contiguous windows lifted verbatim out of a real title or summary, so
# every query stays checkable against the record it points at.
TOPIC_WINDOW_SIZES = (5, 4, 6, 3)
MIN_TOPIC_CONTENT_WORDS = 2
MIN_TOPIC_WORD_LENGTH = 3
TOPIC_STOPWORDS = frozenset(
    """a an and are as at be been but by for from has have how in into is it its of on or
    that the their there these this to via was were what when where which who with within
    using use used toward towards about across after against among over under between""".split()
)


class TestSetValidationError(ValueError):
    """Raised when the evaluation set does not satisfy the Role 5 contract."""

    __test__ = False  # the Test* prefix is domain vocabulary, not a pytest collection target


def _is_blank(value: Any) -> bool:
    return is_blank(value)


def _text(value: Any) -> str:
    return normalize_whitespace(str(value))


def _has_valid_date(value: Any) -> bool:
    if _is_blank(value):
        return False
    parsed = pd.to_datetime(value, errors="coerce")
    return not pd.isna(parsed)


def qa_dispatch_type(question: str) -> str:
    """Return the question_type that retrieval.qa would answer this wording with."""
    lowered = question.lower()
    if any(trigger in lowered for trigger in AUTHOR_TRIGGERS):
        return "authors"
    if any(trigger in lowered for trigger in DATE_TRIGGERS):
        return "date"
    if any(trigger in lowered for trigger in CATEGORY_TRIGGERS):
        return "categories"
    return "summary"


def has_quoted_span(text: str) -> bool:
    """True when retrieval.qa would attempt its exact lookup on this wording."""
    return QA_EXACT_LOOKUP_PATTERN.search(text) is not None


def _content_words(phrase: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9]+", phrase.lower())
    return [token for token in tokens if len(token) >= MIN_TOPIC_WORD_LENGTH and token not in TOPIC_STOPWORDS]


def _document_haystacks(records: list[dict[str, Any]]) -> dict[str, str]:
    return {
        _text(row["paper_id"]): f"{_text(row['title'])} {_text(row['summary'])}".lower()
        for row in records
    }


def _topic_phrase(row: dict[str, Any], haystacks: dict[str, str]) -> str | None:
    """Pick a contiguous phrase that occurs in this document and in no other one.

    The phrase is copied verbatim out of the real title (or, failing that, the real
    summary), never generated, and is accepted only when it is a strict sub-span of its
    source and unique across the corpus. Uniqueness is what makes the query fair: there is
    exactly one document a correct retriever could return. Rows that cannot produce such a
    phrase yield no semantic question at all rather than an ambiguous one.
    """
    paper_id = _text(row["paper_id"])
    if paper_id not in haystacks:
        return None
    own_haystack = haystacks[paper_id]
    other_haystacks = [text for other_id, text in haystacks.items() if other_id != paper_id]

    for source in (_text(row["title"]), _text(row["summary"])):
        words = source.split()
        for size in TOPIC_WINDOW_SIZES:
            if size >= len(words):
                continue
            for start in range(len(words) - size + 1):
                phrase = " ".join(words[start : start + size]).strip(" ,.;:!?-—")
                if not phrase or "'" in phrase:
                    continue
                if len(_content_words(phrase)) < MIN_TOPIC_CONTENT_WORDS:
                    continue
                needle = phrase.lower()
                if needle not in own_haystack:
                    continue
                if any(needle in other for other in other_haystacks):
                    continue
                return phrase
    return None


def _build_semantic_topic_question(
    row: dict[str, Any], haystacks: dict[str, str]
) -> tuple[str, str] | None:
    summary = _text(row["summary"])
    if _is_blank(summary) or len(summary) < MIN_SUMMARY_CHARS:
        return None
    ground_truth = first_sentence(summary)
    if len(ground_truth) < MIN_GROUND_TRUTH_CHARS:
        return None
    phrase = _topic_phrase(row, haystacks)
    if phrase is None:
        return None
    question = f"Which paper discusses {phrase}?"
    if has_quoted_span(question):
        return None
    return question, ground_truth


def _title_reference(title: str) -> str:
    """Quote the title so retrieval.qa can run its exact lookup.

    That lookup keys off the first single-quoted span, so a title that already contains
    an apostrophe is referenced unquoted: the question stays valid and answerable, it
    just falls back to pure semantic retrieval instead of the exact-lookup shortcut.
    """
    if "'" in title:
        return title
    return f"'{title}'"


def _build_summary_question(row: dict[str, Any]) -> tuple[str, str] | None:
    summary = _text(row["summary"])
    if _is_blank(summary) or len(summary) < MIN_SUMMARY_CHARS:
        return None
    ground_truth = first_sentence(summary)
    if len(ground_truth) < MIN_GROUND_TRUTH_CHARS:
        return None
    return f"Summarize the paper titled {_title_reference(_text(row['title']))}.", ground_truth


def _build_authors_question(row: dict[str, Any]) -> tuple[str, str] | None:
    if _is_blank(row["authors_joined"]):
        return None
    return (
        f"Who authored the paper titled {_title_reference(_text(row['title']))}?",
        _text(row["authors_joined"]),
    )


def _build_date_question(row: dict[str, Any]) -> tuple[str, str] | None:
    if not _has_valid_date(row["published"]):
        return None
    return (
        f"When was the paper titled {_title_reference(_text(row['title']))} published?",
        _text(row["published"]),
    )


def _build_categories_question(row: dict[str, Any]) -> tuple[str, str] | None:
    if _is_blank(row["categories_joined"]):
        return None
    return (
        f"What categories are assigned to the paper titled {_title_reference(_text(row['title']))}?",
        _text(row["categories_joined"]),
    )


_BUILDERS: dict[str, Callable[[dict[str, Any]], tuple[str, str] | None]] = {
    "summary": _build_summary_question,
    "authors": _build_authors_question,
    "date": _build_date_question,
    "categories": _build_categories_question,
}


def test_set_fingerprint(samples: list[dict[str, Any]]) -> str:
    """Stable content hash used to prove baseline/corrupted/repaired share one test set."""
    canonical = json.dumps(samples, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return sha256(canonical.encode("utf-8")).hexdigest()


test_set_fingerprint.__test__ = False  # the test_ prefix here means evaluation set, not pytest


def metadata_path(output_path: Path) -> Path:
    return Path(output_path).with_name(f"{Path(output_path).stem}_metadata.json")


def validate_test_set(samples: Any, df: pd.DataFrame | None = None) -> None:
    """Validate the evaluation set contract; raise TestSetValidationError on the first problem.

    `df` is the *baseline clean* dataset. Pass it when the set is generated or when
    re-validating against baseline. Leave it None when loading the locked set for a
    corrupted/repaired run, where documents are expected to be missing on purpose.
    """
    if not isinstance(samples, list):
        raise TestSetValidationError("Test set must be a JSON list of samples.")
    if not samples:
        raise TestSetValidationError("Test set is empty; refusing to evaluate on zero questions.")

    known_ids = None
    if df is not None:
        if "paper_id" not in df.columns:
            raise TestSetValidationError("Clean dataset has no `paper_id` column.")
        known_ids = {_text(value) for value in df["paper_id"].tolist() if not _is_blank(value)}

    seen_ids: set[str] = set()
    seen_questions: set[tuple[str, str]] = set()

    for position, sample in enumerate(samples):
        where = f"sample #{position}"
        if not isinstance(sample, dict):
            raise TestSetValidationError(f"{where}: expected an object, got {type(sample).__name__}.")

        missing = [key for key in SAMPLE_KEYS if key not in sample]
        if missing:
            raise TestSetValidationError(f"{where}: missing required field(s) {missing}.")
        extra = [key for key in sample if key not in SAMPLE_KEYS]
        if extra:
            raise TestSetValidationError(f"{where}: unexpected field(s) {extra}.")

        sample_id = sample["id"]
        if not isinstance(sample_id, str) or _is_blank(sample_id):
            raise TestSetValidationError(f"{where}: `id` must be a non-empty string.")
        if sample_id in seen_ids:
            raise TestSetValidationError(f"{where}: duplicate id {sample_id!r}.")
        seen_ids.add(sample_id)

        question_type = sample["question_type"]
        if question_type not in QUESTION_TYPES:
            raise TestSetValidationError(
                f"{where}: question_type {question_type!r} is not one of {list(QUESTION_TYPES)}."
            )

        question = sample["question"]
        if not isinstance(question, str) or _is_blank(question):
            raise TestSetValidationError(f"{where}: `question` must be a non-empty string.")
        dispatched = qa_dispatch_type(question)
        expected_route = QA_ROUTED_TYPE[question_type]
        if dispatched != expected_route:
            raise TestSetValidationError(
                f"{where}: wording routes to {dispatched!r} in retrieval.qa but question_type "
                f"{question_type!r} expects {expected_route!r}; the answer would be graded "
                "against the wrong field."
            )
        if question_type == SEMANTIC_TOPIC_TYPE and has_quoted_span(question):
            raise TestSetValidationError(
                f"{where}: a semantic_topic question must not contain a single-quoted span; it "
                "would trigger the exact lookup in retrieval.qa and stop measuring semantic search."
            )
        question_key = (question_type, question.strip().lower())
        if question_key in seen_questions:
            raise TestSetValidationError(f"{where}: duplicate question for type {question_type!r}.")
        seen_questions.add(question_key)

        ground_truth = sample["ground_truth"]
        if not isinstance(ground_truth, str) or _is_blank(ground_truth):
            raise TestSetValidationError(f"{where}: `ground_truth` must be a non-empty string.")

        doc_ids = sample["ground_truth_doc_ids"]
        if not isinstance(doc_ids, list) or not doc_ids:
            raise TestSetValidationError(f"{where}: `ground_truth_doc_ids` must be a non-empty list.")
        for doc_id in doc_ids:
            if not isinstance(doc_id, str) or _is_blank(doc_id):
                raise TestSetValidationError(f"{where}: document id {doc_id!r} is not a non-empty string.")
            if known_ids is not None and doc_id not in known_ids:
                raise TestSetValidationError(
                    f"{where}: document id {doc_id!r} does not exist in the clean dataset."
                )


def build_test_set(
    df: pd.DataFrame,
    output_path,
    *,
    seed: int = TEST_SET_SEED,
    questions_per_type: int = QUESTIONS_PER_TYPE,
    source_path=None,
) -> list[dict[str, Any]]:
    """Build the evaluation set from the *cleaned* dataframe and persist it as a JSON list.

    Every question is derived from a real row: `ground_truth` is read back off that row and
    `ground_truth_doc_ids` carries its real `paper_id`. Nothing is synthesised. Rows that
    cannot support a given question type (blank authors, unparseable date, too-short
    summary) are skipped rather than filled in.

    Sampling is seeded, so the same cleaned dataset always yields the same test set.
    Writes the samples to `output_path` and a sidecar `<stem>_metadata.json` holding the
    provenance the list schema itself cannot carry (seed, counts, fingerprint).
    """
    output_path = Path(output_path)

    if df is None or len(df) == 0:
        raise TestSetValidationError("Cleaned dataset is empty; cannot build an evaluation set.")
    missing_columns = [column for column in REQUIRED_COLUMNS if column not in df.columns]
    if missing_columns:
        raise TestSetValidationError(f"Cleaned dataset is missing required column(s): {missing_columns}.")
    if questions_per_type < 1:
        raise TestSetValidationError("questions_per_type must be at least 1.")

    records = [row for row in df.to_dict(orient="records") if not _is_blank(row.get("paper_id"))]
    if len(records) < MIN_DOCUMENTS:
        raise TestSetValidationError(
            f"Cleaned dataset has {len(records)} usable document(s) with a paper_id; "
            f"at least {MIN_DOCUMENTS} are required to build an evaluation set."
        )
    records.sort(key=lambda row: _text(row["paper_id"]))

    haystacks = _document_haystacks(records)
    samples: list[dict[str, Any]] = []
    # Two clean papers can legitimately share a title, which would yield the same metadata
    # question twice; such a question has no single answerable target, so the later
    # candidate is skipped rather than emitted and rejected downstream.
    seen_questions: set[tuple[str, str]] = set()
    for question_type in QUESTION_TYPES:
        builder = _BUILDERS.get(question_type)
        order = list(range(len(records)))
        random.Random(f"{seed}:{question_type}").shuffle(order)

        taken = 0
        for position in order:
            if taken >= questions_per_type:
                break
            row = records[position]
            if question_type == SEMANTIC_TOPIC_TYPE:
                built = _build_semantic_topic_question(row, haystacks)
            else:
                built = builder(row)
            if built is None:
                continue
            question, ground_truth = built
            if qa_dispatch_type(question) != QA_ROUTED_TYPE[question_type]:
                continue
            question_key = (question_type, question.strip().lower())
            if question_key in seen_questions:
                continue
            seen_questions.add(question_key)
            paper_id = _text(row["paper_id"])
            samples.append(
                {
                    "id": f"{question_type}-{safe_slug(paper_id)}",
                    "question_type": question_type,
                    "question": question,
                    "ground_truth": ground_truth,
                    "ground_truth_doc_ids": [paper_id],
                }
            )
            taken += 1

    validate_test_set(samples, df)
    write_json(output_path, samples)

    type_counts = {
        question_type: sum(1 for sample in samples if sample["question_type"] == question_type)
        for question_type in QUESTION_TYPES
    }
    warnings: list[str] = []
    if not type_counts[SEMANTIC_TOPIC_TYPE]:
        warnings.append(
            "No semantic_topic question could be built: no document yielded a topic phrase that "
            "is unique across the corpus. Retrieval will only be measurable through the exact "
            "lookup route, which does not exercise semantic search."
        )
    for question_type, count in type_counts.items():
        if count < questions_per_type:
            warnings.append(
                f"Only {count}/{questions_per_type} {question_type} question(s) could be built "
                "from eligible rows."
            )

    write_json(
        metadata_path(output_path),
        {
            "generated_at": now_utc().isoformat(),
            "seed": seed,
            "questions_per_type": questions_per_type,
            "source_clean_path": str(source_path) if source_path is not None else None,
            "clean_dataset_rows": int(len(df)),
            "documents_with_paper_id": len(records),
            "test_set_path": str(output_path),
            "total_questions": len(samples),
            "question_type_counts": type_counts,
            "fingerprint": test_set_fingerprint(samples),
            "warnings": warnings,
        },
    )
    return samples


def load_test_set(path) -> list[dict[str, Any]]:
    """Read a persisted evaluation set without validating it against any dataset."""
    payload = read_json(Path(path))
    if not isinstance(payload, list):
        raise TestSetValidationError(f"{path} must contain a JSON list of samples.")
    return payload


def load_or_build_test_set(
    df: pd.DataFrame,
    output_path,
    *,
    refresh: bool = False,
    validate_documents: bool = True,
    seed: int = TEST_SET_SEED,
    questions_per_type: int = QUESTIONS_PER_TYPE,
    source_path=None,
) -> list[dict[str, Any]]:
    """Return the locked evaluation set, building it only when it does not exist yet.

    Corrupted and repaired runs must call this with `refresh=False` and
    `validate_documents=False` so the baseline questions and ground truth are reused
    verbatim instead of being regenerated from degraded data.
    """
    output_path = Path(output_path)
    if output_path.exists() and not refresh:
        samples = load_test_set(output_path)
        validate_test_set(samples, df if validate_documents else None)
        return samples
    return build_test_set(
        df,
        output_path,
        seed=seed,
        questions_per_type=questions_per_type,
        source_path=source_path,
    )
