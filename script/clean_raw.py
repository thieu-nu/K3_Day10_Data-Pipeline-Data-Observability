from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.config import load_settings
from ingestion.cleaning import build_clean_dataframe, save_clean_data
from ingestion.crossref import load_raw_records


def main() -> None:
    print("Loading settings...")
    settings = load_settings()

    raw_path = settings.paths.raw_records_json
    print(f"Loading raw records from {raw_path}...")
    records = load_raw_records(raw_path)
    print(f"Loaded {len(records)} raw records.")

    run_date = datetime.now(UTC)
    print("Cleaning and transforming records (building clean dataframe)...")
    clean_df = build_clean_dataframe(records, run_date)

    stats = clean_df.attrs.get("cleaning_stats", {})
    print(f"Cleaning complete! Retained {len(clean_df)} / {len(records)} records.")
    print("Filter stats:", stats)

    print("Saving clean data and cleaning summary...")
    save_clean_data(clean_df, settings, raw_count=len(records))
    print(f" -> Clean CSV saved to: {settings.paths.clean_csv}")
    print(f" -> Clean JSON saved to: {settings.paths.clean_json}")
    print(f" -> Cleaning summary saved to: {settings.paths.cleaning_summary}")


if __name__ == "__main__":
    main()
