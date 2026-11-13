# BÁO CÁO KIỂM TOÁN MÃ NGUỒN VÀ ĐỐI CHIẾU 9 KHUYẾN NGHỊ (PHASE 1 - REPOSITORY AUDIT)
**Dự án**: Enterprise GenAI Assistant for Legal Research  
**Nghiên cứu cơ sở**: Haki, Safaei, Magan & Griffiths (2025), *Integrating Generative AI Into Enterprise Platforms: Insights From Salesforce*, Information Systems Journal (ISJ).  
**Tài liệu thực nghiệm đối chiếu**: Báo cáo cuối kỳ `CSHTTT.pdf` (Nguyễn Thùy Linh - 24022680, Đặng Trần Tiến - 24022745, GVHD: TS. Nguyễn Thị Hậu).  
**Ngày thực hiện**: Tháng 11/2026.  
**Vai trò**: Senior Enterprise AI Architect & Research Software Engineer.

---

## 1. TỔNG QUAN HỆ THỐNG VÀ HIỆN TRẠNG KHO MÃ

Repository hiện tại là một nguyên mẫu học thuật (prototype) được xây dựng nhằm minh họa ở mức tối thiểu hai khuyến nghị kỹ thuật của bài báo Haki và cộng sự (2025): **Trust Layer (R5)** và **Kiến trúc Prompt kết hợp RAG (R6)** trong ngữ cảnh nghiệp vụ pháp lý ("Luật AI").

### 1.1 Cấu trúc thư mục hiện tại
```text
enterprise_genai_demo/
├── backend/
│   ├── __init__.py          (0 bytes)
│   ├── main.py              (FastAPI router: /health, /ask, /mask-test, /audit - 96 dòng)
│   ├── schemas.py           (Pydantic schemas: AskRequest, AskResponse, MaskTest* - 31 dòng)
│   ├── rag.py               (TF-IDF + Cosine similarity trên knowledge_base/*.md - 30 dòng)
│   ├── llm.py               (OpenAI-compatible client invocation, hardcoded prompt - 37 dòng)
│   └── trust.py             (Regex PII masking, check_role, 3-keyword toxicity filter - 36 dòng)
├── frontend/
│   ├── package.json         (Vite dev server)
│   ├── vite.config.js       (Proxy /ask, /health, /audit sang http://127.0.0.1:8000)
│   ├── index.html           (Giao diện web "Luật AI" - 440 dòng)
│   ├── app.js               (Logic frontend, chat state, mock history, hardcoded fallback - 662 dòng)
│   └── style.css            (Stylesheet giao diện)
├── knowledge_base/
│   ├── 01_paper_summary.md        (Tóm tắt bài báo Haki et al. - 6 chunks, 302 từ)
│   ├── 02_demo_security_notes.md  (Ghi chú an toàn demo - 3 chunks, 159 từ)
│   └── 03_domain.md               (Nội dung pháp lý 5 chủ đề - 6 chunks, 759 từ)
├── audit.log                (File log JSON Lines ghi metadata 17 request mẫu)
├── masking_unit_test.json   (File chứa kết quả test che PII 1.000 mẫu)
├── main.py                  (Giao diện cũ viết bằng Streamlit - 70 dòng)
├── ui_theme.py              (Theme hỗ trợ giao diện Streamlit cũ - 673 dòng)
├── requirements.txt         (FastAPI, uvicorn, requests, openai, scikit-learn, pydantic)
├── .env.example             (OPENAI_API_KEY, OPENAI_MODEL, OPENAI_BASE_URL)
└── README.md                (Tài liệu hướng dẫn chạy hệ thống trên Windows)
```

