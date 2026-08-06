from __future__ import annotations

from pathlib import Path
import json

import pandas as pd
import pytest

from conftest import FAKE_KEY, SECRET_PREFIX, make_clean_df, make_clean_row
from core.config import load_settings
from observability.quality import (
    MAX_FUTURE_AGE_DAYS,
    REQUIRED_COLUMNS,
    _safe_report_stem,
    build_freshness_report,
    freshness_report_path,
    quality_report_path,
    run_data_quality_checks,
)

@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", FAKE_KEY)
    return load_settings(project_dir=tmp_path)


def check_by_name(payload, name):
    return next(check for check in payload["checks"] if check["check_name"] == name)


def status_of(payload, name):
    return check_by_name(payload, name)["status"]


def rows(count=6, **overrides):
    return [make_clean_row(index, **overrides) for index in range(count)]


# --- happy path ------------------------------------------------------------------------


def test_valid_dataset_passes_the_core_checks(settings, clean_df):
    payload = run_data_quality_checks(clean_df, settings, "baseline_quality")
    assert payload["summary"]["overall_status"] == "pass"
    assert payload["summary"]["failed"] == 0
    assert payload["summary"]["warned"] == 0
    assert payload["dataset_rows"] == len(clean_df)
    assert payload["report_name"] == "baseline_quality"
    assert payload["schema_version"]


def test_every_check_carries_the_full_schema(settings, clean_df):
    payload = run_data_quality_checks(clean_df, settings, "baseline_quality")
    expected = {
        "check_name",
        "quality_dimension",
        "status",
        "observed_value",
        "expected_condition",
        "affected_count",
        "total_count",
        "message",
    }
    assert payload["checks"]
    for check in payload["checks"]:
        assert set(check) == expected
        assert check["status"] in {"pass", "fail", "warning"}
        assert check["quality_dimension"] in {
            "completeness",
            "uniqueness",
            "validity",
            "freshness",
        }


def test_summary_counts_match_the_check_list(settings, clean_df):
    payload = run_data_quality_checks(clean_df, settings, "baseline_quality")
    summary = payload["summary"]
    assert summary["total"] == len(payload["checks"])
    assert summary["passed"] + summary["failed"] + summary["warned"] == summary["total"]


# --- failure detection -------------------------------------------------------------------


def test_empty_dataset_fails_overall(settings):
    payload = run_data_quality_checks(pd.DataFrame(), settings, "empty_quality")
    assert payload["summary"]["overall_status"] == "fail"
    assert status_of(payload, "dataset_not_empty") == "fail"
    assert payload["dataset_rows"] == 0


def test_missing_required_column_is_reported_not_raised(settings):
    df = make_clean_df().drop(columns=["text_for_embedding", "age_days"])
    payload = run_data_quality_checks(df, settings, "missing_columns")
    check = check_by_name(payload, "required_columns_present")
    assert check["status"] == "fail"
    assert check["observed_value"] == ["age_days", "text_for_embedding"]
    assert check["affected_count"] == 2
    assert check["total_count"] == len(REQUIRED_COLUMNS)
    assert status_of(payload, "text_for_embedding_present") == "fail"
    assert status_of(payload, "age_days_numeric") == "fail"


def test_null_paper_id_is_detected(settings):
    data = rows()
    data[0]["paper_id"] = None
    payload = run_data_quality_checks(pd.DataFrame(data), settings, "q")
    check = check_by_name(payload, "paper_id_not_null")
    assert check["status"] == "fail"
    assert check["affected_count"] == 1
    assert check["observed_value"] == pytest.approx(1 / 6, rel=1e-4)


def test_blank_paper_id_is_detected_separately_from_null(settings):
    data = rows()
    data[0]["paper_id"] = "   "
    payload = run_data_quality_checks(pd.DataFrame(data), settings, "q")
    assert status_of(payload, "paper_id_not_null") == "pass"
    blank = check_by_name(payload, "paper_id_not_blank")
    assert blank["status"] == "fail"
    assert blank["affected_count"] == 1


def test_duplicate_paper_id_is_detected(settings):
    data = rows()
    data[1]["paper_id"] = data[0]["paper_id"]
    payload = run_data_quality_checks(pd.DataFrame(data), settings, "q")
    check = check_by_name(payload, "paper_id_unique")
    assert check["status"] == "fail"
    assert check["affected_count"] == 1
    assert check["observed_value"] == 1


