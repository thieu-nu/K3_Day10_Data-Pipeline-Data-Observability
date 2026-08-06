# Member Role Report — Trần Hoàng Quân — Day 10: Data Pipeline & Data Observability

## 1. Thông tin cá nhân

| Thông tin | Nội dung |
| --- | --- |
| Họ và tên | Trần Hoàng Quân |
| MSSV | 2A202601805 |
| Khóa/Lớp | K3 |
| Tên nhóm | 5 nang cong chua |
| Vai trò chính | VAI TRÒ 1 — Điều phối pipeline: cấu hình, orchestration, release |
| Phạm vi code | `src/core/`, `src/pipelines/` |
| Repository | https://github.com/thieu-nu/K3_Day10_Data-Pipeline-Data-Observability |
| Ngày đối soát | 2026-08-06 |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Deliverable | File/hàm phụ trách | Input | Output | Trạng thái |
| --- | --- | --- | --- | --- |
| Cấu hình và artifact paths | `src/core/config.py` | Quy ước artifact của năm owner | Baseline/corrupted/repaired paths và ba collection riêng | Hoàn thành cấu hình; đã xác minh manifest baseline dùng path portable |
| Clean contract và gate | `src/core/clean_contract.py` | Raw response, raw records, clean CSV/JSON và cleaning summary | `clean-v1`, GO/STOP report, count/schema/lineage và clean SHA-256 | Hoàn thành; gate hiện **GO**, 24 raw/24 clean, 0 blocker |
| Baseline orchestration | `src/pipelines/phase1.py` | Raw → clean → gate → index → test set → evaluation → observability/report | Baseline flow có fail-closed handoff | Code orchestration đã có; E2E chưa được release vì observability/report artifacts thiếu |
| Corruption orchestration/release | `src/pipelines/corruption_flow.py`, release checklist | Baseline, test set cố định, corrupted/repaired handoff | Comparison flow và release decision | Code hiện có trên main và metrics đã có; chưa xác nhận hoàn tất do thiếu quality/freshness/report |

Tôi không nhận ownership cho logic ingestion, cleaning/corruption, retrieval, evaluation hoặc observability của các thành viên khác. Khi code trong những module đó chưa sẵn sàng, tôi ghi blocker và giữ release gate đóng thay vì sửa thay owner.

### Việc điều phối và hỗ trợ

| Hoạt động | Owner liên quan | Kết quả |
| --- | --- | --- |
| Chốt handoff raw → clean → index/test set → evaluate/report | Tuấn, Mạnh, Khiêm, Hưng | Tên/path artifact và điều kiện GO/STOP được ghi trong báo cáo nhóm |
| Reconcile raw/clean | Tuấn, Mạnh | `24 = 24 + 0 filtered + 0 deduplicated`; `C1-BLOCKER-001` được đóng |
| Kiểm tra baseline index | Khiêm | `papers-baseline`, dimension 384, 24 embeddings; 24 ID khớp đúng clean snapshot |
| Kiểm tra fairness evaluation | Hưng | Ba answers artifact dùng cùng 20 sample và cùng thứ tự ID |
| Release audit | Cả nhóm | Giữ trạng thái **HOLD** vì thiếu official quality/freshness và hai Markdown report |

## 3. Kết quả theo vai trò

| Nhiệm vụ | Bằng chứng | Kết quả |
| --- | --- | --- |
| Triển khai `clean-v1` | Commit `3283d73`; `src/core/clean_contract.py`; `data/quality/clean_contract_gate.json` | Gate kiểm tra artifact, schema, ordered ID, raw lineage, audit count và SHA-256 |
| Chặn downstream trước khi clean ổn định | `_build_index_and_test_set_after_gate` trong `phase1.py` | Chỉ snapshot đã qua gate mới được đưa sang index/test set |
| Khóa clean snapshot | Gate SHA-256 `a805ea3cce587843cecbe78fafd3727c21c018102c095050f52979c1d5109d0a` | Khiêm và Hưng dùng cùng dataset 24 records |
| Đối soát index | Chroma SQLite và `papers_embeddings.json` | `papers-baseline`, 24 vectors, 24 unique IDs, không lệch clean |
| Đối soát evaluation/comparison | `data/results/*_metrics.json`, `*_answers.json` | 20 sample dùng chung; corruption làm bốn metric giảm, repaired trở về baseline |
| Ghi blocker trung thực | `report/group_report.md` | Không tuyên bố E2E/recovery hoàn chỉnh khi observability/report artifacts còn thiếu |