### 1.2 Entry Points và Luồng dữ liệu hiện tại
- **Backend Entry Point**: `backend/main.py:app` chạy trên Uvicorn cổng `8000`.
- **Frontend Entry Point**: `frontend/index.html` phục vụ bởi Vite cổng `5173`.
- **Luồng xử lý yêu cầu (`POST /ask`)**:
  1. Frontend gửi `question`, `role`, `use_rag` tới backend `/ask`.
  2. `check_role(role)` kiểm tra vai trò hợp lệ (`employee` hoặc `admin`).
  3. `mask_pii(question)` áp dụng regex che email, số điện thoại, CCCD 12 số thành placeholder `[..._REDACTED]`.
  4. Nếu `use_rag=True`, `retrieve(safe_question, top_k=3)` quét các file `.md` trong `knowledge_base/`, dùng TF-IDF và Cosine Similarity, trả về top-3 đoạn có điểm > 0.
  5. `generate_answer(safe_question, chunks, role)` ghép context vào chuỗi system prompt cứng và gọi `client.chat.completions.create()`.
  6. `check_output(answer)` kiểm tra chuỗi rỗng và 3 từ khóa tiếng Anh nguy hiểm (`kill yourself`, `build a bomb`, `make a weapon`).
  7. `audit(event)` ghi 1 dòng JSON vào `audit.log` (gồm `role`, `rag_enabled`, `retrieved_chunks`, `pii_masked`, `output_filtered`, `model`, `timestamp_utc`).
  8. Trả về `AskResponse` cho frontend hiển thị.

---

## 2. ĐỐI CHIẾU CHI TIẾT 9 KHUYẾN NGHỊ (HAKI ET AL., 2025) VỚI KHO MÃ VÀ BÁO CÁO CSHTTT.PDF

Bảng đối chiếu tổng hợp tình trạng hiện tại, bằng chứng mã nguồn, phát hiện từ báo cáo thực nghiệm `CSHTTT.pdf`, khoảng cách kỹ thuật (gap) và phương án kiến trúc cần nâng cấp:

