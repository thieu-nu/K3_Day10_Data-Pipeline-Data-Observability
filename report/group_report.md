# Group Report — Day 10: Data Pipeline & Data Observability

> Dùng mẫu này cho báo cáo chung của nhóm 3–5 thành viên. Thay toàn bộ nội dung trong dấu `[ ]` bằng thông tin và kết quả thực tế. Xóa các dòng hướng dẫn không còn cần thiết trước khi nộp.

## 1. Thông tin bài nộp

| Thông tin       | Nội dung                                                              |
| --------------- | --------------------------------------------------------------------- |
| Khóa/Lớp        | K3                                                                    |
| Tên nhóm        | 5 nang cong chua                                                      |
| Repository      | https://github.com/thieu-nu/K3_Day10_Data-Pipeline-Data-Observability |
| Ngày hoàn thành | 2026-08-06                                                            |

### Thành viên và phân công

| STT | Thành viên | MSSV | Vai trò chính và phạm vi sở hữu | Artifact/điều kiện phải có trước phần việc phụ thuộc | Output bàn giao (tên file/contract) | Người nhận trực tiếp |
| --: | --- | --- | --- | --- | --- | --- |
| 1 | Trần Hoàng Quân | 2A202601805 | **VAI TRÒ 1 — Điều phối pipeline:** cấu hình, orchestration, release; sở hữu `src/core/config.py`, `src/core/clean_contract.py`, `src/pipelines/phase1.py`, `src/pipelines/corruption_flow.py` và các entrypoint trong `script/`. Không sửa logic nghiệp vụ thuộc module của thành viên khác. | Trước khi tích hợp/release: contract đường dẫn đã thống nhất; raw snapshot của Tuấn; clean artifacts kèm audit count của Mạnh; index manifest của Khiêm; metrics/quality/report của Hưng. Riêng tại C1, cần `data/raw/crossref_records.json` và bộ clean của Mạnh để reconcile count. | Contract `clean-v1`; gate code và evidence `data/quality/clean_contract_gate.json`; quyết định **GO/STOP**; pipeline entrypoints; checklist/artifacts tích hợp để release. | Hưng nhận run artifacts/evidence để đối soát metrics và report; cả nhóm nhận bản release đã qua gate. |
| 2 | Đàm Minh Tuấn | 2A202601169 | **VAI TRÒ 2 — Ingestion:** Crossref và raw lineage; sở hữu `src/ingestion/crossref.py`. | `Settings`/artifact paths trong `src/core/config.py`, schema `PaperRecord` và quy tắc `paper_id` ổn định đã được Quân chốt. | `data/raw/crossref_response.json`, `data/raw/crossref_records.json`; raw count, query/timestamp nguồn và một sample lineage có thể truy vết. | Mạnh nhận raw records để cleaning; Quân nhận raw count/path để orchestration và kiểm tra gate; Hưng dùng lineage làm evidence. |
| 3 | Đinh Huy Mạnh | 2A202601677 | **VAI TRÒ 3 — Cleaning & corruption:** clean schema, corruption, repair; sở hữu `src/ingestion/cleaning.py` và `src/ingestion/corruption.py`. | Hai raw artifacts của Tuấn đọc được và đúng `PaperRecord`; contract `clean-v1` của Quân đã chốt. | Baseline: `data/clean/papers_clean.csv`, `data/clean/papers_clean.json`, `data/clean/cleaning_summary.json`. Giai đoạn sau: các file `papers_clean_corrupted.*`, `papers_clean_repaired.*` và `data/results/corruption_log.json`. | Khiêm nhận clean data để index; Hưng nhận clean data/audit để tạo test set và quality checks; Quân nhận toàn bộ handoff để mở gate tích hợp. |
| 4 | Lê Minh Khiêm | 2A202601645 | **VAI TRÒ 4 — RAG & agent:** MiniLM, Chroma, semantic search, exact lookup và agent; sở hữu `src/retrieval/`. | Quân xác nhận clean gate **GO**: schema ổn định, `paper_id` duy nhất, `text_for_embedding` hợp lệ và count đã reconcile. | `data/embeddings/papers_embeddings.json`, collection `papers-baseline` trong `data/chroma/`, search/lookup/agent; sau đó là manifest và collection riêng cho corrupted/repaired. | Hưng nhận index để evaluation; Quân nhận manifest/collection metadata để orchestration và release. |
| 5 | Nguyễn Quang Hưng | 2A202601523 | **VAI TRÒ 5 — Evaluation & observability:** test set, metrics, quality, freshness và reports; sở hữu `src/evaluation/` và `src/observability/`. | Clean gate **GO** để tạo test set; index/manifest đúng collection từ Khiêm để evaluate. Cùng một test set phải được giữ nguyên cho baseline/corrupted/repaired. | `data/eval/test_set.json`; `data/results/*_metrics.json`, `data/results/*_answers.json`; artifacts trong `data/quality/`; `data/reports/phase1_report.md` và `data/reports/corruption_report.md`. | Quân nhận metrics/quality/report để quyết định release; cả nhóm nhận evidence để kết luận và demo. |