Không có file test nào do tôi tự sinh trong lần hoàn thiện báo cáo này. Các test hiện có trong repository thuộc các commit/owner đã được pull từ remote và không được dùng thay cho Definition of Done dựa trên artifact.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Các module được phát triển song song nhưng phụ thuộc vào cùng document identity và snapshot. Nếu index được build từ một clean file trong khi test set dùng clean file khác, metrics có thể chạy mà không còn ý nghĩa. Vai trò điều phối cần khóa schema, count, path và checksum; sau đó mới mở từng handoff.

### Cách triển khai

`clean-v1` yêu cầu năm artifact gồm raw response, raw records, clean CSV, clean JSON và cleaning summary. Gate đọc lại dữ liệu đã persist, kiểm tra các cột bắt buộc, kiểu/blank/date/age, uniqueness, CSV–JSON identity, raw lineage và phương trình count. Gate luôn ghi evidence machine-readable; nếu có blocker thì raise `CleanContractError` trước mọi index/test-set call. Khi GO, `phase1.py` truyền chính dataframe đã xác thực sang downstream và đưa count/hash vào source summary của report.

### Input, output và điều kiện dừng

| Thành phần | Mô tả |
| --- | --- |
| Input | `data/raw/crossref_response.json`, `data/raw/crossref_records.json`, clean CSV/JSON và cleaning summary |
| Output gate | `data/quality/clean_contract_gate.json` |
| Downstream baseline | `papers-baseline`, test set, baseline answers/metrics, quality/freshness và `phase1_report.md` |
| Điều kiện STOP | Thiếu/malformed artifact; count lệch; schema/ID/text/date sai; CSV/JSON khác snapshot |
| Điều kiện release | Tất cả artifact bắt buộc tồn tại và report khớp JSON/CSV thật |

### Cách xác minh đã dùng

```powershell
$gate = Get-Content data/quality/clean_contract_gate.json -Raw | ConvertFrom-Json
$gate.status
$gate.counts | Format-List
$gate.blockers.Count

sqlite3 data/chroma/chroma.sqlite3 `
  "SELECT name, dimension FROM collections ORDER BY name; SELECT COUNT(*) FROM embeddings;"