| STT | Khuyến nghị (Haki et al., 2025) | Trạng thái hiện tại | Bằng chứng mã nguồn (File, dòng, hàm) | Phát hiện & Số liệu từ CSHTTT.pdf | Khoảng cách kỹ thuật (Gaps & Architectural Flaws) | Đề xuất giải pháp kiến trúc nâng cấp |
|---|---|---|---|---|---|---|
| **R1** | **Integrate GenAI as an Extension to Existing Platform Offerings** *(Tích hợp GenAI như phần mở rộng của dịch vụ nền tảng)* | **Một phần** (Partial) | `backend/main.py:43-75` (`def ask`)<br>`frontend/app.js:511-538` | Mục 5.2 & Bảng 5.1 (trang 52-53): Chỉ có 1 endpoint `/ask` xử lý toàn bộ luồng, chưa có sự tích hợp thống nhất giữa các tác vụ pháp lý; giao diện hiện như ứng dụng đơn lẻ. | - Các tác vụ chưa được module hóa thành các workflow/pipeline chuyên biệt.<br>- `frontend/app.js:543-614` chứa hàm `generateSmartLegalFallback()` sinh câu trả lời giả lập cố định khi backend mất kết nối, vi phạm nguyên tắc kiến trúc trung thực. | - Loại bỏ hoàn toàn hardcoded fallback sinh câu trả lời giả.<br>- Xây dựng Request Orchestrator thống nhất cho mọi tác vụ nghiên cứu pháp lý (Legal Research, Summary, Comparison, Analysis, Memo). |
| **R2** | **Develop Generic and Industry-Specific Use Cases** *(Phát triển các use cases chung và chuyên biệt theo ngành)* | **Một phần** (Partial) | `knowledge_base/03_domain.md`<br>`frontend/index.html:123-138`<br>`frontend/app.js:207-216` | Bảng 3.2, 3.3, 5.1 (trang 23, 24, 52): 5 chủ đề pháp lý trong `03_domain.md` (nồng độ cồn, ĐKDN, thuê mặt bằng, BHXH, tranh chấp lao động). Nút gợi ý prompt tĩnh. | - Chưa hỗ trợ 5 use case pháp lý chuẩn theo yêu cầu: (1) Legal Research, (2) Legal Summary, (3) Legal Comparison, (4) Legal Document Analysis, (5) Legal Memo.<br>- Giao diện chỉ có chat tự do, chưa có bộ chọn use case nghiệp vụ có cấu trúc. | - Bổ sung Task Selector trên giao diện.<br>- Xây dựng 5 pipeline nghiệp vụ tương ứng 5 use case pháp lý với template và output format chuẩn tắc. |
| **R3** | **Provide Tools to Customize and Develop GenAI Use Cases** *(Cung cấp công cụ tùy biến use case)* | **Rất hạn chế** (Minimal) | `frontend/index.html:361-395`<br>`frontend/app.js:243-250` | Bảng 5.1 (trang 53): Hộp thoại cài đặt chỉ cho đổi vai trò (`employee`/`admin`) và API URL; chưa có công cụ tạo hay tùy biến use case/prompt. | - Người dùng không thể tùy chỉnh Top-K, Similarity Threshold, Temperature, Model selection.<br>- Không thể tùy biến Prompt Template hay xem các phiên bản prompt khác nhau. | - Bổ sung bảng điều khiển tham số trên giao diện: Top-K, Similarity Threshold, Temperature, Model/Provider.<br>- Cung cấp bộ quản lý prompt template tập trung có thể cấu hình tham số. |
| **R4** | **Incorporate New Architecture Components to Support GenAI Capabilities** *(Bổ sung thành phần kiến trúc mới: LLM Gateway / Model Ecosystem)* | **Một phần** (Partial) | `backend/llm.py:9-37` (`def generate_answer`) | Bảng 3.1, 3.10 (trang 20, 32): Gọi trực tiếp OpenAI client. Log chỉ ghi nhận 1 model duy nhất `"openrouter/free"`. Có 2 lỗi gọi mô hình (11.8% thất bại). | - Logic gọi LLM dính chặt vào `llm.py`, thiếu tầng trừu tượng LLM Gateway.<br>- Không có cơ chế timeout, retry có giới hạn, chuyển đổi giữa nhiều model/provider độc lập (e.g. OpenAI, Anthropic/OpenRouter/Local Mock).<br>- Không đo lường latency của LLM API, không ghi nhận token usage hay chi phí ước tính. | - Thiết kế module `LLM Gateway` với `BaseModelAdapter` đa nhà cung cấp.<br>- Hỗ trợ timeout, bounded exponential backoff retry, latency tracking bằng `time.perf_counter()`, token accounting và cost estimator. |
| **R5** | **Establish a Trusted Environment** *(Môi trường tin cậy: Trust Layer toàn diện)* | **Một phần** (Partial) | `backend/trust.py:6-36`<br>`masking_unit_test.json` | Bảng 3.7 (trang 30): Regex PII nuốt khoảng trắng (M3, M4), sót dấu "+" (M5), nhầm CCCD 9 số / MST thành điện thoại (M10, M11), sót hộ chiếu, số TKNH, tên người (M12, M15, M19).<br>Bảng 3.8: Tệp `masking_unit_test.json` ghi `demask_roundtrip_exact=1.0` nhưng mã nguồn **hoàn toàn chưa có hàm demask**!<br>Bảng 3.9 (trang 31): Bộ lọc đầu ra chỉ có 3 cụm từ tiếng Anh, bỏ lọt câu độc hại tiếng Việt (F5). | - **Thiếu quy trình 10 bước** chuẩn của Trust Layer.<br>- Chưa có cơ chế Pseudonymization hai chiều (Masking -> Demasking Mapping Table).<br>- Regex thô sơ, gây false positives và false negatives nghiêm trọng.<br>- Hoàn toàn chưa có kiểm tra Prompt Injection / System Prompt Leakage.<br>- Bộ lọc an toàn đầu ra chỉ bắt từ khóa thô sơ, không kiểm tra ảo giác / căn cứ pháp lý.<br>- Không có cơ chế Output Grounding Validation và Citation Verification. | - Xây dựng Trust Layer Pipeline 10 bước chuẩn hóa.<br>- Triển khai Tokenized PII Pseudonymization hai chiều (Masking có bảng ánh xạ + Demasking đầu ra).<br>- Bổ sung bộ phát hiện Prompt Injection (jailbreak, leak system prompt).<br>- Xây dựng Output Safety đa ngữ (Việt - Anh) kèm phân loại độc hại.<br>- Triển khai Output Grounding Validator kiểm tra citation và hallucination. |
| **R6** | **Build Prompt Architecture** *(Kiến trúc Prompt phân lớp, Dynamic Grounding, Versioning & Feedback)* | **Một phần** (Partial) | `backend/llm.py:20-28`<br>`backend/rag.py:17-30` | Bảng 3.5, 3.6 (trang 27-28): 12 truy vấn trong miền đạt Top-1 91.7%, MRR 0.944; tuy nhiên **cả 3 truy vấn ngoài miền (Q13-Q15) đều bị gán đoạn không liên quan (điểm <= 0.037)** do không có ngưỡng từ chối (abstention threshold).<br>Bảng 3.5: Q1 về "Trust Layer" bị sai ở hạng 1 (chỉ xếp hạng 3, điểm 0.055).<br>Mục 3.6 (trang 34): Chưa đo chất lượng câu trả lời. | - Toàn bộ prompt là 1 f-string cứng trong `llm.py`, không tách lớp (System, Task, Context, Safety, Format).<br>- Dynamic Grounding thô sơ: chỉ lấy top-3 đoạn bất kể điểm thấp, không lọc context không liên quan, không có cơ chế Abstention ("Từ chối trả lời khi không đủ thông tin").<br>- Không có Prompt Versioning (ID, Version).<br>- Không có hệ thống lưu nhận User Feedback (thumbs up/down chỉ toast ở UI, không gửi về backend). | - Tách Prompt Architecture thành 5 lớp module hóa.<br>- Cung cấp bộ Prompt Templates chuẩn cho 5 legal use cases.<br>- Bổ sung Similarity Threshold và cơ chế Abstention tự động từ chối truy vấn ngoài miền.<br>- Đánh số phiên bản Prompt (Prompt Versioning) gắn vào Audit Metadata.<br>- Xây dựng API và cơ chế lưu trữ User Feedback Loop. |
| **R7** | **Implement GenAI-Specific Governance Mechanisms** *(Quản trị đặc thù cho GenAI: Audit Trail, Monitoring & Data Governance)* | **Một phần** (Partial) | `backend/main.py:33-38` (`audit`)<br>`audit.log`<br>`backend/schemas.py:12-14` | Bảng 3.10 (trang 32): `audit.log` chỉ ghi 7 trường tối thiểu. Không ghi latency, không ghi token, không ghi prompt version, không ghi chunk IDs/scores.<br>Mục 3.2.2: Cơ sở tri thức chưa phân biệt văn bản chính thức, sửa đổi, hết hiệu lực, tài liệu nội bộ. | - Audit trail chưa đủ thông tin phục vụ quản trị và đo lường SLA.<br>- Chưa có Performance Dashboard hiển thị số lượng request, latency P50/P95, tỉ lệ PII, tỉ lệ lọc, chi phí.<br>- Knowledge Base thiếu metadata quan trọng: Document ID, Số hiệu điều khoản, Ngày ban hành, Hiệu lực thi hành, Phân loại nguồn (Chính thức vs. Nội bộ). | - Mở rộng cấu trúc Audit Metadata toàn diện (Request ID, model, prompt version, chunk IDs, retrieval scores, latency breakdown, tokens, error, safety flag).<br>- Xây dựng trang Performance Dashboard & Metrics Aggregator.<br>- Chuẩn hóa Knowledge Base với metadata đầy đủ (Document ID, Article, Effective Date, Status: Current/Amended/Expired, Type: Official Law vs Internal Guidelines). |
| **R8** | **Establish Strategic Partnerships and Invest in GenAI Technologies** *(Quan hệ đối tác và đầu tư công nghệ - Góc độ kiến trúc: Provider-Independent Architecture)* | **Chưa có** (Missing) | `backend/llm.py` | Mục 5.2, Bảng 5.1: Báo cáo xem khuyến nghị này là không áp dụng cho prototype sinh viên vì mang tính chiến lược doanh nghiệp. | - Bài báo nêu tính phụ thuộc (vendor lock-in). Ở mức prototype, hiện tại backend gắn chặt với OpenAI SDK.<br>- Thiếu khả năng so sánh song song giữa các model/provider về latency, cost và output quality. | - Hiện thực hóa khuyến nghị này ở tầng kỹ thuật: Thiết kế kiến trúc **Provider-Independent Model Abstraction** (hỗ trợ OpenAI, Anthropic, Local Mock, v.v.).<br>- Cho phép chuyển đổi và so sánh benchmark giữa các nhà cung cấp. |
| **R9** | **Invest in Customer Education and Personalized Consulting** *(Đào tạo khách hàng & hướng dẫn sử dụng AI minh bạch)* | **Rất hạn chế** (Minimal) | `frontend/index.html:338-360`<br>`knowledge_base/02_demo_security_notes.md` | Bảng 5.1 (trang 53): README hướng dẫn cài đặt; ghi chú bảo mật demo; modal miễn trừ trách nhiệm pháp lý. Chưa có tài liệu hướng dẫn kỹ thuật prompt hay cách đọc trích dẫn cho người dùng. | - Chưa có tài liệu hướng dẫn người dùng cách đặt câu hỏi pháp lý hiệu quả.<br>- Chưa có giải thích minh bạch về nguồn gốc dữ liệu, ranh giới pháp lý và cách thẩm tra citation.<br>- Giao diện chưa có nhãn cảnh báo rõ ràng khi câu trả lời có độ tin cậy thấp. | - Xây dựng tài liệu hướng dẫn sử dụng và Prompt Guide cho nhân viên văn phòng luật.<br>- Bổ sung trực quan hóa Confidence Score, Grounding Badge và Citation Verification trực tiếp trên giao diện. |

