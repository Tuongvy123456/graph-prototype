# Ngữ cảnh dự án Cross Paper GraphRAG

## 1. Mục đích của file

Đọc toàn bộ file này trước khi triển khai. Đây là đặc tả định hướng cho Codex trong VS Code, không phải mô tả code đã tồn tại. Khảo sát repository và AGENTS.md trước; giữ nguyên công việc hiện có của người dùng. Nếu có mâu thuẫn giữa file này và yêu cầu mới của người dùng, ưu tiên yêu cầu mới.

Mục tiêu trước mắt là xây prototype backend local hoạt động thật: text/PDF → entity mentions → thông tin cú pháp clause → claim có nguồn → entity resolution tối thiểu → Neo4j → truy vấn graph và evidence. Triển khai module độc lập để có thể so sánh với pipeline không dùng cú pháp hoặc NER. Không biến mọi thành phần dự kiến thành tính năng đã được chứng minh.

## 2. Toàn dự án

Tên tiếng Việt: GraphRAG Liên-Bài-Báo cho Khám phá Kết nối Đa-Bước Ẩn trong Tài liệu Khoa học.

Tên tiếng Anh: Cross-Paper GraphRAG for Discovering Hidden Multi-Hop Connections in Scientific Literature.

Ba trụ cột:
1. Xây typed KG liên bài báo và cross-paper entity resolution.
2. Tìm và giải thích kết nối đa bước giữa concepts/methods, mỗi hop có evidence nguồn.
3. Leiden community detection và LLM community summarization cho câu hỏi tổng quan.

Người dùng:
- Researcher: tạo corpus, hỏi tổng quan/quan hệ, xem path, graph và bài nguồn.
- Curator: review claim, merge/split entity và theo dõi chất lượng.

Corpus cuối dự kiến giới hạn trong một lĩnh vực con, vài trăm đến khoảng 2.000 bài. Prototype dùng tập nhỏ; ưu tiên tiếng Anh. Lĩnh vực cụ thể chưa chốt, không hard-code chỉ biomedical.

## 3. Quan hệ với PathRAG

PathRAG là nền nghiên cứu và baseline retrieval. Hướng cải tiến tập trung indexing graph construction: dùng cấu trúc ngữ pháp trong extraction/validation và bảo toàn điều kiện, phủ định, nguồn.

Không tuyên bố PathRAG chỉ có entity hoặc không chunking. Không gọi lưu thêm nhãn SVO là đóng góp nghiên cứu đã xác nhận. Cần giữ retrieval/generation tương đương khi so graph mặc định với graph mới.

Để tích hợp PathRAG, phải kiểm tra source/version, interface graph, node/edge representation và cách embedding thực tế. Chưa có source PathRAG trong repo thì tạo adapter contract, ghi rõ chưa tích hợp. Traversal Cypher đơn giản chỉ là baseline, không được gọi là thuật toán PathRAG.

Claim node trong Neo4j có thể cần projection entity–relation cho retrieval. Mỗi cạnh projection giữ claim_id để truy ngược. Không đếm số cạnh kỹ thuật đi qua Claim node là số hop ngữ nghĩa.

## 4. Môi trường và trạng thái lựa chọn

Người dùng code bằng VS Code trên Windows, PC RTX 5060 Ti 16 GB. Laptop khi bảo vệ yếu hơn; không giả định có GPU 16 GB. Không tự giả định vị trí Ollama, Neo4j hoặc model cache.

| Thành phần | Lựa chọn | Vai trò và trạng thái |
|---|---|---|
| IDE | VS Code | Đã chọn |
| Graph DB | Neo4j | Đã chọn |
| Runtime LLM | Ollama | Đã chọn dùng thử local |
| Backend | Python, FastAPI | Hướng triển khai chính |
| LLM | qwen3.5:9b | Chính dự kiến; chưa xác nhận tối ưu |
| LLM | qwen3:8b | Đối chứng/ứng viên thay thế |
| LLM | qwen3.5:4b | Backup; phải thử trên laptop |
| NER | urchade/gliner_medium-v2.1 | Chính dự kiến cho tiếng Anh |
| NER | urchade/gliner_multi-v2.1 | Ứng viên đa ngôn ngữ |
| NER | DyGIE++ checkpoint SciERC | Đối chứng nghiên cứu tương lai |
| Cú pháp | spaCy en_core_web_trf | Chính dự kiến |
| Cú pháp | spaCy en_core_web_sm | Đối chứng/backup nhẹ |
| Embedding | qwen3-embedding:0.6b | Ứng viên khởi đầu |
| PDF | PyMuPDF | Đề xuất; phải kiểm tra extraction |
| Schema | Pydantic | Validate cấu trúc |
| Frontend | React hoặc Next.js | Chưa chốt, chưa ưu tiên prototype |

