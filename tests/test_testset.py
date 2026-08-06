from __future__ import annotations

from pathlib import Path
import copy
import json

import pandas as pd
import pytest

from conftest import make_clean_df, make_clean_row
from core.utils import first_sentence
from evaluation.testset import (
    AUTHOR_TRIGGERS,
    CATEGORY_TRIGGERS,
    DATE_TRIGGERS,
    QA_ROUTED_TYPE,
    QUESTION_TYPES,
    SAMPLE_KEYS,
    SEMANTIC_TOPIC_TYPE,
    TOPIC_STOPWORDS,
    TestSetValidationError,
    build_test_set,
    has_quoted_span,
    load_or_build_test_set,
    load_test_set,
    metadata_path,
    qa_dispatch_type,
    test_set_fingerprint,
    validate_test_set,
)

QA_SOURCE = Path(__file__).resolve().parents[1] / "src" / "retrieval" / "qa.py"


def build(tmp_path: Path, df: pd.DataFrame | None = None, **kwargs):
    output_path = tmp_path / "eval" / "test_set.json"
    samples = build_test_set(df if df is not None else make_clean_df(), output_path, **kwargs)
    return samples, output_path


# --- schema and provenance -------------------------------------------------------------


def test_top_level_artifact_is_a_json_list(tmp_path):
    _, output_path = build(tmp_path)
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert isinstance(payload, list)
    assert payload


def test_every_sample_has_exactly_the_contract_fields(tmp_path):
    samples, _ = build(tmp_path)
    for sample in samples:
        assert set(sample) == set(SAMPLE_KEYS)
        assert sample["question"].strip()
        assert sample["ground_truth"].strip()
        assert sample["question_type"] in QUESTION_TYPES
        assert isinstance(sample["ground_truth_doc_ids"], list)
        assert sample["ground_truth_doc_ids"]


def test_all_question_types_are_produced(tmp_path):
    samples, _ = build(tmp_path)
    assert {sample["question_type"] for sample in samples} == set(QUESTION_TYPES)


def test_sample_ids_are_unique(tmp_path):
    samples, _ = build(tmp_path)
    ids = [sample["id"] for sample in samples]
    assert len(ids) == len(set(ids))


def test_metadata_sidecar_records_seed_and_fingerprint(tmp_path):
    samples, output_path = build(tmp_path, seed=1234, source_path="data/clean/papers_clean.csv")
    metadata = json.loads(metadata_path(output_path).read_text(encoding="utf-8"))
    assert metadata["seed"] == 1234
    assert metadata["source_clean_path"] == "data/clean/papers_clean.csv"
    assert metadata["total_questions"] == len(samples)
    assert metadata["fingerprint"] == test_set_fingerprint(samples)
    assert sum(metadata["question_type_counts"].values()) == len(samples)


# --- ground truth comes from real rows --------------------------------------------------


def test_ground_truth_doc_ids_exist_in_clean_dataset(tmp_path):
    df = make_clean_df()
    samples, _ = build(tmp_path, df)
    known = set(df["paper_id"])
    for sample in samples:
        assert set(sample["ground_truth_doc_ids"]) <= known


def test_ground_truth_is_read_back_from_the_referenced_row(tmp_path):
    df = make_clean_df()
    samples, _ = build(tmp_path, df)
    by_paper_id = {row["paper_id"]: row for row in df.to_dict(orient="records")}
    expected = {
        "authors": lambda row: row["authors_joined"],
        "date": lambda row: row["published"],
        "categories": lambda row: row["categories_joined"],
        "summary": lambda row: first_sentence(row["summary"]),
        SEMANTIC_TOPIC_TYPE: lambda row: first_sentence(row["summary"]),
    }
    for sample in samples:
        row = by_paper_id[sample["ground_truth_doc_ids"][0]]
        assert sample["ground_truth"] == expected[sample["question_type"]](row)


def test_metadata_question_references_the_full_title_of_its_own_document(tmp_path):
    df = make_clean_df()
    samples, _ = build(tmp_path, df)
    by_paper_id = {row["paper_id"]: row for row in df.to_dict(orient="records")}
    for sample in samples:
        if sample["question_type"] == SEMANTIC_TOPIC_TYPE:
            continue
        title = by_paper_id[sample["ground_truth_doc_ids"][0]]["title"]
        assert title in sample["question"]


