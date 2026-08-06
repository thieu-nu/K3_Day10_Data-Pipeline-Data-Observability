# Phase 1 - Baseline Report

Generated at: 2026-08-06T05:08:42.855785+00:00
Evaluation state: `baseline`

## 1. Source

| Field | Value |
|---|---|
| `source` | Crossref REST API |
| `query` | agentic retrieval augmented generation large language model |
| `filter` | from-pub-date:2026-02-07,has-abstract:true |
| `raw_count` | 24 |
| `clean_count` | 24 |
| `clean_contract` | clean-v1 |
| `clean_snapshot_sha256` | a805ea3cce587843cecbe78fafd3727c21c018102c095050f52979c1d5109d0a |
| `clean_gate_report` | D:\CODE\AITHUCCHIEN\LABS\K3_Day10_Data-Pipeline-Data-Observability\data\quality\clean_contract_gate.json |

## 2. Dataset and index

| Field | Value |
|---|---|
| Dataset path | N/A |
| Collection | papers-baseline |
| Documents indexed | 24 |
| Embedding model | sentence-transformers/all-MiniLM-L6-v2 |
| top_k | 4 |
| Rows in quality run | 24 |
| Clean schema version | clean-v1 |

## 3. Evaluation set

| Field | Value |
|---|---|
| Path | D:\CODE\AITHUCCHIEN\LABS\K3_Day10_Data-Pipeline-Data-Observability\data\eval\test_set.json |
| Fingerprint | `a9eb111d8faaa7ebc6ced787215d72133d8fb1eaf784800c92d5c06296844279` |
| Questions in file | 12 |
| Evaluated | 12 |
| Failed | 0 |

## 4. LLM provider

| Field | Value |
|---|---|
| Provider | openrouter |
| Model | nvidia/nemotron-3-ultra-550b-a55b:free |
| Judge rubric version | role5-judge-v1 |

_No credential is recorded here; only the provider and model names are._

## 5. Retrieval metrics

| Metric | Value | Denominator |
|---|---|---|
| retrieval_hit_rate | 1.0000 | 12 / 12 |
| semantic_retrieval_hit_rate | 1.0000 | 3 / 3 |
| exact_lookup_success_rate | 1.0000 | 9 / 9 |

`exact_lookup_success_rate` measures the exact-title shortcut in `retrieval.qa`, not semantic search; the two are reported apart on purpose.

## 6. Answer quality

| Metric | Value |
|---|---|
| mean_token_f1 | 1.0000 |

Token F1 definition: Symmetric F1 over the set of unique whitespace-separated tokens of each side, after lowercasing and whitespace normalisation. Punctuation is not stripped and token repetition is ignored. Returns 0.0 when either side has no tokens.

## 7. LLM-as-a-judge

| Field | Value |
|---|---|
| Status | partial |
| Successful calls | 11 |
| Failed calls | 1 |
| judge_accuracy | 1.0000 |
| mean_judge_score | 5.0000 (scale 1-5) |
| Initialisation error | N/A |

## 8. Data quality

| Field | Value |
|---|---|
| Report | baseline_quality.json |
| Overall status | fail |
| Checks | 17 |
| Passed | 16 |
| Warned | 0 |
| Failed | 1 |

| Check | Dimension | Status | Observed | Expected | Affected/Total |
|---|---|---|---|---|---|
| `dataset_not_empty` | completeness | pass | 24 | row_count > 0 | 0/24 |
| `required_columns_present` | validity | pass | (none) | all of ['paper_id', 'title', 'summary', 'text_for_embedding', 'published', 'authors_joined', 'categories_joined', 'abs_url', 'pdf_url', 'age_days'] present | 0/10 |
| `paper_id_not_null` | completeness | pass | 0.0000 | null_rate == 0 | 0/24 |
| `paper_id_not_blank` | completeness | pass | 0.0000 | blank_rate == 0 | 0/24 |
| `paper_id_unique` | uniqueness | pass | 0 | duplicate_count == 0 | 0/24 |
| `title_present` | completeness | pass | 0.0000 | missing_rate <= 0.0 | 0/24 |
| `summary_present` | completeness | pass | 0.0000 | missing_rate <= 0.1 | 0/24 |
| `text_for_embedding_present` | completeness | pass | 0.0000 | missing_rate <= 0.0 | 0/24 |
| `authors_joined_present` | completeness | pass | 0.0000 | missing_rate <= 0.2 | 0/24 |
| `categories_joined_present` | completeness | fail | 1.0000 | missing_rate <= 0.2 | 24/24 |
| `published_parseable` | validity | pass | 0.0000 | unparseable_rate == 0 | 0/24 |
| `age_days_numeric` | validity | pass | 0.0000 | non_numeric_rate == 0 | 0/24 |
| `age_days_not_negative` | validity | pass | 0 | age_days >= -1 | 0/24 |
| `duplicate_rows` | uniqueness | pass | 0 | duplicate_row_count == 0 | 0/24 |
| `abs_url_valid` | validity | pass | 0.0000 | invalid_url_rate <= 0.5 | 0/24 |
| `pdf_url_valid` | validity | pass | 0.0000 | invalid_url_rate <= 0.5 | 0/24 |
| `data_within_freshness_threshold` | freshness | pass | 0.0000 | stale_rate <= 0.5 with age_days <= 180 | 0/24 |

## 9. Freshness

| Field | Value |
|---|---|
| Status | fresh |
| Measured from | published, age_days |
| Threshold (days) | 180 |
| Rows | 24 |
| Stale rows | 0 |
| Rows without a usable date | 0 |
| Rows without a usable age | 0 |
| Latest published | 2026-08-01T00:00:00+00:00 |
| Oldest published | 2026-02-12T00:00:00+00:00 |
| age_days min/mean/max | 5.0000 / 76.5833 / 175.0000 |
| Reason | All 24 row(s) have a usable date and an age within the 180-day threshold (max age 175.0 day(s)). |

## 10. Artifacts

| Artifact | Path |
|---|---|
| Evaluation set | D:\CODE\AITHUCCHIEN\LABS\K3_Day10_Data-Pipeline-Data-Observability\data\eval\test_set.json |
| Dataset | N/A |
| Quality report | D:\CODE\AITHUCCHIEN\LABS\K3_Day10_Data-Pipeline-Data-Observability\data\quality\baseline_quality.json |
| Freshness report | D:\CODE\AITHUCCHIEN\LABS\K3_Day10_Data-Pipeline-Data-Observability\data\quality\freshness_report.json |
| This report | D:\CODE\AITHUCCHIEN\LABS\K3_Day10_Data-Pipeline-Data-Observability\data\reports\phase1_report.md |

## 11. Errors and warnings

### Warnings

_No warning was recorded._

### Errors

- id=summary-10-3390-buildings16132637, stage=judge, error=ValueError: {'message': 'Upstream error from Nvidia: ResourceExhausted: Worker local total request limit reached (33/32)', 'code': 502}

## 12. Limitations

- Metrics describe this dataset, index and evaluation set only; they are not a general statement about the retrieval stack.
- Questions whose title resolves through the exact lookup in `retrieval.qa` bypass semantic ranking, so `retrieval_hit_rate` mixes two retrieval paths. Read `semantic_retrieval_hit_rate` for the semantic signal.
- Token F1 rewards vocabulary overlap, not factual correctness.
- Judge scores, when present, come from a single model at temperature 0 and are not calibrated against human grading.
