from __future__ import annotations

from datetime import UTC, datetime
import json
import math
from pathlib import Path
import re
from typing import Any, Iterable

_BLANK_PLACEHOLDERS = frozenset({"nan", "nat", "none", "null", "<na>"})

# Applied to any provider text before it reaches an artifact or a report.
_SECRET_PATTERNS = (
    (re.compile(r"(authorization\s*['\"]?\s*[:=]\s*['\"]?)(bearer\s+)?[^\s'\"},]+", re.IGNORECASE), r"\1***"),
    (re.compile(r"((?:api[_-]?key|access[_-]?token|bearer)\s*['\"]?\s*[:=]\s*['\"]?)[^\s'\"},]+", re.IGNORECASE), r"\1***"),
    (re.compile(r"\b(?:sk|pk|gsk|xai)-[A-Za-z0-9_\-]{6,}"), "***"),
    (re.compile(r"\bAIza[0-9A-Za-z_\-]{10,}"), "***"),
)


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, payload: Any) -> None:
    ensure_parent(path)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_csv(df, path: Path) -> None:
    ensure_parent(path)
    df.to_csv(path, index=False)


def write_text(path: Path, text: str) -> None:
    ensure_parent(path)
    path.write_text(text, encoding="utf-8")


def now_utc() -> datetime:
    return datetime.now(UTC)


def normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def redact_secrets(text: Any) -> str:
    """Mask credential-shaped substrings so provider text is safe to persist.

    Pattern-based, so it also catches keys this process never held (for instance one echoed
    back inside a provider error body). Callers that do hold the configured key should
    replace that literal value first and then call this.
    """
    redacted = str(text)
    for pattern, replacement in _SECRET_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def is_blank(value: Any) -> bool:
    """True for None, NaN/NaT/NA, empty strings and whitespace-only strings.

    One definition shared by the evaluation-set validator and the data quality checks, so a
    field never counts as present in one report and missing in the other.
    """
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    try:
        text = normalize_whitespace(str(value))
    except Exception:
        return False
    return not text or text.lower() in _BLANK_PLACEHOLDERS


def safe_slug(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return cleaned or "item"


def compact_join(items: Iterable[str], sep: str = ", ") -> str:
    return sep.join(item for item in items if item)


def first_sentence(text: str) -> str:
    chunks = re.split(r"(?<=[.!?])\s+", normalize_whitespace(text))
    return chunks[0] if chunks else normalize_whitespace(text)