# --- wording stays compatible with retrieval/qa.py --------------------------------------


def test_mirrored_triggers_still_exist_in_qa_source():
    """qa.py is owned by another role; fail loudly if its dispatch keywords drift."""
    source = QA_SOURCE.read_text(encoding="utf-8")
    for trigger in AUTHOR_TRIGGERS + DATE_TRIGGERS + CATEGORY_TRIGGERS:
        assert f'"{trigger}"' in source, f"{trigger!r} no longer appears in retrieval/qa.py"


def test_generated_wording_routes_to_the_intended_field(tmp_path):
    samples, _ = build(tmp_path)
    for sample in samples:
        assert qa_dispatch_type(sample["question"]) == QA_ROUTED_TYPE[sample["question_type"]]


def test_exact_lookup_regex_still_exists_in_qa_source():
    source = QA_SOURCE.read_text(encoding="utf-8")
    assert r"""re.search(r"'([^']+)'", question)""" in source
    assert "index.lookup(" in source


def test_metadata_questions_are_single_quoted_for_exact_lookup(tmp_path):
    samples, _ = build(tmp_path)
    for sample in samples:
        if sample["question_type"] == SEMANTIC_TOPIC_TYPE:
            continue
        assert has_quoted_span(sample["question"])


# --- semantic_topic ---------------------------------------------------------------------


def test_semantic_topic_questions_never_trigger_the_exact_lookup(tmp_path):
    samples, _ = build(tmp_path)
    semantic = [s for s in samples if s["question_type"] == SEMANTIC_TOPIC_TYPE]
    assert semantic
    for sample in semantic:
        assert not has_quoted_span(sample["question"])
        assert "'" not in sample["question"]


def test_semantic_topic_phrase_is_verbatim_from_its_own_document(tmp_path):
    df = make_clean_df()
    samples, _ = build(tmp_path, df)
    haystacks = {
        row["paper_id"]: f"{row['title']} {row['summary']}".lower()
        for row in df.to_dict(orient="records")
    }
    for sample in samples:
        if sample["question_type"] != SEMANTIC_TOPIC_TYPE:
            continue
        phrase = sample["question"].removeprefix("Which paper discusses ").removesuffix("?").lower()
        target = sample["ground_truth_doc_ids"][0]
        assert phrase in haystacks[target]


def test_semantic_topic_phrase_is_unique_across_the_corpus(tmp_path):
    df = make_clean_df()
    samples, _ = build(tmp_path, df)
    haystacks = {
        row["paper_id"]: f"{row['title']} {row['summary']}".lower()
        for row in df.to_dict(orient="records")
    }
    for sample in samples:
        if sample["question_type"] != SEMANTIC_TOPIC_TYPE:
            continue
        phrase = sample["question"].removeprefix("Which paper discusses ").removesuffix("?").lower()
        target = sample["ground_truth_doc_ids"][0]
        matching = [pid for pid, hay in haystacks.items() if phrase in hay]
        assert matching == [target]


def test_semantic_topic_phrase_is_never_the_whole_title(tmp_path):
    df = make_clean_df()
    samples, _ = build(tmp_path, df)
    titles = {row["paper_id"]: row["title"] for row in df.to_dict(orient="records")}
    for sample in samples:
        if sample["question_type"] != SEMANTIC_TOPIC_TYPE:
            continue
        phrase = sample["question"].removeprefix("Which paper discusses ").removesuffix("?")
        assert phrase != titles[sample["ground_truth_doc_ids"][0]]


def test_indistinguishable_documents_yield_no_semantic_question(tmp_path):
    """Every row carries the same wording, so no phrase can point at a single paper."""
    rows = [
        make_clean_row(
            index,
            title="Retrieval Augmented Generation",
            summary="This paper studies retrieval augmented generation on a scholarly corpus.",
        )
        for index in range(8)
    ]
    samples, output_path = build(tmp_path, pd.DataFrame(rows), questions_per_type=8)
    assert not [s for s in samples if s["question_type"] == SEMANTIC_TOPIC_TYPE]
    metadata = json.loads(metadata_path(output_path).read_text(encoding="utf-8"))
    assert any("semantic_topic" in warning for warning in metadata["warnings"])


