from __future__ import annotations

from pathlib import Path
from typing import Any
import re

import pandas as pd

from core.config import Settings
from core.utils import is_blank, now_utc, write_json

CLEAN_SCHEMA_VERSION = "clean-v1"

# Columns the downstream pipeline genuinely cannot run without: the first nine are read
# directly by retrieval.index._build_documents, and age_days carries the freshness signal.
REQUIRED_COLUMNS = (
    "paper_id",
    "title",
    "summary",
    "text_for_embedding",
    "published",
    "authors_joined",
    "categories_joined",
    "abs_url",
    "pdf_url",
    "age_days",
)
OPTIONAL_URL_COLUMNS = ("abs_url", "pdf_url")

STATUS_PASS = "pass"
STATUS_WARNING = "warning"
STATUS_FAIL = "fail"

DIMENSION_COMPLETENESS = "completeness"
DIMENSION_UNIQUENESS = "uniqueness"
DIMENSION_VALIDITY = "validity"
DIMENSION_FRESHNESS = "freshness"

# Central thresholds. Freshness comes from settings; the rest are quality policy defined here
# because the starter config has no field for them.
#   (column, warn_above_rate, fail_above_rate)
FIELD_COMPLETENESS_RULES = (
    ("title", 0.0, 0.0),
    ("summary", 0.0, 0.10),
    ("text_for_embedding", 0.0, 0.0),
    ("authors_joined", 0.0, 0.20),
    ("categories_joined", 0.0, 0.20),
)
URL_INVALID_WARN_RATE = 0.0
URL_INVALID_FAIL_RATE = 0.50
STALE_ROW_WARN_RATE = 0.0
STALE_ROW_FAIL_RATE = 0.50
# A published date in the future yields a negative age; a day of clock/timezone slack is
# tolerated, anything beyond that is a data error.
MAX_FUTURE_AGE_DAYS = 1

_URL_PATTERN = re.compile(r"^https?://\S+$", re.IGNORECASE)


# --- artifact paths ----------------------------------------------------------------------


def _safe_report_stem(report_name: str) -> str:
    """Reduce a caller-supplied report name to a bare, safe file stem.

    Any directory component is dropped, so a name like `../../secrets` can only ever write
    inside the configured quality directory.
    """
    name = Path(str(report_name)).name
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name)
    name = name.strip("._-")
    if name.lower().endswith(".json"):
        name = name[:-5].strip("._-")
    if not name:
        raise ValueError(f"report_name {report_name!r} does not contain a usable file name.")
    return name


def quality_report_path(settings: Settings, report_name: str) -> Path:
    """Where a quality report with this name is written. Distinct names never collide."""
    return settings.paths.quality_dir / f"{_safe_report_stem(report_name)}.json"


def freshness_report_path(settings: Settings, report_name: str) -> Path:
    """Per-state freshness path for pipelines to pass into build_freshness_report.

    The starter config carries a single `paths.freshness_report`, which baseline, corrupted
    and repaired would overwrite in turn; this derives a separate file per state inside the
    same quality directory without changing the config contract.
    """
    return settings.paths.quality_dir / f"{_safe_report_stem(report_name)}.json"


# --- small helpers -----------------------------------------------------------------------


def _blank_mask(series: pd.Series) -> pd.Series:
    return series.map(is_blank).astype(bool)


def _rate(count: int, total: int) -> float:
    return round(count / total, 6) if total else 0.0


def _rate_status(rate: float, warn_above: float, fail_above: float) -> str:
    if rate > fail_above:
        return STATUS_FAIL
    if rate > warn_above:
        return STATUS_WARNING
    return STATUS_PASS


def _make_check(
    check_name: str,
    quality_dimension: str,
    status: str,
    observed_value: Any,
    expected_condition: str,
    affected_count: int,
    total_count: int,
    message: str,
) -> dict[str, Any]:
    return {
        "check_name": check_name,
        "quality_dimension": quality_dimension,
        "status": status,
        "observed_value": observed_value,
        "expected_condition": expected_condition,
        "affected_count": int(affected_count),
        "total_count": int(total_count),
        "message": message,
    }


def _missing_column_check(check_name: str, dimension: str, column: str, total: int) -> dict[str, Any]:
    return _make_check(
        check_name,
        dimension,
        STATUS_FAIL,
        None,
        f"column `{column}` exists",
        total,
        total,
        f"Column `{column}` is missing from the dataset, so this check could not run.",
    )


# --- individual checks --------------------------------------------------------------------


def _check_not_empty(total: int) -> dict[str, Any]:
    return _make_check(
        "dataset_not_empty",
        DIMENSION_COMPLETENESS,
        STATUS_PASS if total > 0 else STATUS_FAIL,
        total,
        "row_count > 0",
        0 if total > 0 else 1,
        total,
        f"Dataset holds {total} row(s)." if total else "Dataset is empty.",
    )


