# Corruption Impact Report

Generated at: 2026-08-06T05:19:21.286943+00:00
States covered: baseline, corrupted, repaired

## 1. Run identity

| Field | Baseline | Corrupted | Repaired |
|---|---|---|---|
| Evaluation set fingerprint | `a9eb111d8faaa7ebc6ced787215d72133d8fb1eaf784800c92d5c06296844279` | `a9eb111d8faaa7ebc6ced787215d72133d8fb1eaf784800c92d5c06296844279` | `a9eb111d8faaa7ebc6ced787215d72133d8fb1eaf784800c92d5c06296844279` |
| Evaluation set path | D:\CODE\AITHUCCHIEN\LABS\K3_Day10_Data-Pipeline-Data-Observability\data\eval\test_set.json | D:\CODE\AITHUCCHIEN\LABS\K3_Day10_Data-Pipeline-Data-Observability\data\eval\test_set.json | D:\CODE\AITHUCCHIEN\LABS\K3_Day10_Data-Pipeline-Data-Observability\data\eval\test_set.json |
| Dataset | N/A | D:\CODE\AITHUCCHIEN\LABS\K3_Day10_Data-Pipeline-Data-Observability\data\clean\papers_clean_corrupted.csv | D:\CODE\AITHUCCHIEN\LABS\K3_Day10_Data-Pipeline-Data-Observability\data\clean\papers_clean_repaired.csv |
| Collection | papers-baseline | papers-corrupted | papers-repaired |
| Documents indexed | 24 | 23 | 24 |
| Provider / model | openrouter / nvidia/nemotron-3-ultra-550b-a55b:free | openrouter / nvidia/nemotron-3-ultra-550b-a55b:free | openrouter / nvidia/nemotron-3-ultra-550b-a55b:free |
| Embedding model | sentence-transformers/all-MiniLM-L6-v2 | sentence-transformers/all-MiniLM-L6-v2 | sentence-transformers/all-MiniLM-L6-v2 |
| top_k | 4 | 4 | 4 |

All states were evaluated against the same locked evaluation set.

## 2. Comparison

| Metric/signal | Baseline | Corrupted | Repaired | Corruption delta | Recovery | Note |
|---|---|---|---|---|---|---|
| retrieval_hit_rate | 1.0000 | 0.9167 | 1.0000 | -0.0833 | +0.0833 | degraded |
| semantic_retrieval_hit_rate | 1.0000 | 0.7500 | 1.0000 | -0.2500 | +0.2500 | WARNING different denominators (baseline n=3, corrupted n=4); route membership shifted, so this delta is not a like-for-like comparison; degraded |
| exact_lookup_success_rate | 1.0000 | 1.0000 | 1.0000 | +0.0000 | +0.0000 | unchanged |
| mean_token_f1 | 1.0000 | 0.6667 | 1.0000 | -0.3333 | +0.3333 | degraded |
| judge_accuracy | 1.0000 | 0.6667 | 1.0000 | -0.3333 | +0.3333 | degraded |
| mean_judge_score | 5.0000 | 3.7500 | 5.0000 | -1.2500 | +1.2500 | degraded |
| quality status | fail | fail | fail | - | - | unchanged |
| freshness status | fresh | stale | fresh | - | - | fresh -> stale |

Corruption delta is `corrupted - baseline`; recovery is `repaired - corrupted`. A null metric stays N/A and is never treated as 0.

## 3. Semantic retrieval, split by how the route was reached

`semantic_topic` questions never carry a quoted title, so they stay on the semantic route in every state and keep a stable denominator. The route-derived semantic slice in section 2 also absorbs questions whose quoted title stopped resolving, which is itself a corruption signal but moves the denominator.

| Slice | Baseline | Corrupted | Repaired |
|---|---|---|---|
| semantic_topic hit rate (fixed set) | 1.0000 | 1.0000 | 1.0000 |
| semantic_topic samples | 3 | 3 | 3 |
| route = exact_lookup | 9 | 8 | 9 |
| route = semantic_search | 3 | 4 | 3 |

1 question(s) that resolved through the exact lookup at baseline no longer do so after corruption, which is consistent with titles being altered.