def test_duplicate_titles_do_not_produce_the_same_question_twice(tmp_path):
    rows = [make_clean_row(index, title="One Shared Title For Every Paper") for index in range(8)]
    samples, _ = build(tmp_path, pd.DataFrame(rows), questions_per_type=8)
    keys = [(s["question_type"], s["question"]) for s in samples]
    assert len(keys) == len(set(keys))


def test_semantic_topic_phrase_never_starts_or_ends_on_a_stopword(tmp_path):
    """A window like "Adapting Large Language Models for" must lose its dangling preposition."""
    rows = [
        make_clean_row(index, title=f"Adapting Large Language Models for Clinical Domain {index}")
        for index in range(8)
    ]
    samples, _ = build(tmp_path, pd.DataFrame(rows), questions_per_type=8)
    semantic = [s for s in samples if s["question_type"] == SEMANTIC_TOPIC_TYPE]
    assert semantic
    for sample in semantic:
        phrase = sample["question"].removeprefix("Which paper discusses ").removesuffix("?")
        words = phrase.split()
        assert words[0].lower() not in TOPIC_STOPWORDS, phrase
        assert words[-1].lower() not in TOPIC_STOPWORDS, phrase
        assert len(words) >= 3


def test_row_whose_first_sentence_is_a_bare_section_label_is_skipped(tmp_path):
    """Real abstracts open with things like "Abstract Background." - a useless ground truth."""
    rows = [make_clean_row(index) for index in range(8)]
    rows[0]["summary"] = "Abstract Background. " + "This paper then explains the method at length. " * 3
    blocked = rows[0]["paper_id"]
    samples, _ = build(tmp_path, pd.DataFrame(rows), questions_per_type=8)
    summary_like = {
        sample["ground_truth_doc_ids"][0]
        for sample in samples
        if sample["question_type"] in {"summary", SEMANTIC_TOPIC_TYPE}
    }
    assert blocked not in summary_like


def test_short_ground_truth_does_not_block_metadata_questions(tmp_path):
    """Only the summary-routed types need a usable first sentence; authors/date do not."""
    rows = [make_clean_row(index) for index in range(8)]
    rows[0]["summary"] = "Abstract Background."
    allowed = rows[0]["paper_id"]
    samples, _ = build(tmp_path, pd.DataFrame(rows), questions_per_type=8)
    metadata_docs = {
        sample["ground_truth_doc_ids"][0]
        for sample in samples
        if sample["question_type"] in {"authors", "date", "categories"}
    }
    assert allowed in metadata_docs


def test_semantic_topic_is_accepted_by_the_validator(tmp_path, clean_df):
    samples, _ = build(tmp_path)
    validate_test_set(samples, clean_df)


def test_validator_rejects_quoted_semantic_topic_question(tmp_path, clean_df):
    samples, _ = build(tmp_path)
    broken = copy.deepcopy(samples)
    semantic = next(s for s in broken if s["question_type"] == SEMANTIC_TOPIC_TYPE)
    semantic["question"] = "Which paper discusses 'Retrieval Augmented Generation Study Number 1'?"
    with pytest.raises(TestSetValidationError, match="single-quoted span"):
        validate_test_set(broken, clean_df)


def test_title_containing_apostrophe_is_referenced_without_quotes(tmp_path):
    rows = [
        make_clean_row(index, title=f"Don't Stop Retrieving Number {index}") for index in range(8)
    ]
    samples, _ = build(tmp_path, pd.DataFrame(rows))
    metadata_samples = [s for s in samples if s["question_type"] != SEMANTIC_TOPIC_TYPE]
    assert metadata_samples
    for sample in metadata_samples:
        assert "'Don" not in sample["question"]
        assert "Don't Stop Retrieving" in sample["question"]


# --- determinism and round trip ---------------------------------------------------------


def test_same_seed_and_data_give_identical_output(tmp_path):
    first, _ = build(tmp_path / "a")
    second, _ = build(tmp_path / "b")
    assert first == second
    assert test_set_fingerprint(first) == test_set_fingerprint(second)


