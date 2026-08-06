from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
import json
import math
from numbers import Real
from pathlib import Path
from typing import Any

import pandas as pd

from core.config import Settings
from core.utils import write_json


CLEAN_CONTRACT_VERSION = "clean-v1"
CLEANING_SUMMARY_ATTR = "cleaning_summary"

RAW_REQUIRED_FIELDS = (
    "paper_id",
    "title",
    "summary",
    "authors",
    "categories",
    "primary_category",
    "published",
    "updated",
    "abs_url",
    "pdf_url",
    "comment",
)

CLEAN_REQUIRED_COLUMNS = (
    "paper_id",
    "title",
    "summary",
    "published",
    "age_days",
    "authors_joined",
    "categories_joined",
    "summary_chars",
    "text_for_embedding",
    "abs_url",
    "pdf_url",
)

_CLEAN_STRING_COLUMNS = (
    "paper_id",
    "title",
    "summary",
    "published",
    "authors_joined",
    "categories_joined",
    "text_for_embedding",
    "abs_url",
    "pdf_url",
)

_NONBLANK_CLEAN_COLUMNS = ("paper_id", "title", "summary", "text_for_embedding")
_SUMMARY_COUNT_FIELDS = ("raw_count", "filtered_count", "deduplicated_count", "clean_count")
_REASON_GROUPS = ("filtered", "deduplicated")


@dataclass(frozen=True)
class CleanContractBlocker:
    code: str
    message: str
    evidence: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "evidence": self.evidence,
        }


@dataclass(frozen=True)
class CleanGateReport:
    status: str
    checked_at: str
    artifacts: dict[str, dict[str, Any]]
    counts: dict[str, int | None]
    schema: dict[str, list[str]]
    clean_snapshot_sha256: str | None
    blockers: tuple[CleanContractBlocker, ...]

    @property
    def passed(self) -> bool:
        return self.status == "GO"

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": CLEAN_CONTRACT_VERSION,
            "status": self.status,
            "checked_at": self.checked_at,
            "artifacts": self.artifacts,
            "counts": self.counts,
            "schema": self.schema,
            "clean_snapshot_sha256": self.clean_snapshot_sha256,
            "blockers": [blocker.to_dict() for blocker in self.blockers],
        }


@dataclass(frozen=True)
class ValidatedCleanSnapshot:
    dataframe: pd.DataFrame
    report: CleanGateReport


class CleanContractError(RuntimeError):
    def __init__(self, report: CleanGateReport, report_path: Path):
        self.report = report
        self.report_path = report_path
        codes = ", ".join(blocker.code for blocker in report.blockers)
        super().__init__(
            f"Clean contract {CLEAN_CONTRACT_VERSION} is STOP. "
            f"Evidence: {report_path}. Blockers: {codes}"
        )


def _add_blocker(
    blockers: list[CleanContractBlocker],
    code: str,
    message: str,
    **evidence: Any,
) -> None:
    blockers.append(CleanContractBlocker(code=code, message=message, evidence=evidence))