---

## 3. PHÂN TÍCH THỰC NGHIỆM TỪ BÁO CÁO CSHTTT.PDF VÀ CÁC PHÁT HIỆN CỐT LÕI

Báo cáo `CSHTTT.pdf` đã chỉ ra những hạn chế rất cụ thể của mã nguồn hiện tại thông qua 5 kịch bản thực nghiệm (K1 đến K5):

### 3.1 Kịch bản K1 & K2: Thống kê và đánh giá truy xuất RAG
- **Thực trạng**: Cơ sở tri thức gồm 3 file với 15 đoạn văn bản (`01_paper_summary.md` [6 chunks], `02_demo_security_notes.md` [3 chunks], `03_domain.md` [6 chunks]).
- **Kết quả thực nghiệm**:
  - Với 12 truy vấn trong miền: Top-1 đạt 91.7% (11/12), Top-3 đạt 100%, MRR đạt 0.944.
  - Tuy nhiên, câu hỏi cốt lõi Q1 (*"Trust Layer có vai trò gì trong kiến trúc GenAI doanh nghiệp?"*) bị xếp sai ở hạng 1 (chỉ đứng hạng 3, điểm số rất thấp 0.055) do TF-IDF bị nhiễu bởi các từ dừng phổ biến tiếng Việt (*"vai trò"*, *"trong"*, *"kiến trúc"*).
  - Điểm Q6 (*"Audit log ghi những thông tin gì"*) chỉ đạt 0.058, sát với đoạn xếp thứ hai (0.056).
  - **Lỗ hổng nghiêm trọng**: Cả 3 truy vấn ngoài miền (Q13: *Thủ tục ly hôn đơn phương*, Q14: *Cách nấu phở bò ngon*, Q15: *Quyền thừa kế đất đai của con nuôi*) đều bị gán cho các đoạn tài liệu không liên quan với điểm số từ 0.021 đến 0.037. Mã nguồn `backend/rag.py:29` chỉ lọc `score > 0`. Do đó, câu hỏi nấu phở hay ly hôn vẫn được bơm vào prompt như một "ngữ cảnh pháp lý", dẫn đến nguy cơ mô hình hallucination nghiêm trọng.
  - **Khuyến nghị từ báo cáo**: Cần bổ sung **ngưỡng điểm tối thiểu (retrieval threshold)** (khoảng 0.05 - 0.10) và cơ chế **từ chối trả lời (Abstention)** khi không tìm thấy tài liệu phù hợp.

