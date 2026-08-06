# Group Report — Day 10: Data Pipeline & Data Observability

## 1. Thông tin bài nộp

| Thông tin | Nội dung |
| --- | --- |
| Khóa/Lớp | K3 |
| Tên nhóm | 5 nang cong chua |
| Repository | https://github.com/thieu-nu/K3_Day10_Data-Pipeline-Data-Observability |
| Ngày đối soát | 2026-08-06 |
| Trạng thái release | Chưa release: còn thiếu quality/freshness artifacts và hai report sinh tự động |

### Thành viên và phân công

| STT | Thành viên | MSSV | Vai trò và phạm vi | Input cần nhận | Output bàn giao |
| --: | --- | --- | --- | --- | --- |
| 1 | Trần Hoàng Quân | 2A202601805 | Điều phối pipeline: `src/core/`, `src/pipelines/`, integration và release gate | Raw, clean, index, evaluation và observability artifacts từ các owner | Contract `clean-v1`, quyết định GO/STOP, orchestration và checklist release |
| 2 | Đàm Minh Tuấn | 2A202601169 | Ingestion: `src/ingestion/crossref.py`, Crossref và raw lineage | Settings/source contract | `data/raw/crossref_response.json`, `data/raw/crossref_records.json` |
| 3 | Đinh Huy Mạnh | 2A202601677 | Cleaning & corruption: `src/ingestion/cleaning.py`, `src/ingestion/corruption.py` | Raw snapshot và clean contract | Clean/corrupted/repaired datasets, cleaning summary và corruption log |
| 4 | Lê Minh Khiêm | 2A202601645 | RAG & agent: `src/retrieval/` | Clean snapshot đã qua gate | MiniLM/Chroma collections, manifest, search và lookup |
| 5 | Nguyễn Quang Hưng | 2A202601523 | Evaluation & observability: `src/evaluation/`, `src/observability/` | Clean snapshot, index và test set cố định | Test set, metrics, quality/freshness artifacts và reports |

### Contract và checkpoint tích hợp

| Mốc | Trạng thái | Bằng chứng |
| --- | --- | --- |
| C1 clean gate | **GO** | Raw/clean đều 24; không filter/deduplicate; gate không có blocker |
| `C1-BLOCKER-001` | **RESOLVED** | `data/quality/clean_contract_gate.json` khóa snapshot SHA-256 `a805ea3cce587843cecbe78fafd3727c21c018102c095050f52979c1d5109d0a` |
| `CP2-BLOCKER-001` — test set | **PARTIAL/REPRODUCIBILITY GAP** | `data/eval/test_set.json` đã có 20 sample, nhưng `src/evaluation/testset.py` trên nhánh đang báo cáo vẫn là starter `NotImplementedError` |
| `CP2-BLOCKER-002` — index | **RESOLVED** | Chroma có `papers-baseline`, dimension 384, 24 embeddings; manifest có 24 ID khớp clean |
| `CP3-BLOCKER-001` — observability/report | **OPEN** | Thiếu baseline/corrupted/repaired quality và freshness JSON; thiếu `phase1_report.md` và `corruption_report.md`; code observability hiện còn `NotImplementedError` |

## 2. Tóm tắt kết quả

