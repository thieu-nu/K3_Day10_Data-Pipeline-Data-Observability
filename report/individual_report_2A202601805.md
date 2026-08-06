# Member Role Report — Trần Hoàng Quân — Day 10: Data Pipeline & Data Observability

> Mỗi thành viên trong nhóm tự hoàn thành mẫu này để báo cáo đúng vai trò, phần việc và mức hiểu của mình. Không sao chép nguyên báo cáo chung hoặc báo cáo của thành viên khác. Thay nội dung trong dấu `[ ]` và xóa các dòng hướng dẫn không cần thiết trước khi nộp.

## 1. Thông tin cá nhân

| Thông tin         | Nội dung                  |
| ------------------ | -------------------------- |
| Họ và tên       | Trần Hoàng Quân |
| MSSV               | 2A202601805 |
| Khóa/Lớp         | K3 |
| Tên nhóm         | 5 nang cong chua |
| Vai trò chính    | VAI TRÒ 1 — Điều phối pipeline: cấu hình, orchestration, release |
| Repository         | https://github.com/thieu-nu/K3_Day10_Data-Pipeline-Data-Observability |
| Ngày hoàn thành | 2026-08-06 |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao  | Trạng thái                                 |
| ------------------ | --------------------- | ---------------- | ----------------- | -------------------------------------------- |
| Contract và clean gate C1 | `src/core/config.py`, `src/core/clean_contract.py`, `script/check_clean_contract.py`; mục *Thành viên và phân công* trong `report/group_report.md` | Schema `PaperRecord`, các path trong `Settings`, yêu cầu handoff của Tuấn/Mạnh/Khiêm/Hưng | Contract `clean-v1`, gate GO/STOP, `data/quality/clean_contract_gate.json` và `C1-BLOCKER-001` | Hoàn thành implementation C1; gate hiện **STOP/CLOSED** do thiếu upstream artifacts |
| Baseline orchestration | `src/pipelines/phase1.py`, `script/run_phase1.py` | Raw của Tuấn → clean của Mạnh → gate của Quân → index của Khiêm → evaluation/observability của Hưng | Pipeline baseline và toàn bộ artifact theo `Settings.paths` | Đã ghép flow và chặn downstream sau gate; chưa chạy end-to-end vì upstream chưa hoàn thành |
| Corruption, repair và release | `src/pipelines/corruption_flow.py`, `script/run_corruption_flow.py` | Baseline đã qua gate, test set cố định và ba collection tách biệt | Corrupted/repaired artifacts, comparison report và release checklist | Chưa bắt đầu; chỉ chạy sau khi baseline hoàn chỉnh |

Chỉ nhận ownership cho phần bạn trực tiếp thực hiện. Liên hệ rõ phần việc của bạn với đầu vào, đầu ra và các thành viên phụ thuộc vào phần đó.

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động                         | Thành viên/module được hỗ trợ | Kết quả                    |
| ------------------------------------ | ------------------------------------ | ---------------------------- |
| Chốt giao diện handoff và ranh giới ownership | Tuấn, Mạnh, Khiêm, Hưng | Bảng phân vai ghi rõ artifact tiên quyết, output và người nhận tại `report/group_report.md` |
| Rà soát raw count → clean count | Tuấn (ingestion), Mạnh (cleaning) | Phát hiện chưa có artifact để đo count; ghi `C1-BLOCKER-001` và giữ gate downstream ở trạng thái **STOP** |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao       | Cách xác minh         |
| --------------------------- | ----------------------------- | ------------------------- | ----------------------- |
| Chốt và triển khai clean contract C1 | `src/core/clean_contract.py`, `src/core/config.py`, `report/group_report.md` | Validator artifact/schema/count/lineage, SHA-256 snapshot và contract audit theo reason | Đọc `tests/test_clean_contract.py`; chạy `python script/check_clean_contract.py` khi có Python 3.11 |
| Kiểm tra sự tồn tại của raw/clean artifacts trước khi mở test set/index | `data/raw/`, `data/clean/`, `data/quality/clean_contract_gate.json` | `C1-BLOCKER-001`: raw/clean count chưa đo được; gate **STOP/CLOSED** với năm blocker code | `Get-ChildItem data/raw,data/clean -File` và đọc JSON evidence |
| Bảo đảm thứ tự gate → index → test set | `src/pipelines/phase1.py`, `tests/test_phase1_gate.py` | Gate STOP raise trước mọi downstream call; chỉ snapshot GO được chuyển tiếp | Đã thêm test sentinel cho STOP/GO; chưa chạy vì môi trường thiếu Python 3.11 |

