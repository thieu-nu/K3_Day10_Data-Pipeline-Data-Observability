# Member Role Report — Đàm Minh Tuấn — Day 10: Data Pipeline & Data Observability

## 1. Thông tin cá nhân

| Thông tin         | Nội dung                                                              |
| ----------------- | --------------------------------------------------------------------- |
| Họ và tên         | Đàm Minh Tuấn                                                         |
| MSSV              | 2A202601169                                                           |
| Khóa/Lớp          | K3                                                                    |
| Tên nhóm          | 5 nang cong chua                                                      |
| Vai trò chính     | VAI TRÒ 2 — Ingestion: Crossref API, chuẩn hóa PaperRecord và raw lineage |
| Repository        | https://github.com/thieu-nu/K3_Day10_Data-Pipeline-Data-Observability |
| Ngày hoàn thành   | 2026-08-06                                                            |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module / deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao | Trạng thái |
| :--- | :--- | :--- | :--- | :--- |
| **Thu thập & tích hợp Crossref API** | `src/ingestion/crossref.py` (hàm `fetch_crossref_records`), `script/fetch_raw.py` | Cấu hình `Settings` từ `src/core/config.py`: URL, query string, tham số lọc (`source_filter`), và `max_results` | Snapshot JSON nguyên gốc từ API (`data/raw/crossref_response.json`) | **Hoàn thành 100%**: Xây dựng thành công HTTP request với retry & exponential backoff, bóc tách chính xác 24 bản ghi gốc |
| **Chuẩn hóa Raw Schema & Lineage** | `src/ingestion/crossref.py` (hàm `parse_crossref_payload`, `load_raw_records`, dataclass `PaperRecord`) | Payload thô từ Crossref REST API | Bộ dữ liệu gốc có cấu trúc chuẩn (`data/raw/crossref_records.json`), mapping định danh `DOI` $\rightarrow$ `paper_id` ổn định | **Hoàn thành 100%**: Loại bỏ bản ghi thiếu DOI/title, làm sạch HTML basic, xuất cấu trúc chuẩn cho module cleaning |
| **Bộ kiểm thử TDD cho Ingestion** | `tests/test_crossref.py`, `tests/test_ingestion.py` | Fixture dữ liệu mẫu sim Crossref response | Báo cáo kiểm thử xác thực tính đầy đủ và toàn vẹn của luồng tải dữ liệu | **Hoàn thành 100%**: Bộ kiểm thử chạy qua màu xanh (`PASSED`), không còn stopper `NotImplementedError` |

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Thành viên/module được hỗ trợ | Kết quả |
| :--- | :--- | :--- |
| **Thống nhất định danh `paper_id` & quy tắc handoff dữ liệu thô** | Mạnh (Role 3 - Cleaning) và Quân (Role 1 - Coordinator) | Thiết lập vững chắc trường `paper_id` theo chuẩn `DOI` tinh rỗng để Mạnh dễ dàng de-duplicate và Quân bọc Clean Contract Gate C1 kiểm soát count (`24 records`) |
| **Cung cấp Raw Lineage & cơ chế khôi phục dữ liệu (Source Re-ingestion)** | Hưng (Role 5 - Observability) và Khiêm (Role 4 - RAG Agent) | Đóng gói snapshot thô `raw_records_json` bất biến (immutable), tạo điểm tựa cứu cánh để thi hành bước *Repair* khôi phục lại 100% sức mạnh RAG Agent sau khi dữ liệu tầng Clean bị làm hỏng ở Phase 2 |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao | Cách xác minh |
| :--- | :--- | :--- | :--- |
| Triển khai logic thu thập dữ liệu tự động từ nguồn Crossref | `src/ingestion/crossref.py` (`fetch_crossref_records`) | Kết nối ổn định tới API, tự động vượt qua lỗi mạng/rate limit bằng exponential backoff, xuất ra file `data/raw/crossref_response.json` | Chạy lệnh `python script/fetch_raw.py` và kiểm tra sự tồn tại của file payload gốc |
| Bóc tách, chuyển đổi chuỗi JSON thô sang cấu trúc định hình `PaperRecord` | `src/ingestion/crossref.py` (`parse_crossref_payload`, `load_raw_records`) | Danh sách 24 bản ghi chuẩn (`data/raw/crossref_records.json`) đủ trường thông tin cơ bản: `paper_id`, `title`, `summary`, `authors`, `published`,... | Chạy bộ test unit `python -m pytest tests/test_crossref.py -v` (kết quả `PASSED`) |
| Bồi đắp luồng Phục hồi sau thối nát dữ liệu (Phase 2 Repair Flow) | `src/pipelines/corruption_flow.py` (bước 6: Source Re-ingestion) | Tác nhân chính cung cấp dữ liệu sạch nguyên bản để dựng lại `repaired_clean_csv` và `repaired_embeddings_json` | Chạy `python script/run_corruption_flow.py` và quan sát chỉ số phục hồi 100% trong `data/reports/corruption_report.md` |

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết
Trong kiến trúc một Data Pipeline và RAG System, bước **Ingestion** là đầu nguồn nước (upstream foundation). Nếu luồng thu thập dữ liệu từ bên thứ 3 (Crossref API) bị gián đoạn do cáp quang, nghẽn mạng (HTTP 429 Rate Limit) hoặc mang về dữ liệu rác (thiếu DOI, trống tiêu đề, thẻ HTML xen thô mút mù), toàn bộ các tầng hạ du (Cleaning, Vector Indexing, Evaluation) sẽ đổ vỡ theo dây chuyền (Garbage In, Garbage Out). Thách thức đặt ra cho Vai trò 2 là phải kiến tạo một họng hút dữ liệu mạnh mẽ, bền bỉ, chuẩn hóa định danh vô ngã (immutable identifier) và bảo lưu vĩnh viễn phả hệ nguồn (raw lineage).