Nhóm đã hoàn thành chuỗi artifact từ Crossref đến raw, clean, Chroma index, evaluation set, baseline evaluation, corruption và repaired evaluation. Clean contract `clean-v1` xác nhận 24 raw records tạo 24 clean records, không có record bị filter hoặc deduplicate; toàn bộ `paper_id` duy nhất và `text_for_embedding` không rỗng. Test set gồm 20 câu hỏi lấy từ clean corpus và ba trạng thái dùng cùng đúng 20 sample. Corruption làm retrieval hit rate giảm từ 1.00 xuống 0.60, mean token F1 từ 0.2465 xuống 0.1248, judge accuracy từ 0.50 xuống 0.20 và mean judge score từ 3.05 xuống 1.80. Sau repair từ raw, bốn metric trở về đúng mức baseline. Audit trực tiếp dataset cũng cho thấy corrupted data có 23 dòng, chỉ 22 ID duy nhất, 3 summary rỗng và 2 dòng stale; repaired data trở về 24 dòng, 24 ID duy nhất, không summary rỗng và không dòng stale theo ngưỡng 180 ngày. Tuy nhiên chưa thể công bố pipeline hoàn tất: các quality/freshness JSON và hai Markdown report sinh tự động chưa tồn tại, Ragas bị skip, test-set generator và observability code chưa được merge vào phiên bản đang đối soát.

## 3. Kiến trúc và luồng dữ liệu

```text
Crossref API
    -> data/raw/crossref_response.json
    -> data/raw/crossref_records.json
    -> clean-v1 gate
    -> data/clean/papers_clean.{csv,json}
    -> MiniLM + Chroma papers-baseline
    -> data/eval/test_set.json (khóa dùng chung)
    -> baseline answers/metrics
    -> corrupted clean + papers-corrupted + answers/metrics
    -> repair lại từ raw + papers-repaired + answers/metrics
    -> quality/freshness + comparison report (đang bị blocker)
```

| Khối | Input | Xử lý chính | Output | Owner |
| --- | --- | --- | --- | --- |
| Ingestion | Crossref REST API | Query, retry/backoff, parse DOI thành stable `paper_id`, lưu raw response trước parse | Hai JSON trong `data/raw/` | Tuấn |
| Cleaning | Raw `PaperRecord` | Normalize, validate date, filter summary ngắn, deduplicate ID, tính `age_days`, tạo embedding text | Clean CSV/JSON và cleaning summary | Mạnh |
| Embedding/index | Clean snapshot đã qua gate | MiniLM 384 chiều, ba collection Chroma tách biệt | Chroma DB và manifest baseline | Khiêm |
| Evaluation | Test set cố định và collection tương ứng | Retrieval, answer, token F1 và LLM judge | `*_answers.json`, `*_metrics.json` | Hưng |
| Observability | Baseline/corrupted/repaired data | Quality và freshness | Chưa có artifact chính thức | Hưng |
| Orchestration | Tất cả handoff artifact | Gate thứ tự chạy, tách path/collection, dừng khi thiếu evidence | `phase1.py`, `corruption_flow.py`, release decision | Quân |

## 4. Cách tái hiện kết quả

### Cấu hình không chứa secret

| Biến/tham số | Giá trị dùng trong lần đối soát |
| --- | --- |
| `LLM_PROVIDER` | `openrouter` |
| `LLM_MODEL` | `nvidia/nemotron-3-ultra-550b-a55b:free` |
| Credential | Có cấu hình cục bộ; không ghi giá trị vào báo cáo |
| Embedding model | `sentence-transformers/all-MiniLM-L6-v2` |
| Số Crossref records yêu cầu/nhận được | 24/24 |
| Retrieval `top_k` | 4 |
| Freshness threshold | 180 ngày |
| Test set seed | N/A — artifact hiện tại không có metadata seed; dùng SHA-256 file để khóa |

### Lệnh cài đặt và chạy chuẩn

```powershell
python -m uv sync
python -m uv run python script/run_phase1.py
python -m uv run python script/run_corruption_flow.py
```

### Kết quả tái hiện hiện tại

| Flow | Trạng thái | Bằng chứng |
| --- | --- | --- |
| Clean gate | Thành công | `status=GO`, raw/clean 24/24, blocker count 0 |
| Baseline | Thất bại một phần | Có index, test set, answers và metrics; thiếu quality/freshness và `phase1_report.md` |
| Corruption/repair | Thất bại một phần | Có corrupted/repaired clean data, Chroma collections, answers và metrics; thiếu quality/freshness, manifests corrupted/repaired và comparison report |