def test_blank_text_for_embedding_is_detected(settings):
    data = rows()
    data[0]["text_for_embedding"] = "   "
    data[1]["text_for_embedding"] = None
    payload = run_data_quality_checks(pd.DataFrame(data), settings, "q")
    check = check_by_name(payload, "text_for_embedding_present")
    assert check["status"] == "fail"
    assert check["affected_count"] == 2


def test_missing_title_is_detected(settings):
    data = rows()
    data[0]["title"] = ""
    payload = run_data_quality_checks(pd.DataFrame(data), settings, "q")
    assert status_of(payload, "title_present") == "fail"


def test_missing_summary_warns_below_threshold_and_fails_above(settings):
    few = rows(20)
    few[0]["summary"] = ""
    warned = run_data_quality_checks(pd.DataFrame(few), settings, "q")
    assert status_of(warned, "summary_present") == "warning"

    many = rows(20)
    for row in many[:6]:
        row["summary"] = ""
    failed = run_data_quality_checks(pd.DataFrame(many), settings, "q")
    check = check_by_name(failed, "summary_present")
    assert check["status"] == "fail"
    assert check["affected_count"] == 6
    assert check["observed_value"] == pytest.approx(0.3)


def test_missing_authors_and_categories_are_detected(settings):
    data = rows()
    data[0]["authors_joined"] = None
    data[1]["categories_joined"] = "  "
    payload = run_data_quality_checks(pd.DataFrame(data), settings, "q")
    assert check_by_name(payload, "authors_joined_present")["affected_count"] == 1
    assert check_by_name(payload, "categories_joined_present")["affected_count"] == 1
    assert status_of(payload, "authors_joined_present") == "warning"


def test_invalid_published_date_is_detected(settings):
    data = rows()
    data[0]["published"] = "not-a-date"
    data[1]["published"] = ""
    payload = run_data_quality_checks(pd.DataFrame(data), settings, "q")
    check = check_by_name(payload, "published_parseable")
    assert check["status"] == "fail"
    assert check["affected_count"] == 2


def test_non_numeric_age_days_is_detected(settings):
    data = rows()
    data[0]["age_days"] = "quite old"
    payload = run_data_quality_checks(pd.DataFrame(data), settings, "q")
    check = check_by_name(payload, "age_days_numeric")
    assert check["status"] == "fail"
    assert check["affected_count"] == 1


def test_negative_age_days_is_detected(settings):
    data = rows()
    data[0]["age_days"] = -30
    payload = run_data_quality_checks(pd.DataFrame(data), settings, "q")
    check = check_by_name(payload, "age_days_not_negative")
    assert check["status"] == "fail"
    assert check["affected_count"] == 1


def test_small_negative_age_days_is_tolerated(settings):
    data = rows()
    data[0]["age_days"] = -MAX_FUTURE_AGE_DAYS
    payload = run_data_quality_checks(pd.DataFrame(data), settings, "q")
    assert status_of(payload, "age_days_not_negative") == "pass"


def test_duplicate_rows_are_detected(settings):
    data = rows()
    data.append(dict(data[0]))
    payload = run_data_quality_checks(pd.DataFrame(data), settings, "q")
    check = check_by_name(payload, "duplicate_rows")
    assert check["status"] == "fail"
    assert check["affected_count"] == 1


def test_invalid_urls_are_detected(settings):
    data = rows()
    data[0]["abs_url"] = "not a url"
    data[1]["pdf_url"] = ""
    payload = run_data_quality_checks(pd.DataFrame(data), settings, "q")
    assert check_by_name(payload, "abs_url_valid")["affected_count"] == 1
    assert check_by_name(payload, "pdf_url_valid")["affected_count"] == 1


def test_stale_rows_raise_the_freshness_check(settings):
    data = rows()
    for row in data[:2]:
        row["age_days"] = settings.freshness_threshold_days + 400
    payload = run_data_quality_checks(pd.DataFrame(data), settings, "q")
    check = check_by_name(payload, "data_within_freshness_threshold")
    assert check["affected_count"] == 2
    assert check["status"] in {"warning", "fail"}