## 4. Quality and freshness detail

| Signal | Baseline | Corrupted | Repaired |
|---|---|---|---|
| quality overall_status | fail | fail | fail |
| quality failed checks | 1 | 4 | 1 |
| quality dataset rows | 24 | 23 | 24 |
| freshness status | fresh | stale | fresh |
| stale rows | 0 | 3 | 0 |
| oldest published | 2026-02-12T00:00:00+00:00 | 2020-02-04T00:00:00+00:00 | 2026-02-12T00:00:00+00:00 |
| max age_days | 175.0000 | 2375.0000 | 175.0000 |

Corrupted-state checks that did not pass:

| Check | Dimension | Status | Observed | Affected/Total |
|---|---|---|---|---|
| `paper_id_unique` | uniqueness | fail | 2 | 2/23 |
| `summary_present` | completeness | fail | 0.1304 | 3/23 |
| `categories_joined_present` | completeness | fail | 1.0000 | 23/23 |
| `duplicate_rows` | uniqueness | fail | 2 | 2/23 |
| `data_within_freshness_threshold` | freshness | warning | 0.1304 | 3/23 |

## 5. Degradation evidence

4 question(s) got worse. The most affected one:

| Field | Baseline | Corrupted |
|---|---|---|
| Sample id | `date-10-1111-exsy-70341` |  |
| Question type | date |  |
| Question | When was the paper titled 'Hi‐ RAG : A Hierarchical Retrieval‐Augmented Generation Framework for Scalable and Generalisable Tool Selection in Large Language Model Agents' published? |  |
| Ground truth doc ids | 10.1111/exsy.70341 |  |
| Retrieved doc ids | 10.1111/exsy.70341, 10.63646/kpqm1958, 10.36227/techrxiv.177272838.89432844/v1, 10.20944/preprints202604.0339.v1 | 10.55041/isjem07213, 10.63646/kpqm1958, 10.36227/techrxiv.177272838.89432844/v1, 10.70121/001c.158711 |
| Retrieval hit | yes | no |
| Hit rank | 1 | N/A |
| Route | exact_lookup | semantic_search |
| token_f1 | 1.0000 | 0.0000 |
| Judge score | 5 | 2 |

Signals detected: retrieval hit lost; token F1 1.0000 -> 0.0000; exact lookup no longer resolves; fell back to semantic search; judge score 5 -> 2.

Matching corruption-log entries for this question's ground-truth documents:

| paper_id | Corruption record |
|---|---|
| `10.1111/exsy.70341` | corruption_type=drop_latest_records, affected_field=row |

All degraded questions:

| Sample id | Type | Signals |
|---|---|---|
| `date-10-1111-exsy-70341` | date | retrieval hit lost; token F1 1.0000 -> 0.0000; exact lookup no longer resolves; fell back to semantic search; judge score 5 -> 2 |
| `semantic_topic-10-35314-3y9hy151` | semantic_topic | hit rank 1 -> 2; token F1 1.0000 -> 0.0000; answer became empty; judge score 5 -> 1 |
| `semantic_topic-10-55041-isjem07213` | semantic_topic | token F1 1.0000 -> 0.0000; answer became empty; judge score 5 -> 1 |
| `summary-10-1093-sleep-zsag091-0346` | summary | token F1 1.0000 -> 0.0000; answer became empty; judge score 5 -> 1 |

## 6. Evidence chain

corruption -> observability signal moved (quality changed: no, freshness changed: yes) -> at least one retrieval/answer metric moved. The chain holds on this evaluation set.

## 7. Limitations

- Conclusions cover this corpus, this evaluation set and this top_k only.
- A metric moving alongside a corruption is evidence of association; causation is claimed only where a corruption-log record matches the affected document.
- Judge metrics are compared only where both states produced a real judge verdict; token overlap is never substituted for a missing judge score.
- `retrieval_hit_rate` blends the exact-lookup and semantic routes; read section 3 before attributing a change to embedding quality.

### Baseline warnings

_No warning was recorded._

### Corrupted warnings

_No warning was recorded._

### Repaired warnings

_No warning was recorded._