def _check_required_columns(df: pd.DataFrame, total: int) -> dict[str, Any]:
    missing = [column for column in REQUIRED_COLUMNS if column not in df.columns]
    return _make_check(
        "required_columns_present",
        DIMENSION_VALIDITY,
        STATUS_PASS if not missing else STATUS_FAIL,
        sorted(missing),
        f"all of {list(REQUIRED_COLUMNS)} present",
        len(missing),
        len(REQUIRED_COLUMNS),
        "All required columns are present."
        if not missing
        else f"Missing required column(s): {missing}.",
    )


def _check_paper_id(df: pd.DataFrame, total: int) -> list[dict[str, Any]]:
    if "paper_id" not in df.columns:
        return [
            _missing_column_check("paper_id_not_null", DIMENSION_COMPLETENESS, "paper_id", total),
            _missing_column_check("paper_id_not_blank", DIMENSION_COMPLETENESS, "paper_id", total),
            _missing_column_check("paper_id_unique", DIMENSION_UNIQUENESS, "paper_id", total),
        ]

    series = df["paper_id"]
    null_count = int(series.isna().sum())
    blank_count = int(_blank_mask(series).sum()) - null_count
    usable = series[~_blank_mask(series)].astype(str).str.strip()
    duplicate_count = int(usable.duplicated(keep="first").sum())

    return [
        _make_check(
            "paper_id_not_null",
            DIMENSION_COMPLETENESS,
            STATUS_PASS if null_count == 0 else STATUS_FAIL,
            _rate(null_count, total),
            "null_rate == 0",
            null_count,
            total,
            f"{null_count} row(s) have a null paper_id.",
        ),
        _make_check(
            "paper_id_not_blank",
            DIMENSION_COMPLETENESS,
            STATUS_PASS if blank_count == 0 else STATUS_FAIL,
            _rate(blank_count, total),
            "blank_rate == 0",
            blank_count,
            total,
            f"{blank_count} row(s) have a blank (non-null but empty) paper_id.",
        ),
        _make_check(
            "paper_id_unique",
            DIMENSION_UNIQUENESS,
            STATUS_PASS if duplicate_count == 0 else STATUS_FAIL,
            duplicate_count,
            "duplicate_count == 0",
            duplicate_count,
            int(len(usable)),
            f"{duplicate_count} paper_id value(s) appear more than once.",
        ),
    ]


def _check_field_completeness(df: pd.DataFrame, total: int) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for column, warn_above, fail_above in FIELD_COMPLETENESS_RULES:
        name = f"{column}_present"
        if column not in df.columns:
            checks.append(_missing_column_check(name, DIMENSION_COMPLETENESS, column, total))
            continue
        missing = int(_blank_mask(df[column]).sum())
        rate = _rate(missing, total)
        checks.append(
            _make_check(
                name,
                DIMENSION_COMPLETENESS,
                _rate_status(rate, warn_above, fail_above),
                rate,
                f"missing_rate <= {fail_above}",
                missing,
                total,
                f"{missing}/{total} row(s) have a missing or blank `{column}`.",
            )
        )
    return checks


def _check_published_validity(df: pd.DataFrame, total: int) -> dict[str, Any]:
    if "published" not in df.columns:
        return _missing_column_check("published_parseable", DIMENSION_VALIDITY, "published", total)
    parsed = pd.to_datetime(df["published"], errors="coerce", utc=True, format="mixed")
    invalid = int(parsed.isna().sum())
    rate = _rate(invalid, total)
    return _make_check(
        "published_parseable",
        DIMENSION_VALIDITY,
        STATUS_PASS if invalid == 0 else STATUS_FAIL,
        rate,
        "unparseable_rate == 0",
        invalid,
        total,
        f"{invalid}/{total} row(s) have a missing or unparseable `published` date.",
    )


def _check_age_days(df: pd.DataFrame, total: int) -> list[dict[str, Any]]:
    if "age_days" not in df.columns:
        return [
            _missing_column_check("age_days_numeric", DIMENSION_VALIDITY, "age_days", total),
            _missing_column_check("age_days_not_negative", DIMENSION_VALIDITY, "age_days", total),
        ]
    numeric = pd.to_numeric(df["age_days"], errors="coerce")
    non_numeric = int(numeric.isna().sum())
    implausible = int((numeric < -MAX_FUTURE_AGE_DAYS).sum())
    return [
        _make_check(
            "age_days_numeric",
            DIMENSION_VALIDITY,
            STATUS_PASS if non_numeric == 0 else STATUS_FAIL,
            _rate(non_numeric, total),
            "non_numeric_rate == 0",
            non_numeric,
            total,
            f"{non_numeric}/{total} row(s) have a missing or non-numeric `age_days`.",
        ),
        _make_check(
            "age_days_not_negative",
            DIMENSION_VALIDITY,
            STATUS_PASS if implausible == 0 else STATUS_FAIL,
            implausible,
            f"age_days >= -{MAX_FUTURE_AGE_DAYS}",
            implausible,
            total,
            f"{implausible} row(s) are dated more than {MAX_FUTURE_AGE_DAYS} day(s) in the future.",
        ),
    ]