# --- purity and artifacts ------------------------------------------------------------------


def test_quality_checks_do_not_mutate_the_input(settings):
    df = make_clean_df()
    before = df.copy(deep=True)
    run_data_quality_checks(df, settings, "q")
    pd.testing.assert_frame_equal(df, before)


def test_quality_artifact_reloads_as_json(settings, clean_df):
    payload = run_data_quality_checks(clean_df, settings, "baseline_quality")
    path = Path(payload["report_path"])
    assert path.exists()
    assert json.loads(path.read_text(encoding="utf-8")) == payload


def test_three_quality_reports_do_not_overwrite_each_other(settings, clean_df):
    baseline = run_data_quality_checks(clean_df, settings, "baseline_quality")
    corrupted = run_data_quality_checks(clean_df.head(3), settings, "corrupted_quality")
    repaired = run_data_quality_checks(clean_df, settings, "repaired_quality")

    paths = {p["report_path"] for p in (baseline, corrupted, repaired)}
    assert len(paths) == 3
    for path in paths:
        assert Path(path).exists()
    assert json.loads(Path(corrupted["report_path"]).read_text(encoding="utf-8"))["dataset_rows"] == 3
    assert json.loads(Path(baseline["report_path"]).read_text(encoding="utf-8"))["dataset_rows"] == len(clean_df)


def test_report_name_cannot_escape_the_quality_directory(settings, clean_df):
    quality_dir = settings.paths.quality_dir.resolve()
    for hostile in ("../../secrets", "..\\..\\secrets", "/etc/passwd", "sub/dir/report.json"):
        payload = run_data_quality_checks(clean_df, settings, hostile)
        resolved = Path(payload["report_path"]).resolve()
        assert resolved.parent == quality_dir, hostile
        assert resolved.exists()


def test_report_name_without_usable_characters_is_rejected(settings, clean_df):
    with pytest.raises(ValueError, match="usable file name"):
        run_data_quality_checks(clean_df, settings, "../..")


def test_safe_stem_strips_directories_and_extension():
    assert _safe_report_stem("baseline_quality") == "baseline_quality"
    assert _safe_report_stem("baseline_quality.json") == "baseline_quality"
    assert _safe_report_stem("../../etc/passwd") == "passwd"


def test_quality_artifact_contains_no_secret(settings, clean_df):
    payload = run_data_quality_checks(clean_df, settings, "baseline_quality")
    blob = Path(payload["report_path"]).read_text(encoding="utf-8")
    assert FAKE_KEY not in blob
    assert "OPENROUTER_API_KEY" not in blob
    assert SECRET_PREFIX not in blob


# --- freshness -------------------------------------------------------------------------------


def test_fresh_dataset_is_recognised(settings, tmp_path):
    df = make_clean_df()
    report = build_freshness_report(df, settings, tmp_path / "baseline_freshness.json")
    assert report["status"] == "fresh"
    assert report["stale_rows"] == 0
    assert report["invalid_or_missing_date_rows"] == 0
    assert report["threshold_days"] == settings.freshness_threshold_days
    assert report["latest_published"] >= report["oldest_published"]
    assert report["min_age_days"] <= report["mean_age_days"] <= report["max_age_days"]
    assert report["measured_from"] == ["published", "age_days"]


def test_stale_rows_are_detected(settings, tmp_path):
    data = rows()
    data[0]["age_days"] = settings.freshness_threshold_days + 900
    report = build_freshness_report(pd.DataFrame(data), settings, tmp_path / "f.json")
    assert report["status"] == "stale"
    assert report["stale_rows"] == 1
    assert report["stale_row_rate"] == pytest.approx(1 / 6, rel=1e-4)
    assert "exceed the" in report["reason"]


def test_empty_dataset_is_unknown_not_fresh(settings, tmp_path):
    report = build_freshness_report(pd.DataFrame(), settings, tmp_path / "f.json")
    assert report["status"] == "unknown"
    assert report["row_count"] == 0
    assert "empty" in report["reason"].lower()


def test_all_dates_missing_is_unknown(settings, tmp_path):
    data = rows()
    for row in data:
        row["published"] = None
        row["age_days"] = None
    report = build_freshness_report(pd.DataFrame(data), settings, tmp_path / "f.json")
    assert report["status"] == "unknown"
    assert report["latest_published"] is None
    assert report["max_age_days"] is None