Không đánh dấu E2E thành công chỉ dựa trên metrics vì các postcondition observability/report chưa đạt.

## 5. Ingestion, cleaning và data contract

### Nguồn dữ liệu

| Thuộc tính | Giá trị |
| --- | --- |
| Source | `https://api.crossref.org/works` |
| Query | `agentic retrieval augmented generation large language model` |
| Filter | `from-pub-date:2026-02-07,has-abstract:true` |
| Raw artifact commit | `7688eeb`, 2026-08-06 11:16:46 +07:00 |
| Số item trong response/parsed records | 24/24 |
| Stable ID | DOI trong field `paper_id` |
| Retry/backoff | Tối đa 5 lần cho 429/500/502/503/504, exponential backoff 1/2/4/8 giây, timeout 20 giây |

### Raw và clean schema

| Dataset | Trường chính | Kiểm tra |
| --- | --- | --- |
| Raw | `paper_id`, `title`, `summary`, `authors`, `categories`, `primary_category`, `published`, `updated`, `abs_url`, `pdf_url`, `comment` | 24 records; truy vết bằng DOI |
| Clean | `paper_id`, `title`, `summary`, `authors_joined`, `categories_joined`, `primary_category`, `published`, `updated`, `age_days`, `summary_chars`, `text_for_embedding`, URL và comment | 24 dòng; 24 ID duy nhất; 0 embedding text rỗng |

### Quy tắc cleaning và audit count

| Quy tắc | Dimension | Kết quả baseline |
| --- | --- | ---: |
| Loại record thiếu `paper_id` hoặc title | Completeness | 0 |
| Loại summary dưới 100 ký tự | Validity | 0 |
| Loại ngày published không hợp lệ | Validity | 0 |
| Deduplicate theo stable `paper_id` | Uniqueness | 0 record bị loại |
| Tạo `text_for_embedding` từ title, authors và summary | Usability | 24/24 không rỗng |

Audit count: `24 raw = 24 clean + 0 filtered + 0 deduplicated`. CSV và JSON cùng thứ tự ID; clean snapshot SHA-256 được lưu trong clean gate.

## 6. Evaluation setup

| Thuộc tính | Giá trị |
| --- | --- |
| Test set | `data/eval/test_set.json` |
| Số câu hỏi | 20 |
| Question types | `authors=5`, `categories=5`, `date=5`, `summary=5` |
| Ground-truth IDs | 20/20 thuộc 24 clean `paper_id` |
| Test set file SHA-256 | `25234e2c8510cb71c65d8546fba0ea1fc0bef93f50555889c5f3410a7b07dffa` |
| Embedding/index | MiniLM, Chroma `papers-baseline`, dimension 384 |
| Retrieval | `top_k=4` |
| LLM judge | OpenRouter; 0/20 fallback rows ở từng trạng thái |
| Ragas | Skipped vì `RUN_RAGAS` chưa bật |

Ba file answers có cùng 20 ID theo cùng thứ tự với test set. Vì vậy baseline, corrupted và repaired được so sánh trên cùng câu hỏi và ground truth; không tái sinh test set từ corrupted data.

## 7. Kết quả baseline

### Artifact checklist

| Artifact | Path | Trạng thái | Ghi chú |
| --- | --- | --- | --- |
| Raw response/records | `data/raw/` | Có | 24 records |
| Cleaned dataset | `data/clean/papers_clean.*` | Có | 24 dòng, gate GO |
| Embedding manifest/index | `data/embeddings/papers_embeddings.json`, `data/chroma/` | Có | `papers-baseline`, 24 vectors |
| Evaluation set | `data/eval/test_set.json` | Có | 20 sample |
| Baseline answers/metrics | `data/results/baseline_{answers,metrics}.json` | Có | 20 answers |
| Baseline quality/freshness | `data/quality/` | Thiếu | Chỉ có clean gate; chưa có official quality/freshness JSON |
| Baseline report | `data/reports/phase1_report.md` | Thiếu | Blocker CP3 |