def _check_duplicate_rows(df: pd.DataFrame, total: int) -> dict[str, Any]:
    try:
        duplicate_count = int(df.duplicated(keep="first").sum())
    except TypeError as exc:
        return _make_check(
            "duplicate_rows",
            DIMENSION_UNIQUENESS,
            STATUS_WARNING,
            None,
            "duplicate_row_count == 0",
            0,
            total,
            f"Duplicate detection could not run on this dataset: {exc}",
        )
    return _make_check(
        "duplicate_rows",
        DIMENSION_UNIQUENESS,
        STATUS_PASS if duplicate_count == 0 else STATUS_FAIL,
        duplicate_count,
        "duplicate_row_count == 0",
        duplicate_count,
        total,
        f"{duplicate_count} fully duplicated row(s).",
    )


def _check_urls(df: pd.DataFrame, total: int) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for column in OPTIONAL_URL_COLUMNS:
        if column not in df.columns:
            continue  # optional in the quality contract; the schema check already reports it
        invalid = int(
            df[column]
            .map(lambda value: is_blank(value) or not _URL_PATTERN.match(str(value).strip()))
            .astype(bool)
            .sum()
        )
        rate = _rate(invalid, total)
        checks.append(
            _make_check(
                f"{column}_valid",
                DIMENSION_VALIDITY,
                _rate_status(rate, URL_INVALID_WARN_RATE, URL_INVALID_FAIL_RATE),
                rate,
                f"invalid_url_rate <= {URL_INVALID_FAIL_RATE}",
                invalid,
                total,
                f"{invalid}/{total} row(s) have a missing or non-http(s) `{column}`.",
            )
        )
    return checks


def _check_freshness_dimension(df: pd.DataFrame, settings: Settings, total: int) -> dict[str, Any]:
    threshold = int(settings.freshness_threshold_days)
    if "age_days" not in df.columns:
        return _missing_column_check("data_within_freshness_threshold", DIMENSION_FRESHNESS, "age_days", total)
    numeric = pd.to_numeric(df["age_days"], errors="coerce")
    stale = int((numeric > threshold).sum())
    rate = _rate(stale, total)
    return _make_check(
        "data_within_freshness_threshold",
        DIMENSION_FRESHNESS,
        _rate_status(rate, STALE_ROW_WARN_RATE, STALE_ROW_FAIL_RATE),
        rate,
        f"stale_rate <= {STALE_ROW_FAIL_RATE} with age_days <= {threshold}",
        stale,
        total,
        f"{stale}/{total} row(s) are older than the {threshold}-day freshness threshold.",
    )


# --- public API ----------------------------------------------------------------------------


def run_data_quality_checks(df: pd.DataFrame, settings: Settings, report_name: str) -> dict[str, Any]:
    """Run the clean-dataset quality checks and persist them under `report_name`.

    The input frame is only read, never modified. A missing optional column is skipped; a
    missing required column produces an explicit failed check instead of an exception, so one
    schema gap does not hide every other finding.
    """
    output_path = quality_report_path(settings, report_name)
    total = int(len(df)) if df is not None else 0

    checks: list[dict[str, Any]] = [_check_not_empty(total)]
    if df is not None:
        checks.append(_check_required_columns(df, total))

    if df is not None and total > 0:
        checks.extend(_check_paper_id(df, total))
        checks.extend(_check_field_completeness(df, total))
        checks.append(_check_published_validity(df, total))
        checks.extend(_check_age_days(df, total))
        checks.append(_check_duplicate_rows(df, total))
        checks.extend(_check_urls(df, total))
        checks.append(_check_freshness_dimension(df, settings, total))

    failed = sum(1 for check in checks if check["status"] == STATUS_FAIL)
    warned = sum(1 for check in checks if check["status"] == STATUS_WARNING)
    passed = sum(1 for check in checks if check["status"] == STATUS_PASS)
    if failed:
        overall = STATUS_FAIL
    elif warned:
        overall = STATUS_WARNING
    else:
        overall = STATUS_PASS

    payload: dict[str, Any] = {
        "report_name": report_name,
        "report_path": str(output_path),
        "evaluated_at": now_utc().isoformat(),
        "dataset_rows": total,
        "schema_version": CLEAN_SCHEMA_VERSION,
        "freshness_threshold_days": int(settings.freshness_threshold_days),
        "checks": checks,
        "summary": {
            "total": len(checks),
            "passed": passed,
            "failed": failed,
            "warned": warned,
            "overall_status": overall,
        },
    }
    write_json(output_path, payload)
    return payload


