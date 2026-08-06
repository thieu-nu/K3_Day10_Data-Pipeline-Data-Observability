from __future__ import annotations

import json

import pandas as pd
import pytest

from conftest import make_clean_df
from ingestion.corruption import (
    BLANK_SUMMARY_ROWS,
    DROP_LATEST_ROWS,
    DUPLICATE_ROWS,
    STALE_SHIFT_DAYS,
    TRUNCATED_TITLE_CHARS,
    corrupt_clean_dataframe,
)


@pytest.fixture
def corrupted(tmp_path):
    df = make_clean_df(24)
    log_path = tmp_path / "corruption_log.json"
    out = corrupt_clean_dataframe(df, log_path)
    log = json.loads(log_path.read_text(encoding="utf-8"))
    return df, out, log, log_path


def events_of(log, corruption_type):
    return [event for event in log["events"] if event["corruption_type"] == corruption_type]


def row_for(df, paper_id):
    return df[df["paper_id"] == paper_id].iloc[0]


# --- contract --------------------------------------------------------------------------


def test_input_dataframe_is_not_mutated(tmp_path):
    df = make_clean_df(24)
    before = df.copy(deep=True)
    corrupt_clean_dataframe(df, tmp_path / "log.json")
    pd.testing.assert_frame_equal(df, before)


def test_columns_are_preserved(corrupted):
    df, out, _, _ = corrupted
    assert list(out.columns) == list(df.columns)


def test_empty_input_is_refused(tmp_path):
    with pytest.raises(ValueError, match="empty"):
        corrupt_clean_dataframe(pd.DataFrame(), tmp_path / "log.json")


def test_corruption_is_deterministic(tmp_path):
    first = corrupt_clean_dataframe(make_clean_df(24), tmp_path / "a.json")
    second = corrupt_clean_dataframe(make_clean_df(24), tmp_path / "b.json")
    pd.testing.assert_frame_equal(first.reset_index(drop=True), second.reset_index(drop=True))
    assert json.loads((tmp_path / "a.json").read_text())["events"] == json.loads(
        (tmp_path / "b.json").read_text()
    )["events"]


# --- scenarios -------------------------------------------------------------------------


def test_latest_records_are_dropped(corrupted):
    df, out, log, _ = corrupted
    dropped = {event["paper_id"] for event in events_of(log, "drop_latest_records")}
    assert len(dropped) == DROP_LATEST_ROWS
    assert dropped == set(df["paper_id"].head(DROP_LATEST_ROWS))
    assert not (set(out["paper_id"]) & dropped)


def test_summaries_are_blanked(corrupted):
    _, out, log, _ = corrupted
    for event in events_of(log, "blank_summary"):
        row = row_for(out, event["paper_id"])
        assert row["summary"] == ""
        assert row["summary_chars"] == 0


def test_noise_is_injected_into_summaries(corrupted):
    df, out, log, _ = corrupted
    for event in events_of(log, "inject_noise"):
        before = row_for(df, event["paper_id"])
        after = row_for(out, event["paper_id"])
        assert after["summary"] != before["summary"]
        assert len(after["summary"]) > len(before["summary"])


def test_titles_are_truncated(corrupted):
    df, out, log, _ = corrupted
    for event in events_of(log, "truncate_title"):
        before = row_for(df, event["paper_id"])
        after = row_for(out, event["paper_id"])
        assert len(after["title"]) <= TRUNCATED_TITLE_CHARS
        assert before["title"].startswith(after["title"])


def test_published_dates_are_pushed_back(corrupted):
    df, out, log, _ = corrupted
    for event in events_of(log, "stale_published"):
        before = row_for(df, event["paper_id"])
        after = row_for(out, event["paper_id"])
        assert after["age_days"] == before["age_days"] + STALE_SHIFT_DAYS
        assert pd.to_datetime(after["published"]) < pd.to_datetime(before["published"])


def test_rows_are_duplicated(corrupted):
    _, out, log, _ = corrupted
    duplicated = [event["paper_id"] for event in events_of(log, "duplicate_row")]
    assert len(duplicated) == DUPLICATE_ROWS
    for paper_id in duplicated:
        assert (out["paper_id"] == paper_id).sum() == 2
    assert int(out.duplicated().sum()) == DUPLICATE_ROWS