#### Clean contract C1 do Quân chốt

| Hạng mục                        | Contract `clean-v1`                                                                                                                                                                                                                                                                                                       |
| ------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Input hàm                       | `build_clean_dataframe(records: list[PaperRecord], run_date: datetime) -> pd.DataFrame`.                                                                                                                                                                                                                                  |
| Input lưu trên đĩa              | `data/raw/crossref_records.json`; lineage đối chiếu qua `data/raw/crossref_response.json`. Mỗi raw record có các field: `paper_id`, `title`, `summary`, `authors`, `categories`, `primary_category`, `published`, `updated`, `abs_url`, `pdf_url`, `comment`.                                                             |
| Output bắt buộc                 | `data/clean/papers_clean.csv` và `data/clean/papers_clean.json`; hai file phải đọc được, có cùng số dòng và cùng các cột bắt buộc.                                                                                                                                                                                        |
| Schema tối thiểu cho downstream | `paper_id: str` duy nhất/không rỗng; `title: str`, `summary: str`, `text_for_embedding: str` không rỗng; `published` là ngày ISO hợp lệ; `age_days: int >= 0`; có các cột `authors_joined`, `categories_joined`, `summary_chars`, `abs_url`, `pdf_url`.                                                                   |
| Audit count bắt buộc            | Mạnh gắn audit vào `df.attrs["cleaning_summary"]`; orchestration ghi `data/clean/cleaning_summary.json` theo schema: `contract_version`, `raw_count`, `filtered_count`, `deduplicated_count`, `clean_count`, `reason_counts.filtered`, `reason_counts.deduplicated`. Tổng từng nhóm reason phải bằng aggregate tương ứng và `raw_count = clean_count + filtered_count + deduplicated_count`. |
| Điều kiện **GO**                | Năm raw/clean/audit artifacts đều tồn tại và đọc được; CSV/JSON có cùng count và thứ tự `paper_id`; clean ID truy vết được về raw; `raw_count > 0`; `0 < clean_count <= raw_count`; audit count khớp; schema tối thiểu hợp lệ; ID duy nhất; text/date/age hợp lệ. Gate lưu SHA-256 snapshot clean. |
| Điều kiện **STOP**              | Thiếu/malformed artifact hoặc cột; CSV/JSON lệch snapshot; count/reason không khớp; clean ID không có trong raw; `paper_id` null/trùng; `text_for_embedding` rỗng; `published`/`age_days` sai. `enforce_clean_contract` ghi `data/quality/clean_contract_gate.json` rồi raise `CleanContractError`; **không gọi** `build_test_set` hay `LocalEmbeddingIndex.build`. |
| Handoff sau khi **GO**          | `_build_index_and_test_set_after_gate` chỉ nhận snapshot do gate xác thực rồi mới gọi index/test set. Cùng snapshot và SHA-256 được bàn giao cho Khiêm (index), Hưng (test set/quality) và Quân (evidence tích hợp). |