def build_freshness_report(df: pd.DataFrame, settings: Settings, report_path) -> dict[str, Any]:
    """Summarise how current the dataset is, measured only from `published` and `age_days`.

    Staleness is read off `age_days`, which cleaning derives from the run date; the report's
    own generation time is never mixed into the measurement. `published` supplies the
    newest/oldest bounds and the date-validity count.

    Status:
      * `unknown` - nothing measurable: no rows, no `published`/`age_days` column, or every
        row's date or age is unusable.
      * `stale`   - measurable and not current: at least one row older than the configured
        threshold, or at least one row whose date or age cannot be read. A row with no usable
        date is never counted as fresh.
      * `fresh`   - every row has a parseable `published`, a numeric `age_days`, and no age
        exceeds the threshold.
    """
    report_path = Path(report_path)
    threshold = int(settings.freshness_threshold_days)
    total = int(len(df)) if df is not None else 0

    payload: dict[str, Any] = {
        "evaluated_at": now_utc().isoformat(),
        "report_path": str(report_path),
        "dataset_path": None,
        "measured_from": ["published", "age_days"],
        "row_count": total,
        "latest_published": None,
        "oldest_published": None,
        "min_age_days": None,
        "mean_age_days": None,
        "max_age_days": None,
        "threshold_days": threshold,
        "stale_rows": 0,
        "stale_row_rate": None,
        "invalid_or_missing_date_rows": total,
        "invalid_or_missing_age_rows": total,
        "future_dated_rows": 0,
        "status": "unknown",
        "reason": "",
    }

    if df is None or total == 0:
        payload["invalid_or_missing_date_rows"] = 0
        payload["invalid_or_missing_age_rows"] = 0
        payload["reason"] = "Dataset is empty, so freshness cannot be measured."
        write_json(report_path, payload)
        return payload

    missing_columns = [column for column in ("published", "age_days") if column not in df.columns]
    if missing_columns:
        payload["reason"] = (
            f"Column(s) {missing_columns} are absent, so freshness cannot be measured."
        )
        write_json(report_path, payload)
        return payload

    published = pd.to_datetime(df["published"], errors="coerce", utc=True, format="mixed")
    ages = pd.to_numeric(df["age_days"], errors="coerce")

    invalid_dates = int(published.isna().sum())
    invalid_ages = int(ages.isna().sum())
    usable_dates = published.dropna()
    usable_ages = ages.dropna()

    payload["invalid_or_missing_date_rows"] = invalid_dates
    payload["invalid_or_missing_age_rows"] = invalid_ages
    if not usable_dates.empty:
        payload["latest_published"] = usable_dates.max().isoformat()
        payload["oldest_published"] = usable_dates.min().isoformat()
    if not usable_ages.empty:
        payload["min_age_days"] = float(usable_ages.min())
        payload["mean_age_days"] = round(float(usable_ages.mean()), 4)
        payload["max_age_days"] = float(usable_ages.max())
        payload["future_dated_rows"] = int((usable_ages < -MAX_FUTURE_AGE_DAYS).sum())

    stale_rows = int((usable_ages > threshold).sum()) if not usable_ages.empty else 0
    payload["stale_rows"] = stale_rows
    payload["stale_row_rate"] = _rate(stale_rows, total)

    if usable_dates.empty and usable_ages.empty:
        payload["status"] = "unknown"
        payload["reason"] = (
            f"No row carries a usable `published` date or `age_days` value across {total} row(s)."
        )
    elif usable_ages.empty:
        payload["status"] = "unknown"
        payload["reason"] = (
            f"No row carries a usable `age_days` value, so staleness against the {threshold}-day "
            "threshold cannot be evaluated."
        )
    else:
        reasons: list[str] = []
        if stale_rows:
            reasons.append(f"{stale_rows}/{total} row(s) exceed the {threshold}-day threshold")
        if invalid_dates:
            reasons.append(f"{invalid_dates} row(s) have no usable `published` date")
        if invalid_ages:
            reasons.append(f"{invalid_ages} row(s) have no usable `age_days`")
        if reasons:
            payload["status"] = "stale"
            payload["reason"] = "Dataset is not fresh: " + "; ".join(reasons) + "."
        else:
            payload["status"] = "fresh"
            payload["reason"] = (
                f"All {total} row(s) have a usable date and an age within the {threshold}-day "
                f"threshold (max age {payload['max_age_days']} day(s))."
            )

    write_json(report_path, payload)
    return payload