### Cách triển khai
Tôi xây dựng mô- đun `src/ingestion/crossref.py` chia theo quy trình hai buồng (Two-Stage Buffer):
1. **Buồng mạng & Tải (Network Fetcher):** Sử dụng `requests` kèm vòng lặp kiểm tra mã lỗi HTTP. Nếu xuất hiện các mã 429 (Rate Limit) hoặc 500-504 (Server Error), hệ thống kích hoạt thuật toán nghỉ nhịp tăng theo hàm mũ (Exponential Backoff) để thử lại tải mà không làm nghẽn tiến trình. Ngay sau khi thành công, toàn bộ raw payload chưa chỉnh sửa được sao lưu tức khắc vào `data/raw/crossref_response.json` làm chứng cứ kiểm toán gốc (Lineage Trial).
2. **Buồng chuyển đổi (Schema Normalizer & Mapping):** Hàm `parse_crossref_payload` lướt qua cây đối tượng JSON, lọc bỏ các bản ghi khuyết DOI hoặc tiêu đề rỗng. Trường `DOI` được lót thành chìa khóa định danh chính thức (`paper_id`). Tóm tắt (`abstract`) và các thông tin ngày tháng (`date-parts`) được cạo bỏ thẻ HTML rớt (`_clean_html`), định dạng về chuẩn ISO-8601 (`YYYY-MM-DD`) và gán vào cấu trúc kiểu dữ liệu chặt chẽ `PaperRecord`. Cuối cùng, toàn bộ được ghi snapshot ra `data/raw/crossref_records.json`.

### Input, output và contract

| Thành phần | Mô tả chi tiết |
| :--- | :--- |
| **Input** | Thông tin gọi API từ `Settings`: `source_query = "agentic retrieval augmented generation large language model"`, `source_filter = "from-pub-date:2026-02-07,has-abstract:true"`, `max_results = 24` |
| **Output** | 2 artifacts trong `data/raw/`: `crossref_response.json` (bản đồ thô) và `crossref_records.json` (danh sách 24 object theo chuỗi schema `PaperRecord`) |
| **Module phụ thuộc** | `src/core/config.py` (quản lý đường dẫn và tham số) |
| **Module sử dụng output** | `src/ingestion/cleaning.py` (của Mạnh), `src/core/clean_contract.py` & `src/pipelines/phase1.py` (của Quân), `src/pipelines/corruption_flow.py` |
| **Điều kiện lỗi cần xử lý** | API timeout/lỗi kết nối; response trả về JSON dị dạng không chứa key `message.items`; bài báo bị thiếu DOI (id duy nhất) hoặc vỡ trường cấu trúc |

### Cách xác minh
Kiểm tra bằng lệnh terminal tại thư mục gốc dự án:
```powershell
# 1. Chạy tải dữ liệu thô và xem log hệ thống
python script/fetch_raw.py

# 2. Kiểm tra bộ kiểm thử tự động của riêng module ingestion
python -m pytest tests/test_crossref.py tests/test_ingestion.py -v

# 3. Kiểm tra số lượng và tính tồn tại của các artifacts nguồn
Get-ChildItem data/raw/ -File | Select-Object Name, Length
```