def test_row_count_reflects_drops_and_duplicates(corrupted):
    df, out, log, _ = corrupted
    assert len(out) == len(df) - DROP_LATEST_ROWS + DUPLICATE_ROWS
    assert log["input_rows"] == len(df)
    assert log["output_rows"] == len(out)


def test_derived_columns_stay_consistent(corrupted):
    """text_for_embedding must follow the title/summary the corruption left behind."""
    _, out, log, _ = corrupted
    touched = {
        event["paper_id"]
        for event in log["events"]
        if event["corruption_type"] in {"blank_summary", "inject_noise", "truncate_title"}
    }
    for paper_id in touched:
        row = out[out["paper_id"] == paper_id].iloc[0]
        assert row["text_for_embedding"] == (
            f"Title: {row['title']} | Authors: {row['authors_joined']} | Summary: {row['summary']}"
        )
        assert row["summary_chars"] == len(row["summary"])


def test_scenarios_touch_disjoint_rows(corrupted):
    """One row is never blanked and noised at once, so each signal stays attributable."""
    _, _, log, _ = corrupted
    exclusive = ("blank_summary", "inject_noise", "truncate_title", "stale_published")
    seen: set[str] = set()
    for name in exclusive:
        ids = {event["paper_id"] for event in events_of(log, name)}
        assert not (ids & seen), f"{name} overlaps an earlier scenario"
        seen |= ids


# --- log -------------------------------------------------------------------------------


def test_log_records_every_affected_paper_id(corrupted):
    _, _, log, _ = corrupted
    assert log["affected_paper_ids"]
    assert set(log["affected_paper_ids"]) == {event["paper_id"] for event in log["events"]}


def test_log_counts_match_the_events(corrupted):
    _, _, log, _ = corrupted
    for name, count in log["scenario_counts"].items():
        assert count == len(events_of(log, name))
    assert sum(log["scenario_counts"].values()) == len(log["events"])


def test_log_is_readable_by_the_report_linker(corrupted):
    """The comparison report walks the log for dicts carrying a paper_id."""
    from observability.reporting import _corruption_index

    _, _, log, _ = corrupted
    index = _corruption_index(log)
    assert index
    for paper_id, records in index.items():
        assert paper_id in log["affected_paper_ids"]
        assert all("corruption_type" in record for record in records)


def test_log_reloads_as_json(corrupted):
    _, _, log, log_path = corrupted
    assert json.loads(log_path.read_text(encoding="utf-8")) == log
    assert log["seed"]
    assert log["generated_at"]


# --- downstream signals ------------------------------------------------------------------


def test_quality_checks_detect_the_corruption(corrupted, tmp_path, monkeypatch):
    from core.config import load_settings
    from observability.quality import run_data_quality_checks

    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    settings = load_settings(project_dir=tmp_path / "proj")
    df, out, _, _ = corrupted

    before = run_data_quality_checks(df, settings, "clean_quality")
    after = run_data_quality_checks(out, settings, "corrupted_quality")

    assert before["summary"]["overall_status"] == "pass"
    assert after["summary"]["overall_status"] == "fail"

    by_name = {check["check_name"]: check for check in after["checks"]}
    assert by_name["paper_id_unique"]["status"] == "fail"
    assert by_name["duplicate_rows"]["status"] == "fail"
    assert by_name["summary_present"]["affected_count"] == BLANK_SUMMARY_ROWS


def test_freshness_turns_stale(corrupted, tmp_path, monkeypatch):
    from core.config import load_settings
    from observability.quality import build_freshness_report

    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    settings = load_settings(project_dir=tmp_path / "proj")
    df, out, _, _ = corrupted

    before = build_freshness_report(df, settings, tmp_path / "before.json")
    after = build_freshness_report(out, settings, tmp_path / "after.json")

    assert before["status"] == "fresh"
    assert after["status"] == "stale"
    assert after["stale_rows"] > 0
    assert after["max_age_days"] > before["max_age_days"]