#### Đối chiếu raw count → clean count tại C1

| Blocker          | Quan sát thực tế                                                                                                                                | Bằng chứng trong repository                                                                                                                                                                                                                                | Quyết định và điều kiện gỡ                                                                                                                                                                                                                               |
| ---------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `C1-BLOCKER-001` — **RESOLVED** | `raw_count = 24`, `clean_csv_count = 24`, `clean_json_count = 24`, `filtered_count = 0`, `deduplicated_count = 0`; phương trình audit `24 = 24 + 0 + 0` khớp. | `data/quality/clean_contract_gate.json` ghi contract `clean-v1`, trạng thái **GO**, không có blocker và khóa clean snapshot bằng SHA-256 `a805ea3cce587843cecbe78fafd3727c21c018102c095050f52979c1d5109d0a`. | Gate **OPEN**. Khóa snapshot clean này và bàn giao cùng hash cho Khiêm tạo index, Hưng tạo test set; không refresh source trong lúc dựng baseline. |

#### Blocker handoff clean → test set/index tại CP2

| Blocker | Owner | Quan sát thực tế | Bằng chứng trong repository | Quyết định và điều kiện gỡ |
| --- | --- | --- | --- | --- |
| `CP2-BLOCKER-001` | Hưng — Evaluation & observability | Chưa thể tạo/load test set cho baseline; `data/eval/test_set.json` chưa tồn tại. | `src/evaluation/testset.py` vẫn chứa `TODO(student)` và raise `NotImplementedError`; `data/eval/` mới chỉ có `.gitkeep`. | Chưa chạy `_build_index_and_test_set_after_gate` hoặc baseline E2E. Hưng hoàn thiện `build_test_set`, tạo `data/eval/test_set.json` từ đúng clean snapshot SHA-256 `a805ea3cce587843cecbe78fafd3727c21c018102c095050f52979c1d5109d0a`, rồi xác minh mọi `ground_truth_doc_ids` thuộc 24 `paper_id` clean. |
| `CP2-BLOCKER-002` | Khiêm — RAG & agent | Baseline embedding manifest và Chroma collection chưa tồn tại; semantic search/exact lookup/agent chưa có run evidence. | `data/embeddings/` và `data/chroma/` mới chỉ có `.gitkeep`; collection đã được cấu hình là `papers-baseline`, manifest mục tiêu là `data/embeddings/papers_embeddings.json`. | Khiêm build `papers-baseline` từ cùng clean snapshot, xác minh collection có 24 documents và bàn giao manifest; semantic search, exact lookup và agent phải trả kết quả có nguồn. Quân chỉ mở baseline E2E sau khi cả hai blocker CP2 được gỡ. |

## 2. Tóm tắt kết quả

Viết từ 150–250 từ, trả lời ngắn gọn:

- Nhóm đã hoàn thành những phần nào?
- Baseline pipeline đã tạo ra các artifact nào?
- Corruption nào ảnh hưởng rõ nhất đến data quality hoặc agent?
- Repair đã phục hồi được chỉ số nào?
- Blocker hoặc giới hạn quan trọng nhất còn lại là gì?

**Tóm tắt của nhóm:**

[Viết phần tóm tắt tại đây.]

## 3. Kiến trúc và luồng dữ liệu

### Luồng end-to-end

Điều chỉnh sơ đồ dưới đây nếu cách triển khai thực tế của nhóm khác starter:

```text
Crossref API
    -> raw response/raw records
    -> cleaning và data modeling
    -> embedding + ChromaDB index
    -> evaluation baseline
    -> quality/freshness reports
    -> corruption
    -> re-index và re-evaluate
    -> repair từ dữ liệu nguồn
    -> comparison report
```

### Trách nhiệm của từng khối