Get-ChildItem data -Recurse -File
```

Kết quả thực tế:

- Gate `GO`, raw/clean 24/24, blocker count 0.
- Clean có 24 unique `paper_id`, không có blank `text_for_embedding`.
- Chroma có ba collection `papers-baseline`, `papers-corrupted`, `papers-repaired`, dimension 384 và tổng 71 embedding rows.
- Test set có 20 sample; toàn bộ ground-truth IDs thuộc clean corpus.
- Quality/freshness JSON và hai generated Markdown report chưa tồn tại.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Ban đầu raw/clean artifact chưa có, trong khi index và test set có thể được tạo sớm từ schema dự kiến.
- **Phương án cân nhắc:** Cho downstream chạy theo `max_results=24`, hoặc giữ gate STOP cho tới khi có count/schema/hash quan sát thật.
- **Quyết định:** Chọn fail-closed gate và chỉ mở khi `clean-v1` GO.
- **Lý do:** `max_results` chỉ là request limit, không phải observed count. Dùng snapshot chưa xác minh có thể tạo index/test set không cùng dữ liệu và làm hỏng toàn bộ phép so sánh.
- **Bằng chứng:** Sau khi Tuấn/Mạnh bàn giao, gate xác nhận đúng `24 = 24 + 0 + 0`, khóa SHA-256 và cho phép Khiêm build index với đúng 24 IDs.

## 6. Blocker đã xử lý và blocker còn lại

### `C1-BLOCKER-001` — đã xử lý

- **Triệu chứng ban đầu:** Thiếu raw/clean artifacts, count là N/A và gate STOP.
- **Xử lý:** Giữ downstream đóng; yêu cầu đúng owner tạo raw, clean và audit summary; sau đó chạy lại gate.
- **Kết quả:** Gate GO, 24 raw/24 clean, CSV/JSON identity khớp, không blocker.

### `CP3-BLOCKER-001` — còn mở

- **Triệu chứng:** Có answers/metrics nhưng thiếu baseline/corrupted/repaired quality/freshness JSON; thiếu `data/reports/phase1_report.md` và `data/reports/corruption_report.md`.
- **Nguyên nhân đã xác định:** Code observability/reporting trên nhánh đang đối soát còn `NotImplementedError`; test-set generator artifact cũng chưa tái lập được từ code hiện tại.
- **Phạm vi ảnh hưởng:** Không thể đánh dấu baseline E2E, comparison report hoặc release hoàn tất.
- **Quyết định:** Giữ release **HOLD**; không vá JSON hoặc tự sửa module của Hưng.
- **Điều kiện gỡ:** Owner merge code trên latest main, chạy lại pipeline và chứng minh report khớp artifact.

## 7. Hiểu biết về luồng end-to-end

1. Crossref response được lưu nguyên bản trước khi parse. DOI trở thành stable `paper_id`; raw records được normalize thành clean dataframe, tính `age_days`, `summary_chars` và `text_for_embedding`. Clean gate xác minh snapshot trước khi MiniLM tạo vectors và Chroma lưu collection.
2. Test set chứa question, ground truth và `ground_truth_doc_ids`. Retrieval hit đo xem tài liệu đúng có nằm trong retrieved IDs; token F1 và LLM judge đo chất lượng answer. Ground-truth ID phải xuất phát từ clean corpus, không tự bịa.
3. Quality checks đo cấu trúc/nội dung như row count, null, uniqueness và summary. Freshness tập trung vào tuổi dữ liệu, latest/oldest date, stale rows và ngưỡng thời gian.
4. Baseline, corrupted và repaired phải dùng cùng test set để thay đổi metric phản ánh dữ liệu/index thay đổi, không phải câu hỏi thay đổi. Ba answers artifact hiện cùng đúng 20 IDs theo cùng thứ tự.
5. Repair chỉ được xem là thành công khi dữ liệu được tái tạo từ raw, quality/freshness phục hồi và agent metrics quay lại mức baseline. Metrics hiện đã phục hồi, nhưng release vẫn HOLD vì official observability/report artifacts chưa có.

## 8. Phân tích kết quả

### Metrics chính

| Metric/signal | Baseline | Corrupted | Repaired | Nhận xét |
| --- | ---: | ---: | ---: | --- |
| `retrieval_hit_rate` | 1.0000 | 0.6000 | 1.0000 | Giảm 0.4000 rồi phục hồi toàn bộ |
| `mean_token_f1` | 0.2465 | 0.1248 | 0.2465 | Giảm 0.1217 rồi về đúng baseline |
| `judge_accuracy` | 0.5000 | 0.2000 | 0.5000 | Giảm 0.3000 rồi về đúng baseline |
| `mean_judge_score` | 3.0500 | 1.8000 | 3.0500 | Giảm 1.2500 rồi về đúng baseline |
| Manual quality issues | 0 | 3 blank summaries, 1 duplicate group | 0 | Official quality artifact chưa có |
| Manual stale rows | 0 | 2 | 0 | Official freshness artifact chưa có |

### Kết luận từ số liệu

1. Corruption làm dataset giảm từ 24 xuống 23 dòng, còn 22 unique IDs, xuất hiện blank summary, duplicate và stale rows → retrieval chỉ hit 12/20 thay vì 20/20; F1 và judge metrics cùng giảm.
2. Repair từ raw tạo lại 24 dòng/24 unique IDs, không blank summary và không stale row → bốn metric repaired trùng baseline.

Corruption có tác động rõ ở mức tổng hợp, nhưng không thể khẳng định loại corruption nào gây phần lớn mức giảm vì nhiều lỗi được áp dụng cùng lúc. Cần ablation từng scenario để tách tác động. Kết quả khác kỳ vọng là baseline retrieval đạt 100% nhưng mean token F1 chỉ 0.2465; điều này cho thấy lấy đúng document chưa đảm bảo câu trả lời có lexical overlap cao với ground truth.

## 9. Điều học được và hướng cải thiện

### Ba điều quan trọng nhất

1. Pipeline chỉ đáng tin khi mỗi handoff có schema, path, count và evidence; terminal báo `done` không thay thế artifact verification.
2. Quality và freshness cần được đo độc lập với agent metrics: một index có thể vẫn query được trong khi dữ liệu đã duplicate, blank hoặc stale.
3. Retrieval đúng tài liệu là điều kiện cần nhưng chưa đủ cho answer quality; phải đọc answers và judge evidence trước khi kết luận RAG tốt.

### Nếu có thêm thời gian

Tôi sẽ bổ sung postcondition ở orchestration để xác minh đủ artifact sau mỗi phase, khóa clean/test-set fingerprints trong manifest và chạy ablation từng corruption. Cải thiện được đo bằng khả năng tái lập cùng hash/count/metric từ một lệnh clean checkout, không dựa vào file tạo thủ công.

## 10. Cam kết của thành viên

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Mọi kết luận định lượng đều có artifact để đối chiếu.
- [x] Tôi không ghi “đã chạy thành công” cho phần chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo cá nhân không sao chép nguyên văn báo cáo nhóm.

**Họ và tên:** Trần Hoàng Quân  
**Ngày xác nhận:** 2026-08-06