GLiNER và spaCy chạy bằng Python, không qua ollama pull. NER mặc định spaCy không đáp ứng sẵn Method/Dataset/Concept. SciBERT base không phải checkpoint NER fine-tuned hoàn chỉnh. GLiNER là generalist, không mặc định tốt trên scientific corpus. Mọi model phải được đánh giá.

Kiểm tra phiên bản thực tế và tương thích trước khi lock dependencies; không bịa số phiên bản. Cài PyTorch GPU đúng khả năng driver/GPU nếu cần; CPU vẫn phải dùng được cho NER/parser. Không đổi cấu hình máy toàn cục không cần thiết. Tải model/cài package theo môi trường và quyền thực tế, báo rõ nếu bị chặn.

## 5. Pipeline xây KG

### 5.1 Parse và chunk

PyMuPDF lấy text, trang; lưu file hash và paper_id ổn định. Làm sạch header/footer lặp có kiểm soát. PDF hai cột/bảng có thể sai thứ tự, cần preview text. Không tuyên bố section extraction đúng nếu chỉ lấy raw text. PDF scan không có text phải báo cần OCR, không tạo graph rỗng rồi báo thành công.

Chia theo đoạn/câu, giới hạn context model; giữ chunk_id, paper_id, section nếu xác định được, trang và offsets nguồn. Overlap không được tạo claim trùng.

### 5.2 NER và cú pháp

GLiNER nhận nhãn đề xuất: scientific method, dataset, scientific concept, research task, evaluation metric. Ánh xạ sang Method/Dataset/Concept/Task/Metric. Author ưu tiên metadata. Có định nghĩa từng nhãn; Concept không là mọi danh từ.

Output mention: ID, text, type, char start/end, chunk ID, extractor và score. Score không được coi là xác suất đúng đã hiệu chuẩn. Tách input theo giới hạn GLiNER và map offsets lại chunk; không âm thầm truncate.

spaCy nhận cùng text, trả tokens, POS, dependency, sentence boundaries. Viết logic riêng nhận diện clause patterns và vai trò ngữ pháp; không giả định parser tự trả mẫu SVO hoàn chỉnh.

Ưu tiên SVO, SVC, SV; giữ trạng ngữ làm qualifiers. SVA/SVOA/SVOO/SVOC là mở rộng. Cho OTHER/UNKNOWN. Voice, polarity, modality lưu riêng. SV có thể là event không có object; không tạo entity giả.

NER và parser độc lập, kết hợp qua offsets. Có thể chạy tuần tự để tránh tranh VRAM.

### 5.3 Qwen extraction

Gửi chunk gốc + mentions ứng viên + syntax hints + schema vào Ollama. Dùng structured output theo JSON schema Pydantic, temperature thấp, timeout và retry giới hạn. Chọn context vừa phải và log cấu hình. JSON đúng không bảo đảm semantic correctness.

Output: mentions, claims, relation direction, original predicate, normalized predicate, grammatical roles, clause pattern, voice, polarity, modality, qualifiers, evidence spans.

Cho phép Qwen bổ sung mention NER bỏ sót nhưng phải map được vào span nguồn. Không dùng schema có phần phát biểu tự do làm evidence giả. Thông tin thiếu để null, không đoán dataset/metric.

Nếu chỉ sinh kết quả từ prompt text và syntax hints thì đó là LLM relation extraction có hỗ trợ cú pháp, không tự gọi là OIE engine chuyên biệt. OIE riêng là module ứng viên tương lai.

### 5.4 Validation

Kiểm tra schema, references, enum, offsets, exact source spans, IDs. Sai schema retry giới hạn; hết retry ghi failed/review, không báo success. Evidence tồn tại chỉ là kiểm tra cấu trúc, không chứng minh entailment.

Có thể thêm lượt LLM validation nhưng cùng model có thể lặp lỗi. Status claim: accepted, needs_review hoặc rejected; định nghĩa rõ accepted nghĩa là qua các kiểm tra nào, không đồng nghĩa chuyên gia xác nhận. Claim mơ hồ không tham gia graph retrieval mặc định nếu chưa review.

### 5.5 Entity resolution

Giữ phân biệt mention và canonical entity. Prototype: exact-name/alias được xác nhận, kiểm tra type và ngữ cảnh; không auto-merge cùng tên khác nghĩa. Cases mơ hồ giữ riêng/review.

Embedding tên + type + context tạo ứng viên canonical gần nhất, không quyết định merge bằng cosine similarity đơn lẻ. Quy tắc, LLM hoặc curator xác nhận. Giữ resolution provenance và hỗ trợ review; automatic semantic resolution đầy đủ ngoài phạm vi đầu tiên.