### 3.2 Kịch bản K3 & K3b: Kiểm thử che dữ liệu PII
- **Thực trạng**: `backend/trust.py` dùng 3 biểu thức regex đơn giản.
- **Kết quả thực nghiệm**:
  - Biểu thức regex số điện thoại `(?:\+?84|0)(?:\s|-)?(?:\d[\s-]?){8,10}` bị lỗi nuốt khoảng trắng ở cuối, dẫn đến việc chữ tiếp theo bị dính chặt vào placeholder (Ví dụ M3, M4: `SĐT [PHONE_REDACTED]của chị Lan`).
  - Tiền tố `+` trong số điện thoại quốc tế bị bỏ rơi lại (Ví dụ M5: `Gọi +[PHONE_REDACTED]nhé`).
  - Gán nhãn sai: CMND 9 số cũ và Mã số thuế (10 chữ số) bị gán nhãn thành `[PHONE_REDACTED]` (M10, M11).
  - Bắt nhầm (False Positive): Số đơn hàng 12 chữ số bị che nhầm thành `[ID_NUMBER_REDACTED]` (M16).
  - Bỏ sót (False Negative): Số hộ chiếu (`B1234567`), số tài khoản ngân hàng (16 số), họ tên và ngày sinh hoàn toàn bị bỏ sót (M12, M15, M19).
  - File `masking_unit_test.json` ghi nhận tỉ lệ `demask_roundtrip_exact = 1.0`, nhưng mã nguồn thực tế **hoàn toàn chưa có hàm demasking**.

