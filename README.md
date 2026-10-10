# Cross-Paper GraphRAG prototype

Backend Python cho luồng `.txt`/PDF có text → chunks giữ offset/trang → GLiNER + spaCy (tùy chọn) → Ollama JSON schema → kiểm tra cấu trúc → canonical entity theo tên/loại → Neo4j → claim, bằng chứng và đường đi baseline. Chưa tích hợp thuật toán PathRAG; `pathrag_adapter.py` chỉ định nghĩa contract. Đường đi Cypher tính số hop giữa **entity**, dùng cạnh projection giữ `claim_id` để lấy lại nguồn.

## Môi trường và các mốc kiểm tra (10/10/2026)

- Windows, RTX 5060 Ti 16 GB, driver NVIDIA 616.92, Ollama 0.40.2.
- `python` là Microsoft Store alias; tìm được Python 3.13.14 đi kèm pgAdmin 4 nhưng không có `venv`. Đã tải `qwen3.5:9b` qua Ollama 0.40.2; `ollama list` và HTTP API xác nhận model có sẵn. Một yêu cầu JSON schema ngắn với `think=false` đã trả JSON hợp lệ; lần thử đầu với thinking mặc định trả `content` rỗng sau thời gian dài, nên code đặt `OLLAMA_THINK=false` theo mặc định. Neo4j HTTP `localhost:7474` không phản hồi; Docker daemon chưa chạy.
- Khi tạo repo, đã cài tạm dependency lõi vào `.deps` để kiểm tra rồi dọn đi: Pydantic 2.14.0, pytest 9.1.1, PyMuPDF 1.28.2, FastAPI 0.143.0, Neo4j driver 6.4.0. Unit tests: **6 passed**; smoke test import API và PDF text extraction: **passed**. `scripts/smoke_ollama.py` đã gọi Qwen thật với input tổng hợp: model sinh `Method A USES Dataset D`, validator sửa hai offset nguồn duy nhất gần kề, ghi audit và đặt claim `needs_review` vì offset sửa và clause unknown. Đây không phải phép đo accuracy. Không có output model giả trong repo.
- Cập nhật sau khi cài môi trường dự án: GLiNER 0.2.29 tải/nạp và nhận mention thật sau khi cài protobuf 6.33.6. `en_core_web_trf` 3.8.0 tải được nhưng DLL `_wordpiece` bị Windows Application Control chặn; môi trường hiện dùng fallback có tên rõ ràng `SPACY_MODEL=en_core_web_sm` (3.8.0). Một lần `syntax_assisted --no-persist` trên câu tổng hợp chạy xong với GLiNER + spaCy sm + Qwen, cho 1 claim `USES` trạng thái `accepted`, không sửa offset; kết quả nằm trong `data/runs/6b586e91-4759-4755-bf39-91cb7610a75a.json`. Neo4j local đã kết nối được; `scripts/verify_graph_transaction.py` đã ghi cùng claim hai lần trong transaction, kiểm tra không nhân bản node/cạnh, rồi rollback và xác nhận trạng thái trước/sau bằng nhau. Đây là kiểm tra tích hợp trên input tổng hợp, chưa phải đánh giá chất lượng trên paper thật.
- Kiểm tra mới nhất: **13 unit tests passed**. Run thật `e46dbdfb-b3f3-4d5f-a891-3cd9f5d1a25c` trên `data/sample.txt` hai câu tạo `Method A USES Dataset D` và `Method A OUTPERFORMS Method B` với `dataset=Dataset D`. Chunk gốc thất bại, fallback tách hai câu và xử lý xong; cả hai claim mang `needs_review` vì model trả thuộc tính clause `UNKNOWN`, predicate được chuẩn hóa từ raw text và có `adaptive_split`. Không ghi Neo4j (`--no-persist`); đây không phải xác nhận accuracy.

## Thiết lập Windows PowerShell