def test_missing_columns_give_unknown(settings, tmp_path):
    df = make_clean_df().drop(columns=["age_days"])
    report = build_freshness_report(df, settings, tmp_path / "f.json")
    assert report["status"] == "unknown"
    assert "age_days" in report["reason"]


def test_partially_missing_dates_are_never_fresh(settings, tmp_path):
    data = rows()
    data[0]["published"] = None
    report = build_freshness_report(pd.DataFrame(data), settings, tmp_path / "f.json")
    assert report["status"] == "stale"
    assert report["invalid_or_missing_date_rows"] == 1
    assert "no usable `published` date" in report["reason"]


def test_unusable_age_alone_is_never_fresh(settings, tmp_path):
    data = rows()
    data[0]["age_days"] = "unknown"
    report = build_freshness_report(pd.DataFrame(data), settings, tmp_path / "f.json")
    assert report["status"] == "stale"
    assert report["invalid_or_missing_age_rows"] == 1


def test_future_dated_rows_are_counted(settings, tmp_path):
    data = rows()
    data[0]["age_days"] = -50
    report = build_freshness_report(pd.DataFrame(data), settings, tmp_path / "f.json")
    assert report["future_dated_rows"] == 1
    assert report["min_age_days"] == -50


def test_freshness_does_not_mutate_the_input(settings, tmp_path):
    df = make_clean_df()
    before = df.copy(deep=True)
    build_freshness_report(df, settings, tmp_path / "f.json")
    pd.testing.assert_frame_equal(df, before)


def test_freshness_artifact_reloads_as_json(settings, tmp_path):
    path = tmp_path / "nested" / "baseline_freshness.json"
    report = build_freshness_report(make_clean_df(), settings, path)
    assert json.loads(path.read_text(encoding="utf-8")) == report


def test_three_freshness_reports_do_not_overwrite_each_other(settings):
    baseline_path = freshness_report_path(settings, "baseline_freshness")
    corrupted_path = freshness_report_path(settings, "corrupted_freshness")
    repaired_path = freshness_report_path(settings, "repaired_freshness")
    assert len({baseline_path, corrupted_path, repaired_path}) == 3

    stale = rows()
    for row in stale:
        row["age_days"] = settings.freshness_threshold_days + 500

    build_freshness_report(make_clean_df(), settings, baseline_path)
    build_freshness_report(pd.DataFrame(stale), settings, corrupted_path)
    build_freshness_report(make_clean_df(), settings, repaired_path)

    assert json.loads(baseline_path.read_text(encoding="utf-8"))["status"] == "fresh"
    assert json.loads(corrupted_path.read_text(encoding="utf-8"))["status"] == "stale"
    assert json.loads(repaired_path.read_text(encoding="utf-8"))["status"] == "fresh"


def test_freshness_and_quality_paths_stay_inside_the_quality_directory(settings):
    quality_dir = settings.paths.quality_dir.resolve()
    assert freshness_report_path(settings, "../../x").resolve().parent == quality_dir
    assert quality_report_path(settings, "../../x").resolve().parent == quality_dir


def test_freshness_artifact_contains_no_secret(settings, tmp_path):
    path = tmp_path / "f.json"
    build_freshness_report(make_clean_df(), settings, path)
    blob = path.read_text(encoding="utf-8")
    assert FAKE_KEY not in blob
    assert SECRET_PREFIX not in blob


def test_corruption_style_stale_dates_flip_the_status(settings, tmp_path):
    """The scenario the corruption flow relies on: aged-out rows must show up here."""
    fresh_df = make_clean_df()
    before = build_freshness_report(fresh_df, settings, tmp_path / "before.json")

    corrupted = fresh_df.copy()
    corrupted.loc[: len(corrupted) // 2, "age_days"] = settings.freshness_threshold_days + 1200
    corrupted.loc[: len(corrupted) // 2, "published"] = "2011-03-04"
    after = build_freshness_report(corrupted, settings, tmp_path / "after.json")

    assert before["status"] == "fresh"
    assert after["status"] == "stale"
    assert after["stale_rows"] > 0
    assert after["max_age_days"] > before["max_age_days"]
    assert after["oldest_published"] < before["oldest_published"]