### 3.3 Kịch bản K4: Kiểm thử bộ lọc đầu ra
- **Thực trạng**: `backend/trust.py:29` chỉ có 3 cụm từ tiếng Anh cố định (`kill yourself`, `build a bomb`, `make a weapon`).
- **Kết quả thực nghiệm**: Câu F5 tiếng Việt (*"Hướng dẫn chế tạo vũ khí"*) lọt qua 100% không bị chặn. Cụm từ tiếng Anh vô hại có chứa từ khóa có thể bị chặn nhầm. Không có cơ chế kiểm tra nội dung bịa đặt (hallucination) hay nội dung không căn cứ.

### 3.4 Kịch bản K5: Phân tích nhật ký kiểm toán (Audit Trail)
- **Thực trạng**: File `audit.log` gồm 17 dòng JSON.
- **Kết quả thực nghiệm**: Chỉ ghi 7 trường định danh tối thiểu. Không hề ghi thời gian phản hồi (latency breakdown), không ghi prompt ID/version, không ghi số token tiêu thụ, không ghi ID và điểm của các chunk được truy xuất, không có thông tin chi phí và không ghi nhận phản hồi của người dùng.

---

## 4. BẢN ĐỒ KIẾN TRÚC MỤC TIÊU (TARGET ARCHITECTURE)

Nhằm đáp ứng đầy đủ các khuyến nghị của bài báo Haki et al. (2025) và giải quyết triệt để các tồn tại được báo cáo `CSHTTT.pdf` chỉ ra, kiến trúc hệ thống sẽ được nâng cấp thành luồng xử lý phân lớp rõ ràng:

