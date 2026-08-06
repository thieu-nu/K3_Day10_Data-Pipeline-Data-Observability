import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.config import load_settings
from ingestion.crossref import (
    PaperRecord,
    fetch_source_records,
    load_raw_records,
    parse_crossref_payload,
)


@pytest.fixture
def sample_crossref_payload():
    return {
        "status": "ok",
        "message-type": "work-list",
        "message-version": "1.0.0",
        "message": {
            "items": [
                {
                    "DOI": "10.1007/978-3-030-58465-8_13",
                    "title": ["An Agent-Based Architecture for RAG"],
                    "abstract": "<jats:p>This is a test <p>abstract</p> with XML tags.</jats:p>",
                    "author": [
                        {"given": "John", "family": "Doe"},
                        {"family": "Smith"},
                    ],
                    "subject": ["Computer Science", "Artificial Intelligence"],
                    "published": {"date-parts": [[2024, 5, 15]]},
                    "URL": "http://dx.doi.org/10.1007/978-3-030-58465-8_13",
                    "link": [
                        {"URL": "https://example.com/paper.pdf", "content-type": "application/pdf"}
                    ],
                    "type": "journal-article",
                },
                {
                    # Invalid record (missing title)
                    "DOI": "10.1000/no_title"
                },
                {
                    # Invalid record (missing DOI)
                    "title": ["Missing DOI Paper"]
                }
            ]
        },
    }


def test_parse_crossref_payload(sample_crossref_payload):
    records = parse_crossref_payload(sample_crossref_payload)
    assert len(records) == 1
    record = records[0]
    assert record.paper_id == "10.1007/978-3-030-58465-8_13"
    assert record.title == "An Agent-Based Architecture for RAG"
    assert record.summary == "This is a test abstract with XML tags."
    assert record.authors == ["John Doe", "Smith"]
    assert record.categories == ["Computer Science", "Artificial Intelligence"]
    assert record.primary_category == "Computer Science"
    assert record.published == "2024-05-15"
    assert record.abs_url == "http://dx.doi.org/10.1007/978-3-030-58465-8_13"
    assert record.pdf_url == "https://example.com/paper.pdf"


def test_fetch_and_load_source_records(tmp_path, sample_crossref_payload):
    settings = load_settings()
    # Override paths to use tmp_path
    raw_api = tmp_path / "raw_response.json"
    raw_records = tmp_path / "raw_records.json"
    
    # Using patch to redirect file paths in settings
    with patch.object(settings.paths, "raw_api_response", raw_api), patch.object(
        settings.paths, "raw_records_json", raw_records
    ):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = sample_crossref_payload

        with patch("requests.get", return_value=mock_response) as mock_get:
            records = fetch_source_records(settings)
            mock_get.assert_called_once()
            assert len(records) == 1
            assert raw_api.exists()
            assert raw_records.exists()

            # Verify loading back
            loaded_records = load_raw_records(raw_records)
            assert len(loaded_records) == 1
            assert loaded_records[0].paper_id == records[0].paper_id
            assert loaded_records[0].title == records[0].title