def _display_path(path: Path, project_dir: Path) -> str:
    try:
        return path.resolve().relative_to(project_dir.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _describe_artifact(path: Path, project_dir: Path) -> dict[str, Any]:
    is_file = path.is_file()
    descriptor: dict[str, Any] = {
        "path": _display_path(path, project_dir),
        "exists": path.exists(),
        "is_file": is_file,
        "size_bytes": path.stat().st_size if is_file else None,
        "sha256": None,
    }
    if is_file:
        try:
            descriptor["sha256"] = _sha256_file(path)
        except OSError as exc:
            descriptor["hash_error"] = str(exc)
    return descriptor


def _read_json(
    path: Path,
    artifact_code: str,
    project_dir: Path,
    blockers: list[CleanContractBlocker],
) -> Any | None:
    display_path = _display_path(path, project_dir)
    if not path.is_file():
        _add_blocker(
            blockers,
            f"{artifact_code}_MISSING",
            "Required JSON artifact does not exist.",
            path=display_path,
        )
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        _add_blocker(
            blockers,
            f"{artifact_code}_INVALID_JSON",
            "Required JSON artifact cannot be parsed.",
            path=display_path,
            error=str(exc),
        )
        return None


def _read_clean_csv(
    path: Path,
    project_dir: Path,
    blockers: list[CleanContractBlocker],
) -> pd.DataFrame | None:
    display_path = _display_path(path, project_dir)
    if not path.is_file():
        _add_blocker(
            blockers,
            "CLEAN_CSV_MISSING",
            "Required clean CSV artifact does not exist.",
            path=display_path,
        )
        return None
    try:
        return pd.read_csv(path, keep_default_na=False)
    except Exception as exc:
        _add_blocker(
            blockers,
            "CLEAN_CSV_INVALID",
            "Required clean CSV artifact cannot be parsed.",
            path=display_path,
            error=str(exc),
        )
        return None


def _is_nonnegative_whole_number(value: Any) -> bool:
    return (
        isinstance(value, Real)
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and float(value) >= 0
        and float(value).is_integer()
    )


def _is_iso_date_or_datetime(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def _normalized_ids(df: pd.DataFrame) -> list[str]:
    if "paper_id" not in df.columns:
        return []
    return [
        value.strip().casefold() if isinstance(value, str) else ""
        for value in df["paper_id"].tolist()
    ]


def _canonical_clean_records(df: pd.DataFrame) -> list[dict[str, Any]] | None:
    if set(CLEAN_REQUIRED_COLUMNS) - set(df.columns):
        return None
    records: list[dict[str, Any]] = []
    for row in df.loc[:, CLEAN_REQUIRED_COLUMNS].to_dict(orient="records"):
        canonical: dict[str, Any] = {}
        for column, value in row.items():
            if column in {"age_days", "summary_chars"} and _is_nonnegative_whole_number(value):
                canonical[column] = int(value)
            elif isinstance(value, (str, int, float, bool)) or value is None:
                canonical[column] = value
            else:
                canonical[column] = repr(value)
        records.append(canonical)
    return records


def _validate_raw_records(
    raw_records: list[Any],
    blockers: list[CleanContractBlocker],
) -> list[str]:
    if not raw_records:
        _add_blocker(
            blockers,
            "RAW_RECORDS_EMPTY",
            "Raw snapshot contains no records.",
            raw_count=0,
        )
        return []

    wrong_shape_rows = [index for index, record in enumerate(raw_records) if not isinstance(record, Mapping)]
    if wrong_shape_rows:
        _add_blocker(
            blockers,
            "RAW_RECORD_SHAPE_INVALID",
            "Every raw record must be a JSON object.",
            row_indices=wrong_shape_rows[:20],
            affected_count=len(wrong_shape_rows),
        )

    missing_by_field: dict[str, int] = {}
    raw_ids: list[str] = []
    for record in raw_records:
        if not isinstance(record, Mapping):
            continue
        for field in RAW_REQUIRED_FIELDS:
            if field not in record:
                missing_by_field[field] = missing_by_field.get(field, 0) + 1
        paper_id = record.get("paper_id")
        if isinstance(paper_id, str) and paper_id.strip():
            raw_ids.append(paper_id.strip().casefold())

    if missing_by_field:
        _add_blocker(
            blockers,
            "RAW_SCHEMA_INVALID",
            "Raw records are missing fields required by PaperRecord.",
            missing_by_field=missing_by_field,
            required_fields=list(RAW_REQUIRED_FIELDS),
        )
    if len(raw_ids) != len(raw_records):
        _add_blocker(
            blockers,
            "RAW_PAPER_ID_INVALID",
            "Every raw record must have a nonblank string paper_id.",
            valid_id_count=len(raw_ids),
            raw_count=len(raw_records),
        )
    return raw_ids


def _validate_clean_dataframe(
    df: pd.DataFrame,
    artifact_name: str,
    blockers: list[CleanContractBlocker],
) -> list[str]:
    missing_columns = sorted(set(CLEAN_REQUIRED_COLUMNS) - set(df.columns))
    if missing_columns:
        _add_blocker(
            blockers,
            f"{artifact_name}_SCHEMA_INVALID",
            "Clean artifact is missing columns required by downstream modules.",
            missing_columns=missing_columns,
            required_columns=list(CLEAN_REQUIRED_COLUMNS),
        )
        return _normalized_ids(df)

    for column in _CLEAN_STRING_COLUMNS:
        invalid_rows = [
            index
            for index, value in enumerate(df[column].tolist())
            if not isinstance(value, str)
        ]
        if invalid_rows:
            _add_blocker(
                blockers,
                f"{artifact_name}_{column.upper()}_TYPE_INVALID",
                f"Column {column} must contain strings.",
                row_indices=invalid_rows[:20],
                affected_count=len(invalid_rows),
            )

    for column in _NONBLANK_CLEAN_COLUMNS:
        blank_rows = [
            index
            for index, value in enumerate(df[column].tolist())
            if not isinstance(value, str) or not value.strip()
        ]
        if blank_rows:
            _add_blocker(
                blockers,
                f"{artifact_name}_{column.upper()}_BLANK",
                f"Column {column} must not contain blank values.",
                row_indices=blank_rows[:20],
                affected_count=len(blank_rows),
            )

    normalized_ids = _normalized_ids(df)
    duplicate_ids = sorted(
        {
            paper_id
            for paper_id in normalized_ids
            if paper_id and normalized_ids.count(paper_id) > 1
        }
    )
    if duplicate_ids:
        _add_blocker(
            blockers,
            f"{artifact_name}_PAPER_ID_DUPLICATE",
            "paper_id must be unique after trimming and case folding.",
            duplicate_ids=duplicate_ids[:20],
            affected_id_count=len(duplicate_ids),
        )

    invalid_published_rows = [
        index
        for index, value in enumerate(df["published"].tolist())
        if not _is_iso_date_or_datetime(value)
    ]
    if invalid_published_rows:
        _add_blocker(
            blockers,
            f"{artifact_name}_PUBLISHED_INVALID",
            "published must contain ISO dates or datetimes.",
            row_indices=invalid_published_rows[:20],
            affected_count=len(invalid_published_rows),
        )

    invalid_age_rows = [
        index
        for index, value in enumerate(df["age_days"].tolist())
        if not _is_nonnegative_whole_number(value)
    ]
    if invalid_age_rows:
        _add_blocker(
            blockers,
            f"{artifact_name}_AGE_DAYS_INVALID",
            "age_days must contain nonnegative whole numbers.",
            row_indices=invalid_age_rows[:20],
            affected_count=len(invalid_age_rows),
        )

    invalid_summary_chars_rows = [
        index
        for index, value in enumerate(df["summary_chars"].tolist())
        if not _is_nonnegative_whole_number(value)
    ]
    if invalid_summary_chars_rows:
        _add_blocker(
            blockers,
            f"{artifact_name}_SUMMARY_CHARS_INVALID",
            "summary_chars must contain nonnegative whole numbers.",
            row_indices=invalid_summary_chars_rows[:20],
            affected_count=len(invalid_summary_chars_rows),
        )

    summary_length_mismatch_rows = [
        index
        for index, (summary, summary_chars) in enumerate(
            zip(df["summary"].tolist(), df["summary_chars"].tolist(), strict=False)
        )
        if isinstance(summary, str)
        and _is_nonnegative_whole_number(summary_chars)
        and len(summary) != int(summary_chars)
    ]
    if summary_length_mismatch_rows:
        _add_blocker(
            blockers,
            f"{artifact_name}_SUMMARY_CHARS_MISMATCH",
            "summary_chars must equal the character length of summary.",
            row_indices=summary_length_mismatch_rows[:20],
            affected_count=len(summary_length_mismatch_rows),
        )
    return normalized_ids


def _validated_summary_counts(
    summary: Mapping[str, Any],
    blockers: list[CleanContractBlocker],
) -> dict[str, int] | None:
    if summary.get("contract_version") != CLEAN_CONTRACT_VERSION:
        _add_blocker(
            blockers,
            "CLEANING_SUMMARY_VERSION_INVALID",
            "Cleaning summary contract_version does not match the clean contract.",
            expected=CLEAN_CONTRACT_VERSION,
            actual=summary.get("contract_version"),
        )

    counts: dict[str, int] = {}
    for field in _SUMMARY_COUNT_FIELDS:
        value = summary.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            _add_blocker(
                blockers,
                "CLEANING_SUMMARY_COUNT_INVALID",
                "Cleaning summary counts must be nonnegative integers.",
                field=field,
                actual=value,
            )
        else:
            counts[field] = value

    reason_counts = summary.get("reason_counts")
    if not isinstance(reason_counts, Mapping):
        _add_blocker(
            blockers,
            "CLEANING_SUMMARY_REASONS_INVALID",
            "reason_counts must be an object with filtered and deduplicated groups.",
            actual_type=type(reason_counts).__name__,
        )
    else:
        for group in _REASON_GROUPS:
            group_counts = reason_counts.get(group)
            if not isinstance(group_counts, Mapping):
                _add_blocker(
                    blockers,
                    "CLEANING_SUMMARY_REASON_GROUP_INVALID",
                    "Each reason_counts group must be an object.",
                    group=group,
                    actual_type=type(group_counts).__name__,
                )
                continue
            invalid_reasons = {
                str(reason): count
                for reason, count in group_counts.items()
                if not isinstance(reason, str)
                or not reason.strip()
                or not isinstance(count, int)
                or isinstance(count, bool)
                or count < 0
            }
            if invalid_reasons:
                _add_blocker(
                    blockers,
                    "CLEANING_SUMMARY_REASON_COUNT_INVALID",
                    "Reason names must be nonblank and reason counts must be nonnegative integers.",
                    group=group,
                    invalid_reasons=invalid_reasons,
                )
                continue
            expected_count = counts.get("filtered_count" if group == "filtered" else "deduplicated_count")
            actual_count = sum(group_counts.values())
            if expected_count is not None and actual_count != expected_count:
                _add_blocker(
                    blockers,
                    "CLEANING_SUMMARY_REASON_TOTAL_MISMATCH",
                    "Reason counts do not sum to their aggregate count.",
                    group=group,
                    expected=expected_count,
                    actual=actual_count,
                )

    if len(counts) != len(_SUMMARY_COUNT_FIELDS):
        return None
    if counts["raw_count"] != (
        counts["clean_count"] + counts["filtered_count"] + counts["deduplicated_count"]
    ):
        _add_blocker(
            blockers,
            "CLEANING_SUMMARY_EQUATION_MISMATCH",
            "raw_count must equal clean_count + filtered_count + deduplicated_count.",
            **counts,
        )
    return counts


def persist_cleaning_summary(
    settings: Settings,
    raw_count: int,
    clean_df: pd.DataFrame,
) -> dict[str, Any]:
    """Persist the cleaning-owner audit carried in DataFrame.attrs.

    The cleaning owner supplies filtered_count, deduplicated_count, and
    reason_counts in df.attrs["cleaning_summary"]. Orchestration adds observed
    raw/clean counts and the locked contract version. A no-loss handoff can be
    derived safely; any unexplained row loss remains incomplete and fails the
    clean gate.
    """

    provided = clean_df.attrs.get(CLEANING_SUMMARY_ATTR)
    payload = dict(provided) if isinstance(provided, Mapping) else {}
    clean_count = len(clean_df)
    payload["contract_version"] = CLEAN_CONTRACT_VERSION
    payload["raw_count"] = raw_count
    payload["clean_count"] = clean_count

    if not isinstance(provided, Mapping) and raw_count == clean_count:
        payload["filtered_count"] = 0
        payload["deduplicated_count"] = 0
        payload["reason_counts"] = {"filtered": {}, "deduplicated": {}}
    else:
        payload.setdefault("filtered_count", None)
        payload.setdefault("deduplicated_count", None)
        payload.setdefault("reason_counts", {"filtered": {}, "deduplicated": {}})

    write_json(settings.paths.cleaning_summary, payload)
    return payload


def _evaluate_clean_contract(
    settings: Settings,
) -> tuple[CleanGateReport, pd.DataFrame | None]:
    paths = settings.paths
    project_dir = paths.project_dir
    blockers: list[CleanContractBlocker] = []
    artifact_paths = {
        "raw_response": paths.raw_api_response,
        "raw_records": paths.raw_records_json,
        "clean_csv": paths.clean_csv,
        "clean_json": paths.clean_json,
        "cleaning_summary": paths.cleaning_summary,
    }
    artifacts = {
        name: _describe_artifact(path, project_dir)
        for name, path in artifact_paths.items()
    }

    raw_response = _read_json(
        paths.raw_api_response,
        "RAW_RESPONSE",
        project_dir,
        blockers,
    )
    if raw_response is not None and not isinstance(raw_response, Mapping):
        _add_blocker(
            blockers,
            "RAW_RESPONSE_SHAPE_INVALID",
            "Crossref raw response must be a JSON object.",
            actual_type=type(raw_response).__name__,
        )

    raw_records_payload = _read_json(
        paths.raw_records_json,
        "RAW_RECORDS",
        project_dir,
        blockers,
    )
    raw_records = raw_records_payload if isinstance(raw_records_payload, list) else None
    if raw_records_payload is not None and raw_records is None:
        _add_blocker(
            blockers,
            "RAW_RECORDS_SHAPE_INVALID",
            "Raw records artifact must be a JSON list.",
            actual_type=type(raw_records_payload).__name__,
        )

    clean_csv_df = _read_clean_csv(paths.clean_csv, project_dir, blockers)

    clean_json_payload = _read_json(
        paths.clean_json,
        "CLEAN_JSON",
        project_dir,
        blockers,
    )
    clean_json_records = clean_json_payload if isinstance(clean_json_payload, list) else None
    if clean_json_payload is not None and clean_json_records is None:
        _add_blocker(
            blockers,
            "CLEAN_JSON_SHAPE_INVALID",
            "Clean JSON artifact must be a list of records.",
            actual_type=type(clean_json_payload).__name__,
        )
    clean_json_df: pd.DataFrame | None = None
    if clean_json_records is not None:
        invalid_rows = [
            index
            for index, record in enumerate(clean_json_records)
            if not isinstance(record, Mapping)
        ]
        if invalid_rows:
            _add_blocker(
                blockers,
                "CLEAN_JSON_RECORD_SHAPE_INVALID",
                "Every clean JSON record must be an object.",
                row_indices=invalid_rows[:20],
                affected_count=len(invalid_rows),
            )
        else:
            clean_json_df = pd.DataFrame(clean_json_records)

    summary_payload = _read_json(
        paths.cleaning_summary,
        "CLEANING_SUMMARY",
        project_dir,
        blockers,
    )
    summary = summary_payload if isinstance(summary_payload, Mapping) else None
    if summary_payload is not None and summary is None:
        _add_blocker(
            blockers,
            "CLEANING_SUMMARY_SHAPE_INVALID",
            "Cleaning summary must be a JSON object.",
            actual_type=type(summary_payload).__name__,
        )

    raw_count = len(raw_records) if raw_records is not None else None
    clean_csv_count = len(clean_csv_df) if clean_csv_df is not None else None
    clean_json_count = len(clean_json_records) if clean_json_records is not None else None
    raw_ids = _validate_raw_records(raw_records, blockers) if raw_records is not None else []
    csv_ids = (
        _validate_clean_dataframe(clean_csv_df, "CLEAN_CSV", blockers)
        if clean_csv_df is not None
        else []
    )
    json_ids = (
        _validate_clean_dataframe(clean_json_df, "CLEAN_JSON", blockers)
        if clean_json_df is not None
        else []
    )

    if clean_csv_count == 0:
        _add_blocker(
            blockers,
            "CLEAN_CSV_EMPTY",
            "Clean CSV contains no records.",
            clean_csv_count=0,
        )
    if clean_json_count == 0:
        _add_blocker(
            blockers,
            "CLEAN_JSON_EMPTY",
            "Clean JSON contains no records.",
            clean_json_count=0,
        )
    if (
        clean_csv_count is not None
        and clean_json_count is not None
        and clean_csv_count != clean_json_count
    ):
        _add_blocker(
            blockers,
            "CLEAN_ARTIFACT_COUNT_MISMATCH",
            "Clean CSV and JSON must contain the same number of records.",
            clean_csv_count=clean_csv_count,
            clean_json_count=clean_json_count,
        )
    if csv_ids and json_ids and csv_ids != json_ids:
        _add_blocker(
            blockers,
            "CLEAN_ARTIFACT_IDENTITY_MISMATCH",
            "Clean CSV and JSON must contain the same ordered paper_id values.",
            csv_ids=csv_ids[:20],
            json_ids=json_ids[:20],
        )
    if clean_csv_df is not None and clean_json_df is not None:
        csv_records = _canonical_clean_records(clean_csv_df)
        json_records = _canonical_clean_records(clean_json_df)
        if csv_records is not None and json_records is not None and csv_records != json_records:
            mismatch_rows = [
                index
                for index, (csv_row, json_row) in enumerate(
                    zip(csv_records, json_records, strict=False)
                )
                if csv_row != json_row
            ]
            if len(csv_records) != len(json_records):
                mismatch_rows.extend(
                    range(min(len(csv_records), len(json_records)), max(len(csv_records), len(json_records)))
                )
            _add_blocker(
                blockers,
                "CLEAN_ARTIFACT_CONTENT_MISMATCH",
                "Clean CSV and JSON must contain the same ordered required-field values.",
                row_indices=mismatch_rows[:20],
                affected_count=len(mismatch_rows),
            )
    if raw_ids and json_ids:
        unexpected_clean_ids = sorted(set(json_ids) - set(raw_ids))
        if unexpected_clean_ids:
            _add_blocker(
                blockers,
                "CLEAN_LINEAGE_INVALID",
                "Every clean paper_id must be traceable to the raw snapshot.",
                unexpected_clean_ids=unexpected_clean_ids[:20],
                affected_id_count=len(unexpected_clean_ids),
            )
    if (
        raw_count is not None
        and clean_json_count is not None
        and clean_json_count > raw_count
    ):
        _add_blocker(
            blockers,
            "CLEAN_COUNT_EXCEEDS_RAW",
            "Clean count cannot exceed raw count.",
            raw_count=raw_count,
            clean_count=clean_json_count,
        )

    summary_counts = _validated_summary_counts(summary, blockers) if summary is not None else None
    if summary_counts is not None:
        if raw_count is not None and summary_counts["raw_count"] != raw_count:
            _add_blocker(
                blockers,
                "RAW_COUNT_MISMATCH",
                "Cleaning summary raw_count does not match the raw snapshot.",
                observed=raw_count,
                summary=summary_counts["raw_count"],
            )
        observed_clean_counts = {
            count
            for count in (clean_csv_count, clean_json_count)
            if count is not None
        }
        if any(summary_counts["clean_count"] != count for count in observed_clean_counts):
            _add_blocker(
                blockers,
                "CLEAN_COUNT_MISMATCH",
                "Cleaning summary clean_count does not match clean artifacts.",
                clean_csv_count=clean_csv_count,
                clean_json_count=clean_json_count,
                summary=summary_counts["clean_count"],
            )

    schema = {
        "required_raw_fields": list(RAW_REQUIRED_FIELDS),
        "required_clean_columns": list(CLEAN_REQUIRED_COLUMNS),
        "clean_csv_columns": list(clean_csv_df.columns) if clean_csv_df is not None else [],
        "clean_json_columns": list(clean_json_df.columns) if clean_json_df is not None else [],
    }
    report = CleanGateReport(
        status="GO" if not blockers else "STOP",
        checked_at=datetime.now(UTC).isoformat(),
        artifacts=artifacts,
        counts={
            "raw_count": raw_count,
            "clean_csv_count": clean_csv_count,
            "clean_json_count": clean_json_count,
            "filtered_count": summary_counts["filtered_count"] if summary_counts else None,
            "deduplicated_count": summary_counts["deduplicated_count"] if summary_counts else None,
        },
        schema=schema,
        clean_snapshot_sha256=artifacts["clean_json"].get("sha256"),
        blockers=tuple(blockers),
    )
    return report, clean_json_df


def audit_clean_contract(settings: Settings) -> CleanGateReport:
    """Audit persisted raw/clean artifacts and always write GO/STOP evidence."""

    report, _ = _evaluate_clean_contract(settings)
    write_json(settings.paths.clean_gate_report, report.to_dict())
    return report


def enforce_clean_contract(settings: Settings) -> ValidatedCleanSnapshot:
    """Return the validated clean JSON snapshot or fail before downstream work."""

    report, clean_df = _evaluate_clean_contract(settings)
    write_json(settings.paths.clean_gate_report, report.to_dict())
    if not report.passed or clean_df is None:
        raise CleanContractError(report, settings.paths.clean_gate_report)
    return ValidatedCleanSnapshot(dataframe=clean_df.copy(deep=True), report=report)