```text
                               [ Người dùng / Chuyên viên pháp lý ]
                                                │
                                                ▼
                     ┌─────────────────────────────────────────────────────┐
                     │          Vite + HTML5/CSS3/Vanilla JS               │
                     │  - Legal Task Selector (5 use cases)                │
                     │  - Chat Interface & Real-time Citations             │
                     │  - Grounding Badge & Confidence Alerts              │
                     │  - User Feedback Loop (Thumbs Up/Down + Notes)      │
                     │  - Performance Dashboard & Benchmark Explorer       │
                     └──────────────────────────┬──────────────────────────┘
                                                │ REST API (JSON)
                                                ▼
                     ┌─────────────────────────────────────────────────────┐
                     │               FastAPI API Orchestrator              │
                     │  - POST /api/v1/legal/query                         │
                     │  - POST /api/v1/trust/mask-test                     │
                     │  - POST /api/v1/feedback                            │
                     │  - GET  /api/v1/governance/metrics                  │
                     │  - GET  /api/v1/evaluation/benchmark                │
                     └──────────────────────────┬──────────────────────────┘
                                                │
      ┌─────────────────────────────────────────┼─────────────────────────────────────────┐
      │                                         │                                         │
      ▼                                         ▼                                         ▼
┌───────────────────────────┐     ┌───────────────────────────┐     ┌───────────────────────────┐
│     AI TRUST LAYER        │     │      KNOWLEDGE BASE       │     │    PROMPT ARCHITECTURE    │
│                           │     │        & RAG ENGINE       │     │                           │
│ 1. Input Validation       │     │ 1. Document Schema        │     │ 1. Centralized Templates  │
│ 2. Context-Aware PII Det. │     │    - Metadata, Article,   │     │    - Legal Research       │
│ 3. PII Pseudonymization   │     │      Date, Validity       │     │    - Legal Summary        │
│    (Reversible Token Map) │     │ 2. Hybrid/Normalized      │     │    - Legal Comparison     │
│ 4. Prompt Safety &        │     │    Retrieval Engine       │     │    - Document Analysis    │
│    Injection Detection    │     │ 3. Score Thresholding     │     │    - Legal Memo           │
│ 5. Output Toxicity &      │     │    & Domain Abstention    │     │ 2. Dynamic Grounding      │
│    Harm Filter (VI/EN)    │     │ 4. Citation & Source      │     │ 3. Prompt Versioning      │
│ 6. Grounding & Faith-     │     │    Extraction             │     │ 4. Prompt Test Matrix     │
│    fulness Verification   │     │                           │     │                           │
│ 7. Safe Demasking         │     │                           │     │                           │
└─────────────┬─────────────┘     └─────────────┬─────────────┘     └─────────────┬─────────────┘
              │                                 │                                 │
              └─────────────────────────────────┼─────────────────────────────────┘
                                                │
                                                ▼
                     ┌─────────────────────────────────────────────────────┐
                     │         LLM GATEWAY & MODEL ECOSYSTEM               │
                     │  - Unified Provider Interface (OpenAI, Anthropic,   │
                     │    OpenRouter, Local Mock)                          │
                     │  - Timeout & Bounded Exponential Retry              │
                     │  - Latency Tracker (perf_counter resolution)        │
                     │  - Token Accounting & Cost Estimator                │
                     │  - Explicit Fallback Policy (No silent hardcoding)  │
                     └──────────────────────────┬──────────────────────────┘
                                                │
                                                ▼
                     ┌─────────────────────────────────────────────────────┐
                     │       GOVERNANCE, AUDIT & BENCHMARK SUITE           │
                     │  - Immutable Structured Audit Trail (JSON Lines)    │
                     │  - Real-time Governance Metrics (P50/P95 Latency)   │
                     │  - Automated Benchmark Harness                      │
                     │    * RAG Retrieval Metrics (P@K, R@K, MRR, nDCG)    │
                     │    * Trust Layer Metrics (PII P/R/F1, Safety)       │
                     │    * 4-Configuration Ablation Study (A, B, C, D)    │
                     └─────────────────────────────────────────────────────┘
```

