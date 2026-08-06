from __future__ import annotations

from core.config import load_settings
from core.utils import now_utc
from ingestion.cleaning import build_clean_dataframe, write_clean_artifacts
from ingestion.crossref import load_raw_records


def main() -> None:
    settings = load_settings()
    raw_path = settings.paths.raw_records_json
    if not raw_path.exists():
        raise FileNotFoundError(
            f"Missing {raw_path}. Source Ingestion Owner must create the raw snapshot first."
        )

    records = load_raw_records(raw_path)
    dataframe = build_clean_dataframe(records, run_date=now_utc())
    report_path = settings.paths.clean_json.parent / "cleaning_report.json"
    stats = write_clean_artifacts(
        dataframe,
        csv_path=settings.paths.clean_csv,
        json_path=settings.paths.clean_json,
        report_path=report_path,
    )
    print(f"Cleaned {stats['input_records']} raw records into {stats['output_records']} rows.")
    print(f"CSV: {settings.paths.clean_csv}")
    print(f"JSON: {settings.paths.clean_json}")
    print(f"Report: {report_path}")


if __name__ == "__main__":
    main()