- **Kết quả mong đợi:** Cả 2 file `crossref_response.json` và `crossref_records.json` xuất hiện với dung lượng đầy đủ. Lệnh pytest hiển thị trạng thái `PASSED` toàn bộ, không có ngoại lệ `NotImplementedError`.
- **Kết quả thực tế:** Hệ thống thu về đủ 24 bản ghi hợp lệ từ Crossref, lưu vào hai tệp đích trong `data/raw/`. Mọi test kiểm chứng của Role 2 vượt qua thành công `2/2 PASSED`.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Trong Crossref API, trường tóm tắt (`abstract`) thường bám đầy các thẻ HTML thô (ví dụ: `<jats:p>`, `<p>`, `<b>`) và các mốc thời gian xuất bản (`published`) nằm chắp vá trong các mảng `date-parts` vô định hình.
- **Các phương án đã cân nhắc:** 
  1. Giữ nguyên toàn bộ văn bản rác và mảng thời gian nhét thẳng vào file Raw Records, để Phó module Làm sạch (Role 3 - Cleaning) tự chịu trách nhiệm gọt rửa từ con số 0.
  2. Thực hiện làm sạch sơ bộ (Pre-cleaning) ngay tại tầng Ingestion: dùng Regex lột bỏ thẻ HTML cơ bản của Abstract và chuỗi hóa `date-parts` thành ngày ISO (`YYYY-MM-DD`) trước khi đổ vào `PaperRecord`.
- **Phương án đã chọn:** Chọn **Phương án 2** — Chuẩn hóa sơ bộ ranh giới ngay tại tầng Ingestion nhưng giữ nguyên bản chất nội dung chữ.
- **Lý do:** Kỹ thuật Ingestion chuyên nghiệp đòi hỏi dữ liệu xuất ra khỏi ranh giới của nó phải đạt tiêu chuẩn *Nhất quán cú pháp* (Syntax Consistency). Việc ánh xạ rõ ràng ngày tháng về ISO-8601 giúp module của Mạnh dễ dàng tính ngày `age_days` bằng `pandas` mà không vấp rủi ro sụp trượt mảng, đồng thời duy trì hợp đồng dữ liệu `PaperRecord` vô song trước toàn bộ pipeline.
- **Bằng chứng quyết định phù hợp:** Hàm `_extract_date` và `_clean_html` vận hành êm ái. Khi truyền trả sang bước `build_clean_dataframe`, tỷ lệ lỗi parse ngày (`filtered_invalid_published`) là `0 / 24`, giúp 100% dữ liệu gốc lách qua Clean Contract Gate một cách trơn tru.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng/lỗi nguyên văn:** Trong quá trình khớp nối test kiểm nghiệm luồng Corruption & Repair (`test_corruption_flow.py`), khi hệ thống nỗ lực khôi phục lại dữ liệu bằng hàm `load_raw_records(new_paths.raw_records_json)`, trình biên dịch lập tức ném lỗi chí mạng:
  `TypeError: PaperRecord.__init__() missing 3 required positional arguments: 'primary_category', 'updated', and 'comment'`
- **Lệnh hoặc bước tái hiện:** Chạy lệnh kiểm nghiệm tích hợp pipeline:
  `python -m pytest tests/test_corruption_flow.py -v`
- **Nguyên nhân gốc:** Khi định nghĩa cấu trúc dữ liệu mô phỏng trong test case hoặc khi tải snapshot JSON cũ, các thuộc tính mở rộng mới được bổ sung vào dataclass `PaperRecord` (gồm `primary_category`, `updated`, và `comment`) đã bị khuyết thiếu, gây đứt gãy trình khởi tạo cơ sở bộ nhớ của Python Dataclass.
- **Cách xử lý:** Tôi đã trực tiếp điều chỉnh logic đối soát bên trong luồng bóc tách dữ liệu và sửa đổi hợp đồng giả lập (Mock schema) tại `test_corruption_flow.py`, đồng bộ hóa các trường mặc định chu đáo: luôn cấp chuỗi cho `primary_category` (lấy từ category đầu tiên), đồng bộ `updated` theo `published` nếu khuyết, và đặt chuỗi rỗng `""` cho `comment`.
- **Cách xác minh sau khi sửa:** Chạy lại toàn bộ bộ kiểm nghiệm luồng tích hợp và unit test:
  `python -m pytest tests/test_corruption_flow.py -v` $\rightarrow$ Kết quả `100% PASSED` trong màu xanh viên mãn.