| Khối              | Input         | Xử lý chính                | Output/artifact      | Owner        |
| ----------------- | ------------- | -------------------------- | -------------------- | ------------ |
| Ingestion         | [Nguồn/input] | [Fetch, retry, parse...]   | [Đường dẫn artifact] | [Thành viên] |
| Cleaning          | [Input]       | [Các quy tắc chính]        | [Đường dẫn artifact] | [Thành viên] |
| Embedding/index   | [Input]       | [Model/index config]       | [Đường dẫn artifact] | [Thành viên] |
| Evaluation        | [Input]       | [Test set và metrics]      | [Đường dẫn artifact] | [Thành viên] |
| Observability     | [Input]       | [Quality/freshness checks] | [Đường dẫn artifact] | [Thành viên] |
| Corruption/repair | [Input]       | [Corruption và repair]     | [Đường dẫn artifact] | [Thành viên] |
| Orchestration     | [Input]       | [Thứ tự chạy]              | [Reports/metrics]    | [Thành viên] |

## 4. Cách tái hiện kết quả

### Cấu hình không chứa secret

| Biến/cấu hình             | Giá trị sử dụng |
| ------------------------- | --------------- |
| `LLM_PROVIDER`            | [Giá trị]       |
| `LLM_MODEL`               | [Giá trị]       |
| Embedding model           | [Giá trị]       |
| Số lượng Crossref records | [Giá trị]       |
| Retrieval`top_k`          | [Giá trị]       |
| Freshness threshold       | [Giá trị]       |
| Random seed, nếu có       | [Giá trị]       |

Không dán nội dung API key hoặc file `.env` vào báo cáo.

### Lệnh cài đặt

Chỉ giữ lại cách nhóm đã dùng.

```bash
uv sync
```

Hoặc:

```bash
python -m pip install -e .
```

### Lệnh chạy

Baseline:

```bash
uv run python script/run_phase1.py
```

Hoặc với môi trường `pip` đã kích hoạt:

```bash
python script/run_phase1.py
```

Corruption flow:

```bash
uv run python script/run_corruption_flow.py
```

Hoặc với môi trường `pip` đã kích hoạt:

```bash
python script/run_corruption_flow.py
```

### Kết quả tái hiện

| Lệnh              | Trạng thái                              | Thời điểm chạy gần nhất | Bằng chứng                        |
| ----------------- | --------------------------------------- | ----------------------- | --------------------------------- |
| Baseline pipeline | [Thành công/Thất bại một phần/Thất bại] | [Thời gian]             | [Artifact hoặc log đã che secret] |
| Corruption flow   | [Thành công/Thất bại một phần/Thất bại] | [Thời gian]             | [Artifact hoặc log đã che secret] |

## 5. Ingestion, cleaning và data contract

### Nguồn dữ liệu

| Thuộc tính            | Giá trị                             |
| --------------------- | ----------------------------------- |
| Source                | [Crossref endpoint/dataset thực tế] |
| Query/filter          | [Query hoặc filter]                 |
| Thời điểm lấy dữ liệu | [Timestamp]                         |
| Số record nhận được   | [Số lượng]                          |
| Cơ chế retry/backoff  | [Mô tả ngắn]                        |

### Raw và clean schema

| Trường       | Kiểu dữ liệu | Bắt buộc?  | Ý nghĩa   | Xử lý khi thiếu/sai |
| ------------ | ------------ | ---------- | --------- | ------------------- |
| [Tên trường] | [Kiểu]       | [Có/Không] | [Ý nghĩa] | [Cách xử lý]        |
| [Tên trường] | [Kiểu]       | [Có/Không] | [Ý nghĩa] | [Cách xử lý]        |

### Quy tắc cleaning

| Quy tắc                             | Quality dimension liên quan | Số record bị tác động | Cách xác minh       |
| ----------------------------------- | --------------------------- | --------------------: | ------------------- |
| [Ví dụ: loại record không có title] | [Completeness/Validity/...] |            [Số lượng] | [Artifact/kiểm tra] |
| [Quy tắc thực tế]                   | [Dimension]                 |            [Số lượng] | [Artifact/kiểm tra] |

Giải thích cách nhóm tạo `text_for_embedding`, document ID và `age_days`:

