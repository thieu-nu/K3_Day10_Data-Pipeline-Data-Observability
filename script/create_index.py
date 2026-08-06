from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.config import load_settings
from retrieval.index import LocalEmbeddingIndex


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("Loading settings...")
    settings = load_settings()

    clean_csv_path = settings.paths.clean_csv
    print(f"Loading cleaned dataset from {clean_csv_path}...")
    df = pd.read_csv(clean_csv_path, keep_default_na=False)
    print(f"Loaded {len(df)} cleaned research paper records.")

    print(f"Building ChromaDB embedding vector index using model '{settings.embedding_model}'...")
    print(f" -> Persisting vector database to: {settings.paths.chroma_dir}")
    print(f" -> Saving metadata manifest to: {settings.paths.embeddings_json}")

    index = LocalEmbeddingIndex.build(df, settings)
    print(f"Index successfully created with {len(index.documents)} documents in collection '{index.collection_name}'!\n")

    # Run a quick demonstration semantic search
    sample_query = "hierarchical retrieval augmented generation framework tool selection"
    print(f"--- Running demo semantic search for: '{sample_query}' ---")
    results = index.search(query=sample_query, top_k=2)

    for rank, res in enumerate(results, start=1):
        print(f"#{rank} [Score: {res.score:.4f}] DOI: {res.paper_id}")
        print(f"    Title: {res.title}")
        print(f"    Snippet: {res.content[:150]}...\n")


if __name__ == "__main__":
    main()