---

## 5. KẾ HOẠCH NÂNG CẤP CHI TIẾT THEO CÁC PHASE TIẾP THEO

### Phase 2: Lập kế hoạch chi tiết (Development Plan)
- Xác định chi tiết từng module Python cần xây dựng mới hoặc tái cấu trúc trong `backend/`:
  - `backend/core/` (Orchestrator, config, exceptions).
  - `backend/trust/` (PII detector, reversible pseudonymizer, prompt injection guard, output safety guard, grounding validator).
  - `backend/rag/` (document loaders, structured metadata schema, hybrid/tuned retriever, threshold evaluator, abstention engine).
  - `backend/prompts/` (prompt manager, templates for 5 use cases, versioning registry).
  - `backend/gateway/` (base adapter, OpenAI/OpenRouter adapter, local mock adapter for zero-cost benchmark, latency & token tracker).
  - `backend/governance/` (structured audit logger, metrics aggregator, feedback store).
  - `backend/evaluation/` (eval datasets, retrieval evaluator, ablation benchmark harness).
- Cải tiến giao diện `frontend/`:
  - Loại bỏ hoàn toàn mock fallback.
  - Bổ sung use case switcher, source citation drawer, confidence badge, feedback widget.
  - Bổ sung tab/view Performance Dashboard & Evaluation Benchmark.

### Phase 3: Triển khai mã nguồn cốt lõi (Core Implementation)
- Triển khai theo thứ tự ưu tiên:
  1. Nâng cấp Knowledge Base & RAG Retrieval với ngưỡng abstention để chặn 100% câu hỏi ngoài miền (xử lý triệt để Q13, Q14, Q15).
  2. Nâng cấp Trust Layer đầy đủ (Masking 2 chiều, demasking, injection check, bilingual output guard, grounding check).
  3. Xây dựng Prompt Architecture tách lớp cho 5 use case pháp lý có versioning.
  4. Triển khai LLM Gateway đa mô hình kèm telemetry.
  5. Xây dựng Audit Logger & Metrics API.

### Phase 4: Thiết kế thực nghiệm và chạy Benchmark định lượng (Evaluation & Ablation Study)
- Xây dựng bộ test suite:
  - 30 câu hỏi đánh giá RAG (20 in-domain, 10 out-of-domain) đo Precision@K, Recall@K, MRR, nDCG, Abstention Accuracy.
  - 50 ca kiểm thử PII đa dạng đo Precision, Recall, F1 và Demasking Accuracy.
  - 20 ca kiểm thử Prompt Injection và Output Safety (Việt - Anh).
- Thực thi **Ablation Study trên 4 cấu hình**:
  - Cấu hình A: LLM Baseline (chỉ gọi LLM).
  - Cấu hình B: LLM + RAG (truy xuất tài liệu).
  - Cấu hình C: LLM + RAG + Prompt Architecture (Dynamic grounding + Task template).
  - Cấu hình D: Full System (kèm Trust Layer và Audit Trail).
- Đo đạc thực tế độ trễ chi tiết từng khâu bằng `time.perf_counter()`, tính toán P50, P95, Throughput, Token usage, Chi phí.
- Xuất dữ liệu thực nghiệm ra file JSON/CSV phục vụ trực quan hóa trên dashboard.

### Phase 5: Hoàn thiện tài liệu và bàn giao (Documentation)
- Cập nhật toàn bộ hệ thống tài liệu trong thư mục `docs/`:
  - `docs/architecture.md`
  - `docs/trust_layer.md`
  - `docs/prompt_architecture.md`
  - `docs/evaluation_methodology.md`
  - `docs/benchmark_results.md`
- Cập nhật `README.md` với hướng dẫn chạy hoàn chỉnh trên Windows.
