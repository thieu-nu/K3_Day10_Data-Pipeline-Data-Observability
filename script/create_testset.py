from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.config import load_settings
from evaluation.testset import build_test_set


def main() -> None:
    print("Loading settings...")
    settings = load_settings()

    clean_csv_path = settings.paths.clean_csv
    print(f"Loading cleaned dataset from {clean_csv_path}...")
    df = pd.read_csv(clean_csv_path, keep_default_na=False)
    print(f"Loaded {len(df)} cleaned records.")

    output_path = settings.paths.eval_testset
    print(f"Building evaluation test set and saving to {output_path}...")
    test_set = build_test_set(df, output_path)

    print(f"Successfully generated {len(test_set)} test questions across {len(set(item['question_type'] for item in test_set))} question types:")
    for q_type in sorted(set(item["question_type"] for item in test_set)):
        count = sum(1 for item in test_set if item["question_type"] == q_type)
        print(f"  - {q_type}: {count} questions")
    print(f"\n -> Evaluation set saved to: {output_path}")


if __name__ == "__main__":
    main()