- Document ID giữ nguyên từ `PaperRecord.paper_id` (DOI) xuyên suốt raw → clean → index → evaluation; cleaning không sinh ID mới.
- `text_for_embedding` có format cố định: `Title: {title} | Authors: {authors_joined} | Summary: {summary}`.
- `age_days = max(0, (run_date.date() - published_date).days)`. `run_date` phải timezone-aware hoặc được chuẩn hóa nhất quán trước khi tính.
- Khi trùng `paper_id`, giữ record hợp lệ xuất hiện đầu tiên để kết quả deterministic; không merge âm thầm các nội dung khác nhau.
- Contract và sample validation của Vai trò 3 được ghi tại `report/cp0_role3_cleaning_contract.md` và `script/validate_cleaning_sample.py`.

## 6. Evaluation setup

| Thành phần                            | Cấu hình thực tế         |
| ------------------------------------- | ------------------------ |
| Số câu hỏi                            | [Số lượng]               |
| Các`question_type`                    | [Danh sách]              |
| Ground-truth document ID              | [Cách tạo/đối chiếu]     |
| Embedding model                       | [Tên model]              |
| Vector store/collection               | [Tên/config]             |
| Retrieval`top_k`                      | [Giá trị]                |
| LLM provider/model                    | [Giá trị]                |
| Test set dùng chung cho ba trạng thái | [Đường dẫn hoặc ID/hash] |

Giải thích vì sao test set được giữ nguyên khi đánh giá baseline, corrupted và repaired:

[Giải thích tại đây.]

## 7. Kết quả baseline

### Artifact checklist

| Artifact                 | Đường dẫn thực tế                    | Trạng thái | Ghi chú   |
| ------------------------ | ------------------------------------ | ---------- | --------- |
| Raw response/records     | `data/raw/`                          | [Có/Thiếu] | [Ghi chú] |
| Cleaned dataset          | `data/clean/`                        | [Có/Thiếu] | [Ghi chú] |
| Embedding manifest/index | `data/embeddings/`                   | [Có/Thiếu] | [Ghi chú] |
| Evaluation set           | `data/eval/`                         | [Có/Thiếu] | [Ghi chú] |
| Baseline metrics         | `data/results/baseline_metrics.json` | [Có/Thiếu] | [Ghi chú] |
| Quality/freshness        | `data/quality/`                      | [Có/Thiếu] | [Ghi chú] |
| Baseline report          | `data/reports/phase1_report.md`      | [Có/Thiếu] | [Ghi chú] |

### Baseline metrics

| Metric               |       Giá trị | Diễn giải                         |
| -------------------- | ------------: | --------------------------------- |
| `retrieval_hit_rate` |     [Giá trị] | [Ý nghĩa trong kết quả của nhóm]  |
| `mean_token_f1`      |     [Giá trị] | [Diễn giải]                       |
| `judge_accuracy`     |     [Giá trị] | [Diễn giải]                       |
| `mean_judge_score`   |     [Giá trị] | [Diễn giải]                       |
| Ragas, nếu có        | [Giá trị/N/A] | [Diễn giải hoặc lý do không chạy] |

## 8. Data quality và freshness

### Quality checks

| Check       | Quality dimension | Ngưỡng/kỳ vọng | Kết quả baseline      | Bằng chứng |
| ----------- | ----------------- | -------------- | --------------------- | ---------- |
| [Tên check] | [Dimension]       | [Ngưỡng]       | [Pass/Fail + giá trị] | [Artifact] |
| [Tên check] | [Dimension]       | [Ngưỡng]       | [Pass/Fail + giá trị] | [Artifact] |

### Freshness

| Thuộc tính            | Giá trị                       |
| --------------------- | ----------------------------- |
| Freshness được đo tại | [Dataset/index/artifact]      |
| Timestamp mới nhất    | [Giá trị]                     |
| Ngưỡng freshness      | [Giá trị]                     |
| Trạng thái baseline   | [Fresh/Stale/Unknown]         |
| Lý do                 | [Giải thích dựa trên số liệu] |

## 9. Corruption scenarios và repair

