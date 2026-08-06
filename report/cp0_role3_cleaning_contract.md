# CP0 — Vai trò 3: Cleaning & Corruption Owner

## Phạm vi và handoff

- Input cần nhận từ Source Ingestion Owner: `data/raw/crossref_records.json`, ánh xạ được thành `list[PaperRecord]`.
- Module sở hữu: `src/ingestion/cleaning.py` và, ở pha sau, `src/ingestion/corruption.py` cùng logic repair từ raw snapshot.
- Output bàn giao ở CP1: `data/clean/papers_clean.csv` và `data/clean/papers_clean.json` đúng clean schema.
- Người nhận output: owner của evaluation set, embedding/index, observability và pipeline integration.

## Quyết định contract tại CP0

1. `paper_id`, `title`, `summary`, `published` là các raw field bắt buộc để một record đi tiếp.
2. Sau khi bỏ markup và chuẩn hóa khoảng trắng, record có `summary` dưới 100 ký tự bị loại.
3. `paper_id` là identity xuyên suốt pipeline; deduplicate theo `paper_id` và giữ record hợp lệ đầu tiên.
4. `authors` và `categories` được làm sạch từng phần tử, bỏ rỗng và flatten thành `authors_joined`, `categories_joined` bằng `", "`.
5. `published` được chuẩn hóa thành `YYYY-MM-DD`; ngày không hợp lệ làm record bị loại. `updated` không bắt buộc và có thể rỗng.
6. `age_days` được tính tại `run_date`, bằng `max(0, run_date - published)` theo đơn vị ngày.
7. `text_for_embedding` có format cố định:

   ```text
   Title: {title} | Authors: {authors_joined} | Summary: {summary}
   ```

8. Output phải có tối thiểu: `paper_id`, `title`, `summary`, `published`, `updated`, `authors_joined`, `categories_joined`, `age_days`, `summary_chars`, `text_for_embedding`, `abs_url`, `pdf_url`.

## Sample validation chuẩn bị cho CP1

Chạy sau khi `build_clean_dataframe()` được implement:

```powershell
uv run python script/validate_cleaning_sample.py
```

Sample cố ý chứa markup, whitespace thừa, author/category rỗng và hai record trùng DOI. Validation phải chứng minh:

- markup không còn trong title/summary;
- summary ngắn bị loại;
- duplicate DOI chỉ còn một dòng;
- authors/categories được flatten đúng;
- `published`, `age_days` và `summary_chars` đúng;
- `text_for_embedding` đúng format và không rỗng.

## Trạng thái CP0

- Contract: đã chốt.
- Sample validation: đã chuẩn bị, chưa chạy vì cleaning là nhiệm vụ CP1.
- Baseline/corruption: chưa chạy, đúng quy tắc thứ tự của lab.
- API key: không cần cho phạm vi CP0/CP1 của cleaning.