### Baseline metrics

| Metric | Giá trị | Diễn giải |
| --- | ---: | --- |
| `retrieval_hit_rate` | 1.0000 | 20/20 câu có ground-truth document trong retrieved IDs |
| `mean_token_f1` | 0.2465 | Answer overlap còn thấp dù retrieval hit đầy đủ |
| `judge_accuracy` | 0.5000 | 10/20 answer được judge đánh giá đúng |
| `mean_judge_score` | 3.0500 | Mức trung bình trên thang 1–5 |
| Ragas | N/A | Bị skip; không dùng để kết luận |

## 8. Data quality và freshness

Các số dưới đây là audit trực tiếp từ JSON datasets, chưa thay thế official quality/freshness artifacts.

| Signal | Baseline | Corrupted | Repaired |
| --- | ---: | ---: | ---: |
| Row count | 24 | 23 | 24 |
| Unique `paper_id` | 24 | 22 | 24 |
| Blank summary | 0 | 3 | 0 |
| Duplicate ID groups | 0 | 1 | 0 |
| Stale rows (`age_days > 180`) | 0 | 2 | 0 |
| Maximum `age_days` | 175 | 2300 | 175 |

| Dataset | Latest published | Oldest published | Trạng thái manual |
| --- | --- | --- | --- |
| Baseline | 2026-08-01 | 2026-02-12 | Fresh theo ngưỡng 180 ngày |
| Corrupted | 2026-07-13 | 2020-01-01 | Stale, có 2 dòng vượt ngưỡng |
| Repaired | 2026-08-01 | 2026-02-12 | Trở lại mức baseline |

Official quality/freshness status vẫn là **N/A** vì các JSON tương ứng chưa tồn tại và code `src/observability/quality.py` trên phiên bản hiện tại còn `NotImplementedError`.

## 9. Corruption scenarios và repair

| Corruption | Số lượng/log | Tác động quan sát | Repair |
| --- | --- | --- | --- |
| Drop latest records | 2 | Row count giảm | Re-clean từ raw snapshot |
| Blank summary | Rows 0, 1; audit thấy 3 blank summary tổng cộng | Giảm context trả lời | Khôi phục từ raw |
| Inject noise | Row 2 | Làm nội dung retrieval kém tin cậy | Khôi phục từ raw |
| Truncate title | Row 3 | Có thể làm exact title lookup kém | Khôi phục title từ raw |
| Stale published date | Rows 1, 2 | 2 dòng stale, max age 2300 | Parse lại published từ raw |
| Add duplicate | 1 | 23 rows nhưng chỉ 22 unique IDs | Deduplicate lại khi cleaning |

`data/results/corruption_log.json` ghi original count 24 và corrupted count 23. Repaired dataset được tạo lại từ raw, không sửa tay answers/metrics; row count, uniqueness, blank summary, freshness và bốn metric đều trở về mức baseline.

## 10. So sánh baseline, corrupted và repaired

| Metric/signal | Baseline | Corrupted | Repaired | Delta do corruption | Recovery |
| --- | ---: | ---: | ---: | ---: | ---: |
| `retrieval_hit_rate` | 1.0000 | 0.6000 | 1.0000 | -0.4000 | +0.4000, phục hồi 100% phần mất |
| `mean_token_f1` | 0.2465 | 0.1248 | 0.2465 | -0.1217 | +0.1217, về đúng baseline |
| `judge_accuracy` | 0.5000 | 0.2000 | 0.5000 | -0.3000 | +0.3000, về đúng baseline |
| `mean_judge_score` | 3.0500 | 1.8000 | 3.0500 | -1.2500 | +1.2500, về đúng baseline |
| Manual quality issues | 0 | 3 blank summaries, 1 duplicate group | 0 | Xấu đi rõ ràng | Về mức baseline |
| Manual stale rows | 0 | 2 | 0 | +2 | Về mức baseline |