| Corruption        | Cách tạo | Record bị tác động | Quality signal kỳ vọng | Tác động thực tế  | Cách repair   |
| ----------------- | -------- | -----------------: | ---------------------- | ----------------- | ------------- |
| [Loại corruption] | [Mô tả]  |         [Số lượng] | [Kỳ vọng]              | [Artifact/metric] | [Cách repair] |
| [Loại corruption] | [Mô tả]  |         [Số lượng] | [Kỳ vọng]              | [Artifact/metric] | [Cách repair] |

Corruption log:

- Đường dẫn: `data/results/corruption_log.json`
- Trạng thái: [Có/Thiếu]
- Nhận xét: [Log có đủ loại corruption, record bị tác động và tham số hay không?]

Giải thích cách repair đảm bảo dữ liệu được phục hồi từ nguồn đáng tin cậy thay vì chỉ che kết quả lỗi:

[Giải thích tại đây.]

## 10. So sánh baseline, corrupted và repaired

| Metric/signal            | Baseline | Corrupted | Repaired | Thay đổi do corruption | Mức phục hồi | Nhận xét   |
| ------------------------ | -------: | --------: | -------: | ---------------------: | -----------: | ---------- |
| `retrieval_hit_rate`     |      [ ] |       [ ] |      [ ] |                    [ ] |          [ ] | [Nhận xét] |
| `mean_token_f1`          |      [ ] |       [ ] |      [ ] |                    [ ] |          [ ] | [Nhận xét] |
| `judge_accuracy`         |      [ ] |       [ ] |      [ ] |                    [ ] |          [ ] | [Nhận xét] |
| `mean_judge_score`       |      [ ] |       [ ] |      [ ] |                    [ ] |          [ ] | [Nhận xét] |
| Quality checks pass/fail |      [ ] |       [ ] |      [ ] |                    [ ] |          [ ] | [Nhận xét] |
| Freshness status         |      [ ] |       [ ] |      [ ] |                    [ ] |          [ ] | [Nhận xét] |

Nêu ít nhất hai kết luận có quan hệ nhân quả được hỗ trợ bởi artifacts:

1. [Corruption/data change] → [quality/freshness signal] → [retrieval/answer metric].
2. [Repair action] → [quality/freshness recovery] → [agent metric recovery hoặc lý do chưa recovery].

Không kết luận corruption “có tác động” nếu số liệu không cho thấy thay đổi. Nếu kết quả khác kỳ vọng, mô tả giả thuyết và cách nhóm đã kiểm tra.

## 11. Vấn đề tích hợp quan trọng

Mô tả một vấn đề phát sinh khi ghép các module trong pipeline và cách nhóm xử lý:

- **Triệu chứng:** [Lỗi hoặc kết quả sai.]
- **Nguyên nhân:** [Root cause.]
- **Cách xử lý:** [Thay đổi đã thực hiện.]
- **Cách xác minh:** [Lệnh và artifact.]

## 12. Giới hạn và hướng cải thiện

| Giới hạn hiện tại | Ảnh hưởng   | Hướng cải thiện có thể kiểm chứng |
| ----------------- | ----------- | --------------------------------- |
| [Giới hạn]        | [Ảnh hưởng] | [Đề xuất]                         |
| [Giới hạn]        | [Ảnh hưởng] | [Đề xuất]                         |

## 13. Checklist trước khi nộp

- [ ] Thông tin nhóm và repository chính xác.
- [ ] Phân công khớp với module, artifact và kết quả thực tế.
- [ ] Lệnh tái hiện đã được chạy lại trên phiên bản dùng để nộp.
- [ ] Baseline, corrupted và repaired dùng cùng evaluation set.
- [ ] Bảng metrics khớp với các file trong `data/results/`.
- [ ] Quality/freshness conclusions khớp với `data/quality/`.
- [ ] Các đường dẫn báo cáo và artifact truy cập được.
- [ ] Mỗi thành viên đã hoàn thành báo cáo vai trò riêng.
- [ ] Không có `.env`, API key, token hoặc secret trong source, report, log hay ảnh.
