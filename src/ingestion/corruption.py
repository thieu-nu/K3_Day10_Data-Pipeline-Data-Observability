from __future__ import annotations

from pathlib import Path
import pandas as pd

from core.utils import write_json


def corrupt_clean_dataframe(df: pd.DataFrame, output_log_path: Path | str) -> pd.DataFrame:
    """Simulate nhiều dạng data corruption trên clean dataset."""
    if df.empty:
        write_json(Path(output_log_path), {"status": "empty_dataframe_corrupted"})
        return df.copy()

    corrupted = df.copy().reset_index(drop=True)
    total_rows = len(corrupted)

    # 1. Drop một số latest records (e.g. Drop 2 newest records if rows >= 5)
    dropped_count = 0
    if total_rows >= 5 and "published" in corrupted:
        newest_indices = corrupted.sort_values(by="published", ascending=False).head(2).index
        corrupted = corrupted.drop(index=newest_indices).reset_index(drop=True)
        dropped_count = len(newest_indices)
        total_rows = len(corrupted)

    # 2. Blank summary ở một số dòng (e.g., first 2 rows)
    blanked_indices = []
    if total_rows >= 2 and "summary" in corrupted:
        corrupted.loc[0, "summary"] = ""
        corrupted.loc[1, "summary"] = ""
        blanked_indices = [0, 1]

    # 3. Inject noise vào text ở một số dòng (e.g. row 2)
    noise_indices = []
    if total_rows >= 3 and "summary" in corrupted:
        corrupted.loc[2, "summary"] = "[CORRUPTED NOISE %%%] " + str(corrupted.loc[2, "summary"])
        noise_indices = [2]

    # 4. Làm title bị truncate (e.g., row 3)
    truncated_indices = []
    if total_rows >= 4 and "title" in corrupted:
        orig_title = str(corrupted.loc[3, "title"])
        corrupted.loc[3, "title"] = orig_title[:8] + "..."
        truncated_indices = [3]

    # 5. Làm published date cũ đi và tăng age_days (>500 days)
    staled_indices = []
    if total_rows >= 3 and "age_days" in corrupted:
        corrupted.loc[1:2, "published"] = "2020-01-01"
        corrupted.loc[1:2, "age_days"] = 2300
        staled_indices = [1, 2]

    # 6. Add duplicate rows (duplicate first row)
    duplicate_added = 0
    if total_rows >= 1:
        dup_row = corrupted.iloc[[0]].copy()
        corrupted = pd.concat([corrupted, dup_row], ignore_index=True)
        duplicate_added = 1

    # 7. Rebuild `text_for_embedding`
    if "text_for_embedding" in corrupted:
        for i in range(len(corrupted)):
            t = str(corrupted.loc[i, "title"] if "title" in corrupted else "")
            s = str(corrupted.loc[i, "summary"] if "summary" in corrupted else "")
            corrupted.loc[i, "text_for_embedding"] = f"Title: {t} | Summary: {s}"

    # 8. Ghi corruption log vào output_log_path
    log_payload = {
        "original_row_count": len(df),
        "corrupted_row_count": len(corrupted),
        "dropped_latest_records": dropped_count,
        "blanked_summary_rows": blanked_indices,
        "noise_injected_rows": noise_indices,
        "truncated_title_rows": truncated_indices,
        "staled_date_rows": staled_indices,
        "duplicate_rows_added": duplicate_added,
        "status": "corrupted",
    }

    write_json(Path(output_log_path), log_payload)
    return corrupted