Hai chuỗi bằng chứng được artifact hỗ trợ:

1. Corruption có log làm mất/biến đổi dữ liệu, tạo blank summary, duplicate và stale rows → retrieval hit giảm 40 điểm phần trăm, answer metrics và judge metrics cùng giảm.
2. Re-clean từ đúng raw snapshot → cấu trúc/freshness manual trở về baseline → bốn metric repaired trùng baseline.

Không thể quy toàn bộ mức giảm cho riêng một corruption vì nhiều corruption được áp dụng đồng thời; cần ablation từng scenario nếu muốn kết luận nhân quả chi tiết hơn. Chưa công bố recovery hoàn chỉnh theo tiêu chí release cho tới khi official quality/freshness và comparison report tồn tại.

## 11. Vấn đề tích hợp quan trọng

- **Triệu chứng:** Metrics và answers tồn tại nhưng pipeline hiện tại không tái lập được toàn bộ report/observability; `phase1_report.md` và `corruption_report.md` thiếu.
- **Nguyên nhân:** `src/evaluation/testset.py`, `src/observability/quality.py` và `src/observability/reporting.py` trên nhánh đang đối soát vẫn chứa `NotImplementedError`; code mới của owner chưa được merge đồng bộ với latest main.
- **Xử lý của Quân:** Giữ release gate đóng, ghi blocker có evidence, không sửa logic module của owner khác và không tô đẹp trạng thái E2E.
- **Cách xác minh:** Kiểm tra code bằng `rg -n "TODO|NotImplementedError" ...`; kiểm tra artifact bằng `Test-Path`; đối chiếu trực tiếp JSON/SQLite.

Một vấn đề portability của Chroma manifest đã được Khiêm sửa: `persist_path` hiện là `data/chroma` thay vì absolute machine path.

## 12. Giới hạn và hướng cải thiện

| Giới hạn | Ảnh hưởng | Đề xuất |
| --- | --- | --- |
| Test-set generator chưa có trên nhánh báo cáo | Artifact test set chưa tái sinh được từ code hiện tại | Merge code owner sau review và lưu metadata seed/fingerprint |
| Thiếu quality/freshness JSON và Markdown reports | Chưa đạt CP3/CP6 và chưa đủ evidence release | Hoàn thiện/merge observability, chạy lại và đối chiếu report với JSON |
| Thiếu corrupted/repaired embedding manifests | Ba collections có trong Chroma nhưng lineage index chưa đầy đủ | Lưu manifest riêng cho `papers-corrupted` và `papers-repaired` |
| Ragas bị skip | Thiếu nhóm metric Ragas | Chỉ bật khi môi trường/provider ổn định và ghi rõ chi phí/run config |
| Corruption gộp nhiều scenario | Không tách được tác động của từng lỗi | Chạy ablation từng corruption trên cùng test set |

## 13. Checklist trước khi nộp

- [x] Thông tin nhóm, repository, vai trò và output đã được điền.
- [x] Phân công khớp với module và artifact hiện có.
- [ ] Lệnh E2E đã chạy lại thành công trên đúng phiên bản dùng để nộp.
- [x] Baseline, corrupted và repaired dùng cùng 20 test sample.
- [x] Bảng metrics khớp các JSON trong `data/results/`.
- [ ] Official quality/freshness conclusions khớp artifact vì artifact chưa tồn tại.
- [ ] `phase1_report.md` và `corruption_report.md` truy cập được.
- [ ] Đủ báo cáo cá nhân của cả năm thành viên.
- [x] `.env` được ignore; báo cáo không chứa API key/token/secret.

**Release decision của Quân:** **HOLD** cho tới khi các mục chưa đạt ở trên được giải quyết và kiểm chứng bằng artifact mới.