Output cụ thể đã tạo là implementation contract `clean-v1`, JSON evidence `data/quality/clean_contract_gate.json` và blocker `C1-BLOCKER-001`. Contract cố định input/output, tên artifact, schema downstream, audit reason/count, lineage, checksum và điều kiện dừng. `phase1.py` chỉ chuyển snapshot đã được gate xác thực sang test set/index.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Các module được làm song song nhưng phụ thuộc theo chuỗi raw → clean → index/test set → evaluation/report. Nếu tên file, schema hoặc tiêu chí chấp nhận clean data không thống nhất, nhánh RAG và evaluation có thể xây trên hai snapshot khác nhau hoặc chạy với `paper_id`/`text_for_embedding` lỗi. Vai trò điều phối phải khóa interface và dừng downstream khi chưa có evidence.

### Cách triển khai

Tôi chốt contract `clean-v1` từ các kiểu và path hiện có trong `src/core/config.py`, `src/ingestion/crossref.py`, `src/retrieval/index.py` và `src/observability/quality.py`. `src/core/clean_contract.py` kiểm tra năm artifact, schema/value, CSV–JSON identity, raw lineage, audit reason/count và ghi gate report kèm hash. `phase1.py` gọi `enforce_clean_contract` trước khi resolve hoặc gọi index/test-set builders; lỗi STOP được propagate, không có nhánh fallback chạy downstream.

### Input, output và contract

| Thành phần                   | Mô tả                                     |
| ------------------------------ | ------------------------------------------- |
| Input | `data/raw/crossref_records.json` chứa danh sách `PaperRecord`; lineage qua `data/raw/crossref_response.json` |
| Output | `data/clean/papers_clean.csv`, `data/clean/papers_clean.json`, `data/clean/cleaning_summary.json`; quyết định gate tại `data/quality/clean_contract_gate.json` |
| Module phụ thuộc | `src/core/config.py`, `src/ingestion/crossref.py`, `src/ingestion/cleaning.py` |
| Module sử dụng output | `src/retrieval/index.py`, `src/evaluation/testset.py`, `src/observability/quality.py`, `src/pipelines/phase1.py` |
| Điều kiện lỗi cần xử lý | Artifact thiếu/không đọc được; count không reconcile; schema thiếu cột; `paper_id` null/trùng; `text_for_embedding` rỗng; `published`/`age_days` không parse được |

### Cách xác minh

```powershell
Get-ChildItem data/raw,data/clean -File
rg -n "NotImplementedError" src/ingestion/crossref.py src/ingestion/cleaning.py
```

- **Kết quả mong đợi:** Có `crossref_response.json`, `crossref_records.json`, `papers_clean.csv`, `papers_clean.json`, `cleaning_summary.json`; count khớp contract và ingestion/cleaning không còn dừng bằng `NotImplementedError`.
- **Kết quả thực tế:** `data/raw/` và `data/clean/` chỉ có `.gitkeep`; các hàm ingestion/cleaning trọng yếu vẫn là starter `NotImplementedError`. Vì vậy raw/clean count là `N/A`, không phải 0.
- **Artifact/log:** `data/quality/clean_contract_gate.json` và `report/group_report.md`, blocker `C1-BLOCKER-001`; không chứa secret.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Chưa có raw/clean artifact nhưng hai nhánh test set và index cần bắt đầu từ clean schema ổn định.
- **Các phương án đã cân nhắc:** (1) dùng `max_results=24` và schema dự kiến để cho downstream chạy sớm; (2) khóa gate cho tới khi có snapshot clean và audit count thật.
- **Phương án đã chọn:** Giữ gate **STOP/CLOSED**, chỉ chuyển sang **GO** khi toàn bộ tiêu chí `clean-v1` đạt.
- **Lý do:** Cách này ưu tiên correctness và reproducibility; tránh biến giới hạn request thành số liệu quan sát giả và tránh phải tái tạo test set/index khi `paper_id` hoặc schema thay đổi.
- **Bằng chứng quyết định phù hợp:** `data/quality/clean_contract_gate.json` ghi STOP với năm artifact thiếu; `crossref.py` và `cleaning.py` còn `NotImplementedError`; test sentinel mô tả hành vi không gọi downstream khi STOP.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng/lỗi nguyên văn:** Không tìm thấy `data/raw/crossref_records.json`, `data/clean/papers_clean.csv` và `data/clean/papers_clean.json`; do đó `raw_count`/`clean_count` chưa đo được.
- **Lệnh hoặc bước tái hiện:** Chạy `Get-ChildItem data/raw,data/clean -File`, sau đó tìm `NotImplementedError` trong hai module ingestion/cleaning.
- **Nguyên nhân gốc:** Tuấn và Mạnh chưa hoàn thiện các hàm tạo raw/clean artifacts; thư mục dữ liệu mới chỉ có file giữ chỗ `.gitkeep`.
- **Cách xử lý:** Tôi triển khai `clean-v1`, thêm path audit/gate vào `Settings`, ghi `C1-BLOCKER-001` và đặt fail-closed gate trước `build_test_set`/`LocalEmbeddingIndex.build`. Tôi không sửa thay logic ingestion/cleaning thuộc owner khác.
- **Cách xác minh sau khi sửa:** Chưa thể xác minh bản sửa vì blocker chưa được gỡ; hiện gate vẫn **STOP/CLOSED**.
- **Điều học được:** Giá trị cấu hình như `max_results` không thay thế được count quan sát từ artifact; mọi handoff cần schema, path và evidence kiểm chứng.