- **Điều học được:** Khi làm việc trong một tổ đội song song (Multi-role AI engineering), cấu trúc DTO (Data Transfer Object / Dataclass) chính là "đan xen khế ước". Không bao giờ được tùy tiện chỉnh sửa hay giả định thuộc tính của Dataclass gốc mà không duy trì khả năng đồng bộ ngược (backward compatibility) và tính nghiêm ngặt trên toàn bộ hệ thống test.

## 7. Hiểu biết về luồng end-to-end

1. **Dữ liệu đi từ Crossref đến vector index như thế nào?**
   Dữ liệu khởi phát từ yêu cầu HTTP GET gửi tới máy chủ Crossref REST API (do *Role 2* thực hiện), trả về chuỗi JSON thô được chuẩn hóa nhẹ thành danh sách 24 object `PaperRecord` tại `raw_records.json`. Tiếp theo, bộ lọc Làm sạch (của *Role 3*) hút dữ liệu này, cạo sạch nhiễu sâu, tính toán độ mới (`age_days`), loại bỏ mảng trùng lặp và biến đổi thành tệp `papers_clean.csv`. Sau đó, Trạm gác dữ liệu (Clean Contract Gate C1 do *Role 1* quản lý) rà soát checksum SHA-256 và tính hợp lệ; khi trạm bật tín hiệu **GO**, mô-đun RAG (của *Role 4*) lập tức chuyển đĩa văn bản thô qua mô hình nhúng (`MiniLM-L6-v2`) biến đổi từng bài báo thành các ma trận vector toán học và cất giữ an toàn vào cở sở dữ liệu ChromaDB (`data/chroma/`).
2. **Evaluation set và ground-truth document IDs dùng để đo retrieval/answer quality ra sao?**
   Tập kiểm tra (`test_set.json` do *Role 5* quản lý) sinh ra các câu hỏi song hành cùng đáp án mẫu và ID của bài báo gốc (`ground_truth_doc_ids`). Khi Agent giải quây câu hỏi, hệ thống giám sát tính chỉ số: nếu ma trận tìm kiếm của ChromaDB nhặt được đúng tệp mang `paper_id` thuộc danh sách ground-truth, `retrieval_hit_rate` được chấm 1.0 (đo chất lượng bộ máy tìm kiếm); tiếp đó văn bản trả lời của LLM được so sánh với `ground_truth` để đo tỷ lệ trùng lặp từ (`mean_token_f1`) và giao cho một LLM Judge chấm độ chính xác thực tế từ 1-5 (`mean_judge_score`, đo trí tuệ suy luận).
3. **Quality checks khác freshness monitoring ở điểm nào trong bài lab?**
   - **Quality checks (Kiểm tra chất lượng):** Giám sát *Tính toàn vẹn nội tại của mảng cấu trúc*, đảm bảo không bị ô nhiễm (ví dụ: quét tìm khóa chính null, tóm tắt rỗng `""`, độ dài dưới ngưỡng 100 chữ hay lỗi lặp lồng hàng `duplicate rows`).
   - **Freshness monitoring (Theo dõi độ tươi mới):** Giám sát *Giá trị thực tế theo dòng thời gian*, đo khoảng cách từ ngày chạy đến ngày công bố bài báo (`age_days`). Dù bài báo có cấu trúc ngữ pháp vô song đến đâu nhưng tuổi đời quá cũ (`age_days > 180`), hệ thống freshness vẫn ném cảnh báo hạn ngạch rắc rối (Stale Data).
4. **Vì sao phải dùng cùng một test set cho cả baseline, corrupted và repaired?**
   Đây là nguyên tắc thiết yếu trong "Kiểm chứng Thực nghiệm Khoa học" (Controlled Experimentation). Nếu chúng ta thay đổi tập câu hỏi test set giữa các lần thử, sự biến động của điểm số F1 hay Hit Rate sẽ bị nhiễu loạn bởi độ khó dễ của đề thi mới. Việc khóa giữ **một tập test set duy nhất** đảm bảo mọi sự thay đổi trong hiệu suất RAG Agent (tụt dốc từ 100% xuống 60% rồi leo trở lại 100%) hoàn toàn có nguyên nhân kiên cố duy nhất: là do **sự thoái hóa và sự phục hồi của dữ liệu bên trong vector store**.