### 5.6 Neo4j và indexes

Persist Paper, Chunk, Mention, Entity, Claim; Evidence có thể là node hoặc span fields trên Claim. Unique constraints, parameterized Cypher, stable IDs và idempotency. Không để LLM thực thi Cypher.

Qualifiers/roles JSON lồng nhau phải flatten, serialize hoặc tạo nodes; Neo4j property không nhận dict tùy ý. Không gộp claim khác polarity, điều kiện hoặc nguồn thành kết luận chung. Bản claim trùng cùng source span được khử lặp, claim từ nguồn khác giữ evidence riêng.

Vector index trong Neo4j là lựa chọn dự kiến; dimension lấy từ output model thật. Version index/model phải đồng nhất; đổi embedding thì rebuild index được quản lý rõ.

## 6. Data contracts dự kiến

| Record | Trường tối thiểu |
|---|---|
| Paper | paper_id, title nullable, source_path/hash, metadata |
| Chunk | chunk_id, paper_id, text, page/section nullable, source mapping |
| Mention | mention_id, chunk_id, text, entity_type, start, end, extractor, score nullable |
| Entity | entity_id, canonical_name, entity_type, aliases, description nullable |
| Claim | claim_id, subject_mention_id, object_mention_id nullable, predicate, raw_predicate, clause, qualifiers, evidence, status |
| Clause | pattern, grammatical_subject nullable, verb nullable, grammatical_object nullable, voice, polarity, modality nullable |
| Evidence | chunk_id, text, start, end, source mapping |
| Run | run_id, model/checkpoint revision, prompts/version, settings, timestamps, latency, errors |

Entity types và predicate vocabulary phải cấu hình được. Unknown predicate giữ raw text và review, không âm thầm chuyển thành RELATED_TO. Clause unknown không mặc định extraction thất bại. Mọi mention/claim vẫn trace được đến input.

Liên kết đề xuất:
- Paper HAS_CHUNK Chunk.
- Mention IN_CHUNK Chunk; Mention REFERS_TO Entity.
- Claim SUBJECT Entity; Claim OBJECT Entity nếu có.
- Claim SUPPORTED_BY Chunk; Claim ON_DATASET Entity khi có evidence.

Ví dụ nguồn giả định: “Method B is outperformed by Method A on Dataset D.”
- Grammatical subject: Method B; voice: PASSIVE.
- Semantic subject: Method A; predicate: OUTPERFORMS; object: Method B.
- Qualifier dataset: Dataset D; metric: null.
- Không ép passive thành SVO theo thứ tự từ.

## 7. Luồng hỏi đáp

Câu hỏi → entity/intent identification → tìm canonical nodes bằng alias + vector → retrieval paths → lấy claim/qualifiers/evidence → Qwen trả lời có nguồn.

Giai đoạn prototype có endpoint duyệt graph, xem claim/evidence, path baseline giới hạn độ sâu; PathRAG adapter chỉ ghi implemented khi thực sự tích hợp thuật toán gốc. Global trend: Leiden và community summaries là phần sau.

A–B–C không tự chứng minh nhân quả hay scientific discovery. Phần giải thích nêu predicate/điều kiện từng hop; không sáng tạo edge thiếu bằng chứng. Temporal/retrospective hidden-link validation được thiết kế ở giai đoạn nghiên cứu sau.

## 8. Phạm vi prototype và nghiệm thu

Phải có:
- Ingestion text thật; PDF nhỏ khi parser hoạt động.
- GLiNER mentions và syntax module chạy thật, có thể bật/tắt.
- Ollama extraction theo schema, validation, lỗi rõ ràng.
- Neo4j persist/re-ingest idempotent; truy vấn entity, claim và evidence.
- Cấu hình model, service endpoint, CPU/GPU tách code.
- Bộ câu kiểm tra chủ động, bị động, phủ định, nhiều clause, SVC, SV và đại từ.
- Hai chế độ baseline text-only và syntax-assisted trên cùng LLM/schema; chế độ không NER để ablation.
- Run records và output JSON giúp review; phân biệt output thật với fixtures/mock.

Chưa cam kết: linking semantic quy mô lớn, PathRAG hoàn chỉnh, Leiden/trend đầy đủ, authentication/frontend hoàn chỉnh, hidden-link validated, latency <5 giây.

Tiêu chí cốt lõi: một claim lưu Neo4j có đúng entity, chiều quan hệ, clause và nguồn kiểm tra được. Không tuyên bố accuracy/F1 nếu chưa có gold và đo thật.

## 9. Đánh giá