def test_different_seed_changes_document_selection(tmp_path):
    first, _ = build(tmp_path / "a", make_clean_df(20), seed=1)
    second, _ = build(tmp_path / "b", make_clean_df(20), seed=2)
    assert test_set_fingerprint(first) != test_set_fingerprint(second)


def test_round_trip_save_and_load_preserves_content_and_fingerprint(tmp_path):
    samples, output_path = build(tmp_path)
    reloaded = load_test_set(output_path)
    assert reloaded == samples
    assert test_set_fingerprint(reloaded) == test_set_fingerprint(samples)


def test_load_or_build_reuses_the_locked_file(tmp_path):
    df = make_clean_df()
    output_path = tmp_path / "test_set.json"
    original = build_test_set(df, output_path)

    # A corrupted dataset must never regenerate the questions.
    corrupted = df.drop(index=[0, 1]).reset_index(drop=True)
    reused = load_or_build_test_set(corrupted, output_path, validate_documents=False)
    assert reused == original
    assert test_set_fingerprint(reused) == test_set_fingerprint(original)


def test_load_or_build_rebuilds_when_refresh_is_requested(tmp_path):
    df = make_clean_df(20)
    output_path = tmp_path / "test_set.json"
    original = build_test_set(df, output_path, seed=1)
    rebuilt = load_or_build_test_set(df, output_path, refresh=True, seed=2)
    assert test_set_fingerprint(rebuilt) != test_set_fingerprint(original)


# --- eligibility rules ------------------------------------------------------------------


def test_rows_with_blank_authors_get_no_authors_question(tmp_path):
    rows = [make_clean_row(index) for index in range(8)]
    rows[0]["authors_joined"] = "   "
    rows[1]["authors_joined"] = None
    blocked = {rows[0]["paper_id"], rows[1]["paper_id"]}
    samples, _ = build(tmp_path, pd.DataFrame(rows), questions_per_type=8)
    authors_docs = {
        sample["ground_truth_doc_ids"][0] for sample in samples if sample["question_type"] == "authors"
    }
    assert not (authors_docs & blocked)
    assert len(authors_docs) == 6


def test_rows_with_unparseable_date_get_no_date_question(tmp_path):
    rows = [make_clean_row(index) for index in range(8)]
    rows[0]["published"] = "not-a-date"
    rows[1]["published"] = ""
    blocked = {rows[0]["paper_id"], rows[1]["paper_id"]}
    samples, _ = build(tmp_path, pd.DataFrame(rows), questions_per_type=8)
    date_docs = {
        sample["ground_truth_doc_ids"][0] for sample in samples if sample["question_type"] == "date"
    }
    assert not (date_docs & blocked)


def test_rows_with_too_short_summary_get_no_summary_question(tmp_path):
    rows = [make_clean_row(index) for index in range(8)]
    rows[0]["summary"] = "Too short."
    blocked = rows[0]["paper_id"]
    samples, _ = build(tmp_path, pd.DataFrame(rows), questions_per_type=8)
    summary_docs = {
        sample["ground_truth_doc_ids"][0] for sample in samples if sample["question_type"] == "summary"
    }
    assert blocked not in summary_docs


def test_rows_with_blank_categories_get_no_categories_question(tmp_path):
    rows = [make_clean_row(index) for index in range(8)]
    rows[0]["categories_joined"] = float("nan")
    blocked = rows[0]["paper_id"]
    samples, _ = build(tmp_path, pd.DataFrame(rows), questions_per_type=8)
    category_docs = {
        sample["ground_truth_doc_ids"][0] for sample in samples if sample["question_type"] == "categories"
    }
    assert blocked not in category_docs


def test_rows_without_paper_id_are_never_referenced(tmp_path):
    rows = [make_clean_row(index) for index in range(8)]
    rows[0]["paper_id"] = None
    samples, _ = build(tmp_path, pd.DataFrame(rows), questions_per_type=8)
    for sample in samples:
        assert sample["ground_truth_doc_ids"] != [None]
        assert all(doc_id for doc_id in sample["ground_truth_doc_ids"])


# --- refusal cases ----------------------------------------------------------------------