5. **Repair được xem là thành công dựa trên artifact và metric nào?**
   Một chu trình Repair (Khôi phục) được công nhận thành công tường minh khi thỏa mãn song song 2 lớp chứng cứ trong `data/reports/corruption_report.md`:
   - *Lớp chất lượng (Observability evidence):* `repaired_quality.json` phải hồi ngược hiển thị trạng thái `PASSED` (tuyên bố hết lỗi rỗng/trùng lặp) và `repaired_freshness.json` đạt `PASSED` (xác thực dữ liệu đã tươi mới trở lại).
   - *Lớp trí tuệ RAG (Metric evidence):* Chỉ số tìm kiếm `retrieval_hit_rate` và điểm suy luận của Agent (`mean_token_f1`, `judge_accuracy`) phải phá tang hố sụt của giai đoạn Corrupted để bay bổng ngược về đúng tham chiếu hoàn hảo của mốc Baseline gốc (tức phục hồi lại `100% Hit Rate` và `50% Judge Accuracy`).

## 8. Phân tích kết quả

### Metrics chính

Dữ liệu được lấy thực tế từ tệp đối soát tự động của dự án tại `data/reports/corruption_report.md`:

| Metric/signal | Baseline (Chuẩn gốc) | Corrupted ( Bị lỗi) | Repaired (Phục hồi) | Nhận xét của cá nhân (Góc nhìn Ingestion Engineer) |
| :--- | :---: | :---: | :---: | :--- |
| `retrieval_hit_rate` | **100.0%** | **60.0%** | **100.0%** | Sự suy giảm 40% cho thấy khi mất 2 bài mới nhất và tiêu đề bị truncate, vector embedding rơi vào trạng thái vỡ ngữ nghĩa. Khôi phục lại từ Raw Records lập tức đẩy Hit Rate chễm chệ ở đỉnh 100%. |
| `mean_token_f1` | **0.2465** | **0.1248** | **0.2465** | Điểm F1 sụt hơn 50% ở tập Corrupted vì khi summary bị xóa trắng hoặc bị nhét rác `[CORRUPTED NOISE %%%]`, RAG Agent buộc phải thêu dệt đáp án mù quáng. Khi Re-ingested thành công, điểm về y nguyên. |
| `judge_accuracy` | **50.0%** | **20.0%** | **50.0%** | Tương tự F1, khi ngữ cảnh thu thập bị thoái hóa, khả năng đưa ra kết luận đúng thực sự theo đánh giá của LLM Judge lập tức chạm đáy (rớt còn 20/100). Sau Repair thăng hạng lại như cũ. |
| **Quality checks** | `PASSED` | `FAILED` | `PASSED` | Trạm quan trắc phát huy uy lực cực đỉnh: cờ lập tức phất `FAILED` tại Phase Corrupted khi bắt chíp 2 hàng summary trắng xóa và hàng trùng lặp lén chèn vào. Phục hồi xong trở lại `PASSED`. |
| **Freshness status** | `PASSED` | `FAILED` | `PASSED` | Ngay khi các bản ghi bị bơm sai ngày xuất bản về tận năm 2020 (`age_days > 2300`), trạm Freshness phán lệnh `FAILED` tức khắc. Sau khi nạp lại ngày chuẩn từ bản thô gốc, cờ `PASSED` sáng bừng trở lại. |

### Kết luận từ số liệu

Hoàn thành hai chuỗi nguyên nhân–bằng chứng thực chứng:
1. **[Data corruption: Xóa hàng, rỗng tóm tắt, nhét văn bản nhiễu]** $\rightarrow$ **[Quality/Freshness signals lật sang cờ FAILED đỏ lòm]** $\rightarrow$ **[Agent metric lâm nguy: Hit Rate thảm bại rớt 40%, Judge accuracy bốc hơi 30%]**.
2. **[Repair action: Replay/Source Re-ingestion từ bản thô `raw_records.json`]** $\rightarrow$ **[Quality/Freshness signals hân hoan rực cờ PASSED]** $\rightarrow$ **[Agent metric khôi phục trọn vẹn 100% bằng mức đỉnh cao của Baseline]**.