Cài Python 3.11+ từ [python.org](https://www.python.org/downloads/windows/) và mở terminal mới. Kiểm tra `py -3.11 --version` hoặc dùng phiên bản Python đã cài thay `3.11` bên dưới. Trong thư mục dự án:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e '.[nlp,test]'
python -m spacy download en_core_web_sm
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

Nếu terminal hiển thị `D:\...>` (Command Prompt/cmd.exe), dùng dấu nháy kép và file kích hoạt `.bat`:

```bat
py -3.11 -m venv .venv
.venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -e ".[nlp,test]"
python -m spacy download en_core_web_sm
if not exist .env copy .env.example .env
```

Sau khi sao chép `.env.example`, đặt `SPACY_MODEL=en_core_web_sm` trong `.env` trên PC này. `en_core_web_trf` là model chính dự kiến trong đặc tả nhưng plugin của nó bị Windows Application Control chặn trên máy hiện tại. Không cài lại `en_core_web_trf`/`spacy-curated-transformers` ở môi trường này: plugin của spaCy có thể được nạp ngay cả khi `.env` chọn model `sm`. Nếu `python` vẫn mở Microsoft Store trước khi kích hoạt môi trường ảo, dùng `py -3.11` để tạo `.venv`; sau khi kích hoạt, kiểm tra `python --version` phải là Python 3.11. Trong cmd, dấu nháy đơn không hoạt động như PowerShell và sẽ làm pip hiểu sai `'.[nlp,test]'`.

Nếu GLiNER báo `SentencePieceExtractor requires the protobuf library`, chạy `python -m pip install "protobuf>=4,<7"`; `protobuf` hiện đã được thêm vào extra `nlp`. Nếu Windows báo `An Application Control policy has blocked ... _wordpiece`, model `en_core_web_trf` không nạp được trên máy đó. Fallback đã kiểm chứng là cài `en_core_web_sm`, gỡ plugin transformer bị chặn khỏi `.venv`, rồi đặt `SPACY_MODEL=en_core_web_sm` trong `.env`. Không tự chuyển model ngầm: ghi tên model trong run JSON và so sánh kết quả theo đúng cấu hình.

`en_core_web_trf` và GLiNER cần thêm bộ nhớ. Nếu laptop yếu, sửa `.env`: `SPACY_MODEL=en_core_web_sm`, chạy `python -m spacy download en_core_web_sm`, và đặt `NER_DEVICE=cpu`, `SYNTAX_DEVICE=cpu`; có thể đặt `ENABLE_NER=false` hoặc `ENABLE_SYNTAX=false`. PC có thể thử GPU sau khi cài PyTorch CUDA phù hợp với driver từ [hướng dẫn PyTorch](https://pytorch.org/get-started/locally/); không mặc định cài CUDA. Thiết lập `NER_DEVICE=cuda` và `SYNTAX_DEVICE=cuda` chỉ sau khi kiểm tra `python -c "import torch; print(torch.cuda.is_available())"`. Các model Python tải vào cache khi dùng lần đầu; GLiNER **không** tải bằng Ollama.

Cài/chạy Ollama riêng, tải đúng model chính rồi kiểm tra:

```powershell
ollama pull qwen3.5:9b
ollama list
Invoke-RestMethod http://localhost:11434/api/tags
python .\scripts\smoke_ollama.py
```

Trong Command Prompt (`cmd.exe`), thay `Invoke-RestMethod` bằng `curl.exe`:

```bat
ollama list
curl.exe http://localhost:11434/api/tags
python scripts\smoke_ollama.py
```

`qwen3:8b` và `qwen3.5:4b` là lựa chọn có chủ đích qua `OLLAMA_MODEL`, không tự fallback. `OLLAMA_EMBED_MODEL` được giữ trong cấu hình cho giai đoạn vector retrieval; prototype hiện không gọi embedding.

### Neo4j bằng Docker Desktop

`compose.yaml` dùng Neo4j 5.26, chỉ mở cổng trên `127.0.0.1` và giữ dữ liệu trong Docker volume. Mở `.env` bằng `notepad .env`, điền **mật khẩu do bạn chọn** vào dòng `NEO4J_PASSWORD=` (ít nhất 8 ký tự; không gửi mật khẩu vào chat). Docker Compose và backend cùng đọc mật khẩu từ file này. Sau khi Docker Desktop đã chạy, trong PowerShell **hoặc cmd**:

```bat
docker compose up -d
docker compose ps
```

Lần đầu Docker sẽ tải image. Mở `http://localhost:7474`, đăng nhập username `neo4j` và mật khẩu vừa đặt. Backend dùng `bolt://localhost:7687`. Khi cần xem lỗi khởi động, chạy `docker compose logs --tail 50 neo4j`; để dừng dịch vụ, chạy `docker compose down` (volume dữ liệu vẫn được giữ). Nếu đã có Neo4j riêng, không chạy Compose mà sửa `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, `NEO4J_DATABASE` trong `.env`.

## Chạy và so sánh

```powershell
Set-Location D:\capstone\graph-prototype
.\.venv\Scripts\Activate.ps1
python -m pytest -q
crossgraph ingest .\data\quickstart.txt --no-persist
```

Các lệnh tương đương trong Command Prompt (`cmd.exe`), là terminal đang hiển thị `(.venv) D:\capstone\graph-prototype>` trên máy bạn:

```bat
cd /d D:\capstone\graph-prototype
.venv\Scripts\activate.bat
python -m pytest -q
crossgraph ingest data\quickstart.txt --no-persist
```

`data\quickstart.txt` là câu kiểm tra ngắn đã có sẵn. **Không tạo lại hoặc ghi đè `data\sample.txt`**; file đó có thể chứa ví dụ bạn đang nghiên cứu. Để chạy file hai câu hiện tại của bạn, dùng `crossgraph ingest data\sample.txt --no-persist` trong cmd, hoặc `crossgraph ingest .\data\sample.txt --no-persist` trong PowerShell. Xem `status`, `failed_chunks`, `claims` và file `data\runs\<run_id>.json`; `completed` chỉ nói pipeline chạy hết, mỗi claim vẫn phải xem `status` và `review_reasons`. Nếu một chunk nhiều câu không qua validation, pipeline thử tách nó một lần gần giữa tại ranh giới câu; run JSON ghi `split_attempts`, và claim từ chunk tách được gắn `needs_review` với lý do `adaptive_split`. Raw predicate `uses`/`outperformed` có thể được chuẩn hóa theo rule rõ ràng; run JSON ghi `predicate_repairs`, claim vẫn cần review.

Để mở API, chạy lệnh sau ở một terminal và giữ terminal đó mở:

```bat
python -m uvicorn crossgraph.api:app --host 127.0.0.1 --port 8000
```

Ở terminal thứ hai, mở `http://127.0.0.1:8000/docs` trong trình duyệt hoặc kiểm tra dịch vụ: `curl.exe http://127.0.0.1:8000/health/services` trong cmd; PowerShell có thể dùng `Invoke-RestMethod http://127.0.0.1:8000/health/services`. Endpoint `/` không có trang chủ nên trả 404 là bình thường. `--no-persist` không ghi Neo4j, vì vậy `/entities` sẽ không thấy dữ liệu của lần chạy thử này.

`data\quickstart.txt` và `data\sample.txt` là câu tổng hợp để kiểm tra kỹ thuật; chưa phải bài báo hay dữ liệu đánh giá. Với file thật, thay bằng đường dẫn đến `.txt` hoặc `.pdf` đang tồn tại; ví dụ `crossgraph ingest "D:\papers\my-paper.pdf"`. Bỏ `--no-persist` khi muốn ghi Neo4j, sau khi cấu hình Neo4j trong `.env`. Mỗi lần chạy ghi `data/runs/<run_id>.json`, kể cả lần lỗi sau khi vào pipeline. Nếu một chunk vẫn sai sau ba lượt validation hoặc Ollama trả JSON/schema không hợp lệ sau hai lần gọi, run tiếp tục xử lý các chunk khác và ghi `chunk_errors`: `partial` khi có claim hợp lệ, `failed` khi không có claim nào; CLI trả mã lỗi 2 và **không ghi Neo4j** nếu còn chunk lỗi. Lỗi JSON từ Ollama ghi thêm `done_reason` và độ dài phản hồi để chẩn đoán việc output bị cắt. Vì vậy `partial` không có nghĩa là tài liệu đã ingest đầy đủ. API `POST /ingest/text` nhận JSON `{ "text": "...", "title": "...", "persist": true }`; API còn có `GET /claims/{claim_id}`, `GET /entities/{entity_id}/neighbors`, `GET /paths/baseline?source=...&target=...&max_hops=3`. Bằng chứng claim gồm text, offset, chunk, trang, paper và đường dẫn nguồn. PDF scan không có text sẽ báo cần OCR.

Muốn kiểm tra thao tác Neo4j mà không để lại dữ liệu tổng hợp trong graph, dùng `python scripts\verify_graph_transaction.py data\runs\<run_id>.json`. Script ghi hai lần trong một transaction, đối chiếu số node/cạnh rồi rollback; thay `<run_id>` bằng ID của lần chạy có claim.

So hai chế độ trên cùng file và cùng `OLLAMA_MODEL`:

```powershell
$env:EXTRACTION_MODE = 'text_only'
crossgraph ingest .\data\sample.txt --no-persist
$env:EXTRACTION_MODE = 'syntax_assisted'
$env:ENABLE_NER = 'true'
$env:ENABLE_SYNTAX = 'true'
crossgraph ingest .\data\sample.txt --no-persist
$env:ENABLE_NER = 'false'
crossgraph ingest .\data\sample.txt --no-persist
```

Trong `cmd.exe`:

```bat
set EXTRACTION_MODE=text_only
crossgraph ingest data\sample.txt --no-persist
set EXTRACTION_MODE=syntax_assisted
set ENABLE_NER=true
set ENABLE_SYNTAX=true
crossgraph ingest data\sample.txt --no-persist
set ENABLE_NER=false
crossgraph ingest data\sample.txt --no-persist
```

`text_only` không tải NER/parser và chỉ đưa text vào LLM; `syntax_assisted` đưa mentions và clause hints nếu bật. Cùng schema, prompt version và normalized vocabulary. `GET /runs/{run_id}` trả output JSON của lần chạy. Các mẫu ở `tests/sanity_cases.jsonl` bao gồm chủ động, bị động (`B is outperformed by A`), phủ định, nhiều clause, SVC, SV và đại từ; đây là câu để review, không phải kết quả model. Chưa có gold set nên không có số accuracy/F1.

## Giới hạn và dữ liệu

`accepted` chỉ có nghĩa qua Pydantic, offset, reference và các quy tắc đơn giản; **không** khẳng định entailment hoặc review chuyên gia. Validator chỉ tự sửa offset khi có đúng một vị trí khớp với mention text trong phạm vi lệch tối đa 3 ký tự quanh offset model trả; claim được sửa luôn vào `needs_review`, và các lần sửa nằm trong `extraction_attempts` của run JSON. Nếu có nhiều vị trí gần nhau hoặc lệch quá xa, run báo lỗi để review thay vì đoán vị trí. `needs_review` không vào cạnh retrieval. Entity resolution mặc định chỉ ghép exact name + type **trong cùng paper** để tránh tự ghép đồng âm khác nghĩa xuyên paper. Để curator xác nhận liên kết xuyên paper, đặt `ENTITY_ALIASES_FILE=aliases.json` trong `.env`; file JSON là mảng các record như `[ { "entity_type": "Method", "name": "Method A", "canonical_name": "Method A" } ]`. Chỉ các tên/loại được liệt kê mới dùng canonical ID chung; file alias cần được review trước khi dùng. PDF hai cột/bảng có thể sai thứ tự; chưa có lọc header/footer lặp hoặc nhận diện section đáng tin cậy, nên hãy kiểm tra text trích xuất và trang trước khi ingest. Chưa có OCR, auth, frontend, Leiden, vector index/embedding, PathRAG thật hoặc answer generation. Khi demo trên laptop, ưu tiên gọi API trên PC qua mạng riêng có lớp xác thực/proxy do bạn cấu hình; không công khai Ollama/Neo4j.

Tham khảo API: [Ollama structured outputs](https://docs.ollama.com/capabilities/structured-outputs), [GLiNER model card](https://huggingface.co/urchade/gliner_medium-v2.1), [spaCy models](https://spacy.io/usage/models), [Neo4j Python driver](https://neo4j.com/docs/python-manual/current/).
