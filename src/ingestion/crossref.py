from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import requests

from core.config import Settings

CROSSREF_API_URL = "https://api.crossref.org/works"


@dataclass(frozen=True)
class PaperRecord:
    paper_id: str
    title: str
    summary: str
    authors: list[str]
    categories: list[str]
    primary_category: str
    published: str
    updated: str
    abs_url: str
    pdf_url: str
    comment: str


def _clean_html(text: str) -> str:
    if not text:
        return ""
    cleaned = re.sub(r"<[^>]+>", "", text)
    return " ".join(cleaned.split())


def _extract_date(item: dict[str, Any], date_keys: list[str]) -> str:
    for key in date_keys:
        date_info = item.get(key)
        if isinstance(date_info, dict):
            date_parts = date_info.get("date-parts", [[]])
            if date_parts and isinstance(date_parts, list) and len(date_parts) > 0 and len(date_parts[0]) > 0:
                parts = date_parts[0]
                try:
                    year = int(parts[0])
                    month = int(parts[1]) if len(parts) > 1 and 1 <= int(parts[1]) <= 12 else 1
                    day = int(parts[2]) if len(parts) > 2 and 1 <= int(parts[2]) <= 31 else 1
                    return f"{year:04d}-{month:02d}-{day:02d}"
                except (ValueError, TypeError):
                    continue
    return "1970-01-01"


def parse_crossref_payload(payload: dict) -> list[PaperRecord]:
    """Parse Crossref payload thanh list PaperRecord.

    Pseudo-code:
    1. Duyet `payload["message"]["items"]`.
    2. Lay DOI, title, abstract, authors, subject, dates, URLs.
    3. Chuan hoa text va bo record khong hop le.
    4. Tra ve list `PaperRecord`.
    """
    records: list[PaperRecord] = []
    message = payload.get("message", {})
    if not isinstance(message, dict):
        return records
    items = message.get("items", [])
    if not isinstance(items, list):
        return records

    for item in items:
        if not isinstance(item, dict):
            continue

        # 1. DOI tạo stable paper_id
        doi = str(item.get("DOI") or "").strip()
        if not doi:
            continue

        # 2. Title
        title_raw = item.get("title", [])
        if isinstance(title_raw, list) and len(title_raw) > 0:
            title = _clean_html(str(title_raw[0]))
        elif isinstance(title_raw, str):
            title = _clean_html(title_raw)
        else:
            title = ""
        if not title:
            continue

        # 3. Summary (Abstract)
        summary = _clean_html(str(item.get("abstract") or ""))

        # 4. Authors
        authors: list[str] = []
        author_list = item.get("author", [])
        if isinstance(author_list, list):
            for auth in author_list:
                if isinstance(auth, dict):
                    given = str(auth.get("given") or "").strip()
                    family = str(auth.get("family") or "").strip()
                    name = str(auth.get("name") or "").strip()
                    if given and family:
                        authors.append(f"{given} {family}")
                    elif family:
                        authors.append(family)
                    elif name:
                        authors.append(name)

        # 5. Categories & primary_category
        subjects = item.get("subject", [])
        if isinstance(subjects, list):
            categories = [str(s).strip() for s in subjects if str(s).strip()]
        elif isinstance(subjects, str) and subjects.strip():
            categories = [subjects.strip()]
        else:
            categories = []
        
        doc_type = str(item.get("type") or "general").strip()
        primary_category = categories[0] if categories else doc_type

        # 6. Dates (published & updated)
        published = _extract_date(item, ["published-print", "published-online", "published", "created", "issued"])
        updated = _extract_date(item, ["deposited", "indexed", "updated", "published-online", "published-print", "published", "created"])

        # 7. URLs
        abs_url = str(item.get("URL") or f"http://dx.doi.org/{doi}").strip()
        pdf_url = abs_url
        links = item.get("link", [])
        if isinstance(links, list):
            for link in links:
                if isinstance(link, dict) and link.get("content-type") == "application/pdf":
                    url = str(link.get("URL") or "").strip()
                    if url:
                        pdf_url = url
                        break

        # 8. Comment
        comment = doc_type

        records.append(
            PaperRecord(
                paper_id=doi,
                title=title,
                summary=summary,
                authors=authors,
                categories=categories,
                primary_category=primary_category,
                published=published,
                updated=updated,
                abs_url=abs_url,
                pdf_url=pdf_url,
                comment=comment,
            )
        )

    return records


def fetch_source_records(settings: Settings) -> list[PaperRecord]:
    """Goi source API, luu raw response, parse thanh records.

    Pseudo-code:
    1. Tao params tu `settings.source_query`, `settings.source_filter`, `settings.max_results`.
    2. Goi API voi retry cho cac status code nhu 429/503.
    3. Luu raw response vao `settings.paths.raw_api_response`.
    4. Parse payload bang `parse_crossref_payload`.
    5. Luu records vao `settings.paths.raw_records_json`.
    """
    params = {
        "query": settings.source_query,
        "filter": settings.source_filter,
        "rows": settings.max_results,
    }

    max_retries = 5
    base_delay = 1.0
    payload: dict[str, Any] = {}

    for attempt in range(max_retries):
        response = requests.get(CROSSREF_API_URL, params=params, timeout=20)
        if response.status_code == 200:
            payload = response.json()
            break
        elif response.status_code in {429, 500, 502, 503, 504}:
            if attempt < max_retries - 1:
                time.sleep(base_delay * (2 ** attempt))
                continue
        response.raise_for_status()
    else:
        raise RuntimeError("Failed to fetch records from Crossref API after retries.")

    # Luu raw response vao file
    settings.paths.raw_api_response.parent.mkdir(parents=True, exist_ok=True)
    settings.paths.raw_api_response.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    # Parse payload
    records = parse_crossref_payload(payload)

    # Luu raw records vao file
    settings.paths.raw_records_json.parent.mkdir(parents=True, exist_ok=True)
    records_data = [asdict(r) for r in records]
    settings.paths.raw_records_json.write_text(
        json.dumps(records_data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    return records


def load_raw_records(path: Path) -> list[PaperRecord]:
    """Doc JSON snapshot va map thanh `PaperRecord`."""
    if not path.exists():
        return []
    content = path.read_text(encoding="utf-8")
    if not content.strip():
        return []
    data = json.loads(content)
    return [PaperRecord(**item) for item in data]

