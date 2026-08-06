from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from core.utils import write_json


def build_test_set(df: pd.DataFrame, output_path: Path | str) -> list[dict[str, Any]]:
    """Tạo bộ evaluation set từ cleaned dataframe."""
    if df.empty:
        raise ValueError("Cannot build test set from an empty DataFrame")

    sample_df = df.head(min(5, len(df)))
    test_set: list[dict[str, Any]] = []

    for _, row in sample_df.iterrows():
        paper_id = str(row.get("paper_id", ""))
        title = str(row.get("title", ""))
        summary = str(row.get("summary", ""))
        authors = str(row.get("authors_joined") or "unspecified")
        published = str(row.get("published") or "unspecified")
        categories = str(row.get("categories_joined") or row.get("primary_category") or "unspecified")

        doc_ids = [paper_id]

        # 1. Summary question
        test_set.append({
            "question_type": "summary",
            "question": f"What is the main summary or abstract of the paper titled '{title}'?",
            "ground_truth": summary,
            "ground_truth_doc_ids": doc_ids,
        })

        # 2. Authors question
        test_set.append({
            "question_type": "authors",
            "question": f"Who are the authors of the paper titled '{title}'?",
            "ground_truth": f"The authors are {authors}.",
            "ground_truth_doc_ids": doc_ids,
        })

        # 3. Date question
        test_set.append({
            "question_type": "date",
            "question": f"When was the paper titled '{title}' published?",
            "ground_truth": f"It was published on {published}.",
            "ground_truth_doc_ids": doc_ids,
        })

        # 4. Categories question
        test_set.append({
            "question_type": "categories",
            "question": f"What are the research categories or subjects for the paper titled '{title}'?",
            "ground_truth": f"The research categories are {categories}.",
            "ground_truth_doc_ids": doc_ids,
        })

    # Add incremental IDs and reorder keys
    for idx, item in enumerate(test_set):
        test_set[idx] = {
            "id": f"test_{idx+1}",
            "question_type": item["question_type"],
            "question": item["question"],
            "ground_truth": item["ground_truth"],
            "ground_truth_doc_ids": item["ground_truth_doc_ids"],
        }

    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    write_json(out_file, test_set)

    return test_set

