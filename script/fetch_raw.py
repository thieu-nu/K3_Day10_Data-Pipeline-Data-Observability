from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.config import load_settings
from ingestion.crossref import fetch_source_records


def main() -> None:
    print("Loading settings...")
    settings = load_settings()
    print(f"Fetching raw data from Crossref API (query='{settings.source_query}')...")
    records = fetch_source_records(settings)
    print(f"Successfully loaded and parsed {len(records)} records!")
    print(f" -> Raw API response saved to: {settings.paths.raw_api_response}")
    print(f" -> Raw records saved to: {settings.paths.raw_records_json}")


if __name__ == "__main__":
    main()