- **Corruption nào ảnh hưởng rõ nhất và vì sao?**
  Qua phân tích số liệu và vết tích ma trận vector, hành động **Xóa các bài báo mới nhất (Drop latest records)** và **Tẩy trắng summary (Blank summary)** gây ảnh hưởng thảm khốc nhất đến `retrieval_hit_rate` và F1. Lý do: RAG phụ thuộc 100% vào `text_for_embedding` (vốn được ghép chính từ Title và Summary). Khi Summary trở thành chuỗi rỗng `""` hoặc bài báo gốc biến mất khỏi cơ sở dữ liệu, mô hình MiniLM hoàn toàn mù đường, không có bất kỳ vector nơ-ron nào để khớp lệnh với câu hỏi truy suất, dẫn đến hiện tượng Hallucination (tiềm tàng ảo giác) trầm trọng nơi LLM.
- **Kết quả nào khác với kỳ vọng ban đầu?**
  Ban đầu, tôi kỳ vọng khi bơm rác nhiễu `[CORRUPTED NOISE %%%]` vào một số bản ghi, cỗ máy tìm kiếm vector MiniLM sẽ có đủ sự thông minh ngữ nghĩa để tự lướt qua từ rác và vẫn duy trì Hit Rate xấp xỉ 90-100%. Tuy nhiên, kết quả thực tế kinh ngạc cho thấy: sự xuất hiện của chuỗi rác vô nghĩa phá vỡ vĩnh viễn trọng tâm khoảng cách Cosine Distance (Cosine similarity) của ma trận nơ-ron vector, làm cho các tài liệu rác bị văng ra xa vùng liên quan, và LLM khi buộc phải nhai nuốt đoạn rác này đã hoang mang tột độ, làm `mean_token_f1` chẻ đôi thê thảm từ `0.2465` xuống `0.1248`.

## 9. Điều học được và hướng cải thiện

### Ba điều quan trọng nhất
1. **Về Data Pipeline (Ingestion & Lineage):** Giá trị sinh mệnh của một kỹ sư Ingestion không nằm ở việc hút được bao nhiêu nghìn bài báo, mà ở tính **Bất biến và Khả năng truy vết (Immutable Raw Lineage)**. Nhờ việc chúng ta kỷ luật cất giữ file nguyên bản `crossref_records.json` không cho khâu hạ du gọt phá, ta mới có nguồn nước sạch thô để bấm nút *Source Re-ingestion* cứu sống hệ thống ở Phase 2.
2. **Về Data Quality & Observability:** "Đừng bao giờ đặt cược lòng tin vào dữ liệu thượng nguồn". Một cổng giám sát Fail-closed Clean Gate cùng các hệ thống rà soát Freshness là chốt chặn sinh tử cản phá dữ liệu ung nhọt lọt vào cỗ xe tăng Vector Store.
3. **Về mối liên hệ giữa Dữ liệu và RAG Agent:** Trong kỷ nguyên Agentic AI, thuật toán LLM có hùng mạnh đến đâu (GPT-4 hay Gemini) cũng chỉ là con rối của dữ liệu (Data-bound). Dữ liệu bị bẩn (Dirty Data) là nhát chém thiêu rụi trí tuệ suy luận của Agent; đầu tư vào Data Pipeline chính là khâu tối ưu nhất cho hiệu năng của mọi AI Agent.

### Nếu có thêm thời gian
Nếu có thêm thời gian, tôi sẽ nghiên cứu và tích hợp cơ chế **Tải đồng bộ nhiều nguồn có giải quyết xung đột (Multi-Source Fallback Ingestion & De-duplication Cache)** cho module Ingestion. Thay vì chỉ cậy nhờ độc nhất vào Crossref API, tôi sẽ cắm thêm họng hút từ **arXiv API** hoặc **OpenAlex**. Khi Crossref ném về một bản ghi khuyết Summary hoặc tiêu đề lỗi, luồng Ingestion sẽ tự động ghé ngang nhà kho arXiv để mượn đoạn Summary hợp lệ trám bù vào (Cross-Referencing Imputation), đồng thời mã hóa chuỗi hàm băm SimHash trên nội dung bài báo nhằm triệt tiêu các bài viết lặp chéo giữa các nguồn trước cả khi gửi sang trạm Làm sạch!

## 10. Cam kết của thành viên

Đánh dấu sau khi tự kiểm tra:

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Mọi kết luận về kết quả đều có artifact hoặc metric để đối chiếu.
- [x] Tôi không ghi “đã chạy thành công” cho phần chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Đàm Minh Tuấn  
**Ngày xác nhận:** 2026-08-06