def test_empty_dataframe_is_refused(tmp_path):
    with pytest.raises(TestSetValidationError, match="empty"):
        build_test_set(pd.DataFrame(), tmp_path / "test_set.json")


def test_missing_required_column_is_refused(tmp_path):
    df = make_clean_df().drop(columns=["authors_joined"])
    with pytest.raises(TestSetValidationError, match="authors_joined"):
        build_test_set(df, tmp_path / "test_set.json")


def test_too_few_documents_is_refused(tmp_path):
    with pytest.raises(TestSetValidationError, match="at least"):
        build_test_set(make_clean_df(3), tmp_path / "test_set.json")


def test_no_artifact_is_written_when_the_build_is_refused(tmp_path):
    output_path = tmp_path / "test_set.json"
    with pytest.raises(TestSetValidationError):
        build_test_set(make_clean_df(2), output_path)
    assert not output_path.exists()
    assert not metadata_path(output_path).exists()


# --- validator ---------------------------------------------------------------------------


@pytest.fixture
def valid_samples(tmp_path):
    samples, _ = build(tmp_path)
    return samples


def test_validator_accepts_a_generated_set(valid_samples, clean_df):
    validate_test_set(valid_samples, clean_df)


def test_validator_rejects_unknown_document_id(valid_samples, clean_df):
    broken = copy.deepcopy(valid_samples)
    broken[0]["ground_truth_doc_ids"] = ["10.9999/not-in-corpus"]
    with pytest.raises(TestSetValidationError, match="does not exist"):
        validate_test_set(broken, clean_df)


def test_validator_rejects_empty_ground_truth(valid_samples, clean_df):
    broken = copy.deepcopy(valid_samples)
    broken[0]["ground_truth"] = "   "
    with pytest.raises(TestSetValidationError, match="ground_truth"):
        validate_test_set(broken, clean_df)


def test_validator_rejects_empty_doc_id_list(valid_samples, clean_df):
    broken = copy.deepcopy(valid_samples)
    broken[0]["ground_truth_doc_ids"] = []
    with pytest.raises(TestSetValidationError, match="non-empty list"):
        validate_test_set(broken, clean_df)


def test_validator_rejects_duplicate_ids(valid_samples, clean_df):
    broken = copy.deepcopy(valid_samples)
    broken.append(copy.deepcopy(broken[0]))
    with pytest.raises(TestSetValidationError, match="duplicate id"):
        validate_test_set(broken, clean_df)


def test_validator_rejects_unknown_question_type(valid_samples, clean_df):
    broken = copy.deepcopy(valid_samples)
    broken[0]["question_type"] = "vibes"
    with pytest.raises(TestSetValidationError, match="question_type"):
        validate_test_set(broken, clean_df)


def test_validator_rejects_missing_field(valid_samples, clean_df):
    broken = copy.deepcopy(valid_samples)
    del broken[0]["question"]
    with pytest.raises(TestSetValidationError, match="missing required field"):
        validate_test_set(broken, clean_df)


def test_validator_rejects_extra_field(valid_samples, clean_df):
    broken = copy.deepcopy(valid_samples)
    broken[0]["notes"] = "should not be here"
    with pytest.raises(TestSetValidationError, match="unexpected field"):
        validate_test_set(broken, clean_df)


def test_validator_rejects_wording_that_routes_to_another_field(valid_samples, clean_df):
    broken = copy.deepcopy(valid_samples)
    summary_sample = next(s for s in broken if s["question_type"] == "summary")
    summary_sample["question"] = "Who authored this work?"
    with pytest.raises(TestSetValidationError, match="routes to"):
        validate_test_set(broken, clean_df)


def test_validator_rejects_empty_test_set(clean_df):
    with pytest.raises(TestSetValidationError, match="empty"):
        validate_test_set([], clean_df)


def test_validator_rejects_non_list_payload(clean_df):
    with pytest.raises(TestSetValidationError, match="JSON list"):
        validate_test_set({"samples": []}, clean_df)


def test_validator_without_dataframe_skips_document_existence(valid_samples):
    detached = copy.deepcopy(valid_samples)
    detached[0]["ground_truth_doc_ids"] = ["10.9999/dropped-by-corruption"]
    validate_test_set(detached, None)
