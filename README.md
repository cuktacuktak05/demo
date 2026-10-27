# Enterprise GenAI Assistant — demo cuối kỳ

Prototype Python minh họa **RAG + Trust Layer** theo các ý tưởng trong bài báo:

> Haki, K., Safaei, D., Magan, A., & Griffiths, M. (2025). *Integrating Generative AI Into Enterprise Platforms: Insights From Salesforce*. Information Systems Journal. https://doi.org/10.1111/isj.12593

## 1. Phân biệt nghiên cứu và thiết kế demo

### Nội dung được bài báo hỗ trợ
- Tổ chức các khuyến nghị theo Platform Capability, Platform Architecture và Platform Governance.
- Đề cập trusted environment/Trust Layer để quản lý truy cập dữ liệu, bảo vệ tính ẩn danh, giám sát đầu ra và xử lý yêu cầu về zero data retention.
- Đề cập prompt architecture, prompt templates, context grounding/dynamic grounding và Retrieval-Augmented Generation (RAG).

### Phần do demo đề xuất
- FastAPI làm backend API và Streamlit làm giao diện.
- TF-IDF làm bộ truy xuất đoạn văn bản local để giảm phụ thuộc hạ tầng.
- Regex che một số mẫu email, số điện thoại và số định danh.
- Kiểm tra đầu ra theo quy tắc từ khóa; audit log chỉ lưu metadata.
- Gọi mô hình qua API tương thích OpenAI.

Đây là demo học thuật nhỏ, không phải mã nguồn chính thức Salesforce, không tái tạo đầy đủ Trust Layer thương mại và chưa đủ an toàn cho môi trường production.

## 2. Kiến trúc

```text
Người dùng
   |
Streamlit UI (8501)
   |
FastAPI /ask (8000)
   |
   +--> Trust Layer: role check demo + PII masking
   |
   +--> RAG Retriever: TF-IDF trên knowledge_base/*.md
   |
   +--> Prompt assembly: câu hỏi + đoạn nguồn truy xuất
   |
   +--> Model API (OpenAI hoặc endpoint tương thích)
   |
   +--> Output rule check + audit metadata
   |
Câu trả lời + nguồn RAG + ghi chú Trust Layer
```

## 3. Chạy trên Windows 10/11

### Bước 1 — Cài Python
Dùng Python 3.11 hoặc 3.12. Kiểm tra trong PowerShell:

```powershell
py --version
```

### Bước 2 — Giải nén và tạo môi trường ảo
Mở PowerShell trong thư mục `enterprise_genai_demo`:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Nếu PowerShell chặn kích hoạt môi trường ảo, có thể chạy:
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```
Hoặc bỏ qua kích hoạt và dùng trực tiếp `.\.venv\Scripts\python.exe -m pip ...`.

### Bước 3 — Cấu hình API key
```powershell
Copy-Item .env.example .env
notepad .env
```
Thay `OPENAI_API_KEY` bằng API key của bạn. Có thể đổi `OPENAI_MODEL` sang model mà tài khoản API của bạn được cấp quyền. Nếu dùng endpoint OpenAI-compatible khác, đặt `OPENAI_BASE_URL`.

Không commit file `.env` lên GitHub. ChatGPT Plus/Free không tự bao gồm API credit; API thường được tính phí riêng theo nhà cung cấp.

### Bước 4 — Khởi động backend
Trong PowerShell thứ nhất, ở thư mục gốc dự án:

```powershell
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

Kiểm tra:
- Health: http://127.0.0.1:8000/health
- Swagger: http://127.0.0.1:8000/docs

### Bước 5 — Khởi động Streamlit
Mở PowerShell thứ hai, vào cùng thư mục dự án và kích hoạt `.venv`, sau đó:

```powershell
streamlit run app.py
```

Mở URL Streamlit hiển thị trong terminal, thường là http://localhost:8501.

## 4. Kịch bản demo đề xuất

1. Hỏi: “Trust Layer có vai trò gì trong kiến trúc GenAI doanh nghiệp?” Quan sát nguồn RAG.
2. Hỏi câu có email giả lập, ví dụ `Liên hệ demo@example.com về chính sách dữ liệu.` Quan sát đầu vào sau khi che PII.
3. Tắt RAG và hỏi lại để thảo luận tác dụng của grounding.
4. Mở `audit.log` để cho thấy chỉ metadata truy vấn được ghi, không ghi prompt thô.
5. Thảo luận giới hạn: TF-IDF không phải vector database/semantic embedding; regex và keyword filter chỉ là guardrail minh họa.

## 5. Gọi API bằng Swagger
Mở `/docs`, chọn `POST /ask`, bấm **Try it out**, nhập:

```json
{
  "question": "Trust Layer có vai trò gì?",
  "role": "employee",
  "use_rag": true
}
```

## 6. Cấu trúc thư mục

```text
enterprise_genai_demo/
├── app.py
├── backend/
│   ├── __init__.py
│   ├── main.py
│   ├── schemas.py
│   ├── rag.py
│   ├── llm.py
│   └── trust.py
├── knowledge_base/
│   ├── 01_paper_summary.md
│   └── 02_demo_security_notes.md
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```

## 7. Giới hạn và hướng cải tiến
- Xác thực hiện tại chưa có; role là lựa chọn giao diện, không phải RBAC thực sự.
- PII masking bằng regex có thể bỏ sót dữ liệu nhạy cảm.
- Bộ lọc đầu ra chỉ là kiểm tra từ khóa, không phải mô hình phân loại độc hại.
- Không thể tuyên bố zero data retention nếu chưa xác minh chính sách của nhà cung cấp API.
- RAG TF-IDF phù hợp demo nhỏ; có thể nâng cấp embeddings + vector database, chunking tốt hơn và đánh giá retrieval.
- Bổ sung kiểm thử tự động, rate limiting, quản lý secrets và logging có cấu trúc trước khi triển khai thực tế.
