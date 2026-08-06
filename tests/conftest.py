from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd
import pytest

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


# Credential-shaped strings for the redaction tests. They are assembled at import time on
# purpose: no literal that looks like a real key is ever stored in the repository, so secret
# scanners have nothing to flag and the "never put a key in a fixture" rule holds even for
# obviously fake values. None of these is a real credential.
SECRET_PREFIX = "sk-" + "or-v1-"
FAKE_KEY = SECRET_PREFIX + "abcdef0123456789abcdef0123456789"


def fake_key(suffix: str) -> str:
    """Build another throwaway key-shaped string with the same prefix."""
    return SECRET_PREFIX + suffix


def make_clean_row(index: int, **overrides) -> dict:
    """One row shaped like the cleaned dataset contract that retrieval.index consumes."""
    row = {
        "paper_id": f"10.1234/paper.{index:03d}",
        "title": f"Retrieval Augmented Generation Study Number {index}",
        "summary": (
            f"This paper studies retrieval augmented generation for topic {index}. "
            "It reports experiments on a scholarly corpus and discusses limitations."
        ),
        "authors_joined": f"Author {index} A, Author {index} B",
        "categories_joined": "Computer Science, Information Retrieval",
        "primary_category": "Computer Science",
        "published": f"2025-0{(index % 9) + 1}-15",
        "updated": f"2025-0{(index % 9) + 1}-20",
        "age_days": 30 + index,
        "abs_url": f"https://doi.org/10.1234/paper.{index:03d}",
        "pdf_url": f"https://example.org/pdf/{index:03d}.pdf",
        "summary_chars": 120,
        "text_for_embedding": (
            f"Retrieval Augmented Generation Study Number {index}. "
            f"This paper studies retrieval augmented generation for topic {index}."
        ),
    }
    row.update(overrides)
    return row


def make_clean_df(count: int = 8, **overrides) -> pd.DataFrame:
    return pd.DataFrame([make_clean_row(index, **overrides) for index in range(count)])


@pytest.fixture
def clean_df() -> pd.DataFrame:
    return make_clean_df()


# --- doubles for the retrieval and judge collaborators ------------------------------------


class FakeSearchResult:
    """Shaped like retrieval.index.SearchResult."""

    def __init__(self, paper_id: str, title: str, content: str, score: float = 0.9):
        self.paper_id = paper_id
        self.title = title
        self.content = content
        self.score = score
        self.metadata = {"paper_id": paper_id, "title": title}


class FakeAnswerResult:
    """Shaped like retrieval.qa.AnswerResult."""

    def __init__(self, question: str, answer: str, retrieved_doc_ids: list[str]):
        self.question = question
        self.answer = answer
        self.retrieved_doc_ids = list(retrieved_doc_ids)
        self.retrieved_contexts = [f"context for {doc_id}" for doc_id in retrieved_doc_ids]
        self.retrieved_titles = [f"title for {doc_id}" for doc_id in retrieved_doc_ids]


class FakeIndex:
    """Stands in for LocalEmbeddingIndex: exposes lookup(), documents and collection_name.

    `lookup_hits` maps the text inside a question's single quotes to a paper_id, mirroring
    what LocalEmbeddingIndex.lookup would resolve for a title or paper_id.
    """

    def __init__(self, documents=None, lookup_hits=None, collection_name="papers-test"):
        self.documents = documents if documents is not None else [{"paper_id": "10.1234/paper.000"}]
        self.lookup_hits = lookup_hits or {}
        self.collection_name = collection_name
        self.lookup_calls: list[str] = []

    def lookup(self, value: str):
        self.lookup_calls.append(value)
        paper_id = self.lookup_hits.get(value.strip().lower())
        if paper_id is None:
            return None
        return {"paper_id": paper_id, "title": value, "content": "", "metadata": {}}


class FakeLLM:
    """Minimal chat-model double: replies come from a scripted list, exceptions are raised."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.prompts: list[str] = []

    def invoke(self, prompt):
        self.prompts.append(prompt)
        reply = self.replies.pop(0) if self.replies else self.replies_exhausted()
        if isinstance(reply, BaseException):
            raise reply
        return FakeMessage(reply)

    def replies_exhausted(self):
        raise AssertionError("FakeLLM ran out of scripted replies")


class FakeMessage:
    def __init__(self, content):
        self.content = content


def always_replies(content, times: int = 200):
    return [content] * times


def always_raises(exc_factory, times: int = 200):
    return [exc_factory() for _ in range(times)]