Sanity set nhỏ chỉ kiểm tra chức năng. Dataset nghiên cứu cần annotation và tách validation/test. So model trên pipeline cố định, rồi giữ model cố định khi so phương pháp.

Đo entity/relation precision, recall, F1 với quy ước matching; lỗi chiều, phủ định, qualifiers; evidence support; latency, token/cost nếu có, memory, retry rate. Linking đo clustering F1/duplication rate theo định nghĩa. Downstream đo path correctness và evidence-grounded answer quality. Không dùng self-reported LLM confidence làm ground truth.

## 10. Kiến trúc code đề xuất

Module tách biệt: config, schemas, document_parser, chunker, ner, syntax, ollama_client, extractor, validator, entity_resolution, embeddings, graph_store, retrieval, evaluation và API/CLI.

Có thể dùng FastAPI với CLI dùng chung services; chọn cấu trúc theo repo thật. Các chức năng/API dự kiến: health, ingest text/PDF, run status, entities search, claim detail/evidence, graph neighborhood và path baseline. Không cần dựng frontend ở bước đầu.

Biến môi trường đề xuất:
- OLLAMA_HOST, OLLAMA_MODEL, OLLAMA_EMBED_MODEL.
- GLINER_MODEL, SPACY_MODEL, NER_DEVICE, SYNTAX_DEVICE.
- NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD, NEO4J_DATABASE.
- EXTRACTION_MODE, ENABLE_NER, ENABLE_SYNTAX, ENABLE_LLM_VALIDATION.
- CHUNK_SIZE, CHUNK_OVERLAP, OLLAMA_NUM_CTX, REQUEST_TIMEOUT.

Bổ sung .env.example không credentials thật; .gitignore .env, model cache, venv và dữ liệu nhạy cảm. Neo4j có thể là instance hiện có hoặc Docker tùy máy; không bắt buộc Docker nếu chưa chạy được. Dependency/model loading lỗi phải có hướng dẫn thực tế.

## 11. Demo PC và laptop

PC thực hiện ingestion và model chính. Laptop dùng KG đã chuẩn bị, chạy UI/API nhẹ hoặc gọi backend PC qua mạng riêng có xác thực. Không mở trực tiếp Neo4j/Ollama public.

Backup: graph local, khám phá không LLM, model nhỏ đã thử, video ingestion. Cache phải ghi nhãn. Không trộn kết quả model backup vào kết quả nghiên cứu model chính.

## 12. Yêu cầu khi Codex triển khai

1. Kiểm tra repo và môi trường trước, không ghi đè code đang có.
2. Triển khai một luồng nhỏ end-to-end rồi mở rộng từng module.
3. Không cần hỏi lại các lựa chọn đã nêu; dùng cấu hình mặc định đề xuất và cho đổi bằng env.
4. Chỉ hỏi khi thiếu thông tin bắt buộc như thông tin instance/credential; không bịa.
5. Chưa có service thật vẫn viết adapter và test unit độc lập. Không báo integration passed khi không kết nối được.
6. Test có ý nghĩa: offset mapping, passive direction, negation preservation, claim duplication, schema errors và graph idempotency khi có Neo4j.
7. GPU unsupported phải báo và hỗ trợ CPU nếu khả thi; không tự sửa hệ thống vô hạn.
8. README có lệnh PowerShell và hướng dẫn chạy, cấu hình, test, giới hạn. Ghi phiên bản và kết quả test thực tế.
9. Nếu model chính chưa có, không tự dùng model khác rồi bỏ qua; fallback phải rõ tên/cấu hình.
10. Hoàn thành code và verification trong phạm vi khả thi, báo rõ implemented, tested, blocked và deferred.

## 13. Nguồn tham khảo

- Proposal nhóm: Bản sao của FA26SE007_CROSS_PAPER_GRAPHRAG_FOR_DISCOVERING_HID_huongntc2.pdf.
- PathRAG: https://arxiv.org/abs/2502.14902 ; https://github.com/BUPT-GAMMA/PathRAG
- GLiNER: https://huggingface.co/urchade/gliner_medium-v2.1
- spaCy: https://spacy.io/models/en ; https://spacy.io/usage/linguistic-features
- Ollama: https://docs.ollama.com/capabilities/structured-outputs ; https://ollama.com/library/qwen3.5
- Embedding: https://ollama.com/library/qwen3-embedding
- Neo4j: https://neo4j.com/docs/python-manual/current/
- DyGIE++: https://github.com/dwadden/dygiepp

Đọc tài liệu chính thức và kiểm tra API hiện tại khi triển khai; model cards chỉ xác nhận khả năng được mô tả, không chứng minh tối ưu cho dữ liệu nhóm.
