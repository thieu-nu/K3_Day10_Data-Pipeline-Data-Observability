# CP1 — Vai trò 3: Cleaning

## Kết quả triển khai

- `build_clean_dataframe()` đã hoàn thiện normalization, date parsing, filtering, deduplication và helper fields.
- Thống kê filter/dedupe được gắn tại `dataframe.attrs["cleaning_stats"]` và ghi được ra `cleaning_report.json`.
- `write_clean_artifacts()` ghi clean CSV, clean JSON và cleaning report mà không thay đổi starter signature.
- `script/run_cleaning_cp1.py` sẵn sàng chạy trên `data/raw/crossref_records.json` do Source Ingestion Owner bàn giao.

## Quy tắc đã thực thi

| Quy tắc | Hành vi |
| --- | --- |
| Null ID/title | Loại record và tăng count theo đúng lý do |
| Summary | Bỏ markup/whitespace; loại nếu dưới 100 ký tự |
| Published | Parse và chuẩn hóa `YYYY-MM-DD`; loại ngày sai |
| Updated | Chuẩn hóa nếu hợp lệ, nếu không thì để rỗng |
| Duplicate | So sánh `paper_id` không phân biệt hoa/thường, giữ record hợp lệ đầu tiên |
| Authors/categories | Normalize, bỏ phần tử rỗng/trùng, giữ thứ tự và nối bằng `, ` |
| Freshness | `age_days = max(0, run_date - published)` |
| Embedding text | `Title: ... | Authors: ... | Summary: ...` |

## Minh chứng kiểm tra

Lệnh:

```powershell
.\.venv\Scripts\python.exe script\validate_cleaning_sample.py
```

Kết quả:

```text
CP1 sample validation passed.
```

Sample kiểm tra cả transformation, filter count, dedupe count và việc ghi/đọc lại CSV/JSON/report.

## Trạng thái artifact thật

Tại thời điểm hoàn tất phần code CP1, `data/raw/crossref_records.json` chưa tồn tại. Vì vậy chưa sinh `papers_clean.csv`, `papers_clean.json` từ dữ liệu thật và không dùng dữ liệu giả để thay thế artifact nhóm.

Khi Source Ingestion Owner bàn giao raw snapshot, chạy:

```powershell
uv run python script/run_cleaning_cp1.py
```

Output dự kiến:

- `data/clean/papers_clean.csv`
- `data/clean/papers_clean.json`
- `data/clean/cleaning_report.json`