Nếu chưa xử lý xong:

- **Phạm vi bị ảnh hưởng:** Baseline orchestration, test set, Chroma index, evaluation, quality/freshness và các flow corrupted/repaired.
- **Những gì đã loại trừ:** Không phải lỗi đọc nhầm path downstream; các path mục tiêu đã được cấu hình trong `Settings.paths` nhưng file chưa được tạo. `max_results=24` chỉ là request limit.
- **Bước tiếp theo:** Tuấn tạo raw snapshot/count; Mạnh tạo clean CSV/JSON và audit trong `df.attrs["cleaning_summary"]`; Quân chạy `python script/check_clean_contract.py`, kiểm tra report/schema/checksum rồi mới mở gate cho Khiêm và Hưng. Cần cài lại Python 3.11/uv để chạy test tự động.

## 7. Hiểu biết về luồng end-to-end

Giải thích ngắn gọn bằng lời của bạn:

1. Dữ liệu đi từ Crossref đến vector index như thế nào?
2. Evaluation set và ground-truth document IDs dùng để đo retrieval/answer quality ra sao?
3. Quality checks khác freshness monitoring ở điểm nào trong bài lab?
4. Vì sao phải dùng cùng test set cho baseline, corrupted và repaired?
5. Repair được xem là thành công dựa trên artifact và metric nào?

**Câu trả lời:**

[Viết câu trả lời tại đây.]

## 8. Phân tích kết quả

### Metrics chính

| Metric/signal          | Baseline | Corrupted | Repaired | Nhận xét của cá nhân |
| ---------------------- | -------: | --------: | -------: | ------------------------- |
| `retrieval_hit_rate` |      [ ] |       [ ] |      [ ] | [Nhận xét]              |
| `mean_token_f1`      |      [ ] |       [ ] |      [ ] | [Nhận xét]              |
| `judge_accuracy`     |      [ ] |       [ ] |      [ ] | [Nhận xét]              |
| `mean_judge_score`   |      [ ] |       [ ] |      [ ] | [Nhận xét]              |
| Quality checks         |      [ ] |       [ ] |      [ ] | [Nhận xét]              |
| Freshness status       |      [ ] |       [ ] |      [ ] | [Nhận xét]              |

### Kết luận từ số liệu

Hoàn thành hai chuỗi nguyên nhân–bằng chứng sau:

1. [Data corruption] → [quality/freshness signal thay đổi] → [agent metric thay đổi].
2. [Repair action] → [quality/freshness signal phục hồi] → [agent metric phục hồi hoặc chưa phục hồi].

Corruption nào ảnh hưởng rõ nhất và vì sao?

[Phân tích dựa trên số liệu.]

Kết quả nào khác với kỳ vọng ban đầu?

[Nêu kết quả, giả thuyết và cách đã kiểm tra.]

## 9. Điều học được và hướng cải thiện

### Ba điều quan trọng nhất

1. [Điều học được về data pipeline.]
2. [Điều học được về data quality/observability.]
3. [Điều học được về ảnh hưởng của data đến RAG agent.]

### Nếu có thêm thời gian

[Nêu một cải thiện cụ thể, lý do và cách đo cải thiện đó.]

## 10. Cam kết của thành viên

Đánh dấu sau khi tự kiểm tra:

- [ ] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [ ] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [ ] Mọi kết luận về kết quả đều có artifact hoặc metric để đối chiếu.
- [ ] Tôi không ghi “đã chạy thành công” cho phần chưa được kiểm chứng.
- [ ] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [ ] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Trần Hoàng Quân  
**Ngày xác nhận:** 2026-08-06
