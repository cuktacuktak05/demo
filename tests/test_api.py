import pytest
from fastapi.testclient import TestClient
from backend.main import app
import backend.llm as llm_module
import backend.rag as rag_module


@pytest.fixture
def client():
    return TestClient(app)


def test_health_endpoint(client, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-mock-key")
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["llm_configured"] is True
    assert isinstance(data["kb_chunks"], int)
    assert data["kb_chunks"] > 0

    # Test health when API key is missing
    monkeypatch.setenv("OPENAI_API_KEY", "")
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["llm_configured"] is False


def test_ask_case_1_with_chunks(client, monkeypatch):
    """Ca 1: có chunk. Trả về source_type='kb', citations có score, retrieval metadata."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-mock-key")
    monkeypatch.setenv("RAG_MIN_SCORE", "0.15")

    # Mock LLM generation
    def mock_generate(question, chunks, role):
        assert len(chunks) > 0
        return "Theo tài liệu, mức phạt nồng độ cồn được quy định rõ.", "mock-model"

    monkeypatch.setattr("backend.main.generate_answer", mock_generate)

    res = client.post(
        "/ask",
        json={
            "question": "Quy định về nồng độ cồn và mức xử phạt khi lái xe ô tô",
            "role": "employee",
            "use_rag": True,
        },
    )

    assert res.status_code == 200
    data = res.json()
    assert data["answer"] == "Theo tài liệu, mức phạt nồng độ cồn được quy định rõ."
    assert data["source_type"] == "kb"
    assert len(data["citations"]) > 0

    # Kiểm tra cấu trúc từng citation
    for citation in data["citations"]:
        assert "title" in citation and citation["title"]
        assert "source" in citation and citation["source"]
        assert "snippet" in citation and citation["snippet"]
        assert "score" in citation and isinstance(citation["score"], float)
        assert citation["score"] >= 0.15

    # Kiểm tra retrieval metadata
    retrieval = data["retrieval"]
    assert retrieval["threshold"] == 0.15
    assert retrieval["n_chunks"] == len(data["citations"])
    assert retrieval["top_score"] is not None
    assert retrieval["top_score"] >= retrieval["threshold"]

    # Không có warning kiến thức chung vì có chunk từ tài liệu
    assert "Thông tin tham khảo chung, không trích từ tài liệu" not in data["warnings"]


def test_ask_case_2_without_chunks(client, monkeypatch):
    """Ca 2: không có chunk. Mặc định ALLOW_GENERAL_KNOWLEDGE=false, source_type='none'."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-mock-key")
    monkeypatch.setenv("ALLOW_GENERAL_KNOWLEDGE", "false")
    monkeypatch.setenv("RAG_MIN_SCORE", "0.15")

    # Mock retrieve trả về rỗng (hoặc câu hỏi không liên quan gì đến tài liệu)
    monkeypatch.setattr("backend.main.retrieve", lambda q, top_k=3: [])

    def mock_generate(question, chunks, role):
        assert len(chunks) == 0
        return "Không tìm thấy thông tin phù hợp trong tài liệu nội bộ.", "mock-model"

    monkeypatch.setattr("backend.main.generate_answer", mock_generate)

    res = client.post(
        "/ask",
        json={
            "question": "Thời tiết ngày mai ở sao Hỏa như thế nào?",
            "role": "employee",
            "use_rag": True,
        },
    )

    assert res.status_code == 200
    data = res.json()
    assert data["source_type"] == "none"
    assert data["citations"] == []
    assert data["retrieval"]["n_chunks"] == 0
    assert data["retrieval"]["threshold"] == 0.15
    assert data["retrieval"]["top_score"] is None

    # Mặc định ALLOW_GENERAL_KNOWLEDGE=false nên không có warning tham khảo chung
    assert "Thông tin tham khảo chung, không trích từ tài liệu" not in data["warnings"]


def test_ask_case_3_missing_api_key(client, monkeypatch):
    """Ca 3: thiếu API key. Trả về HTTP 503 với JSON {error_code, message}, không crash."""
    monkeypatch.setenv("OPENAI_API_KEY", "")

    res = client.post(
        "/ask",
        json={
            "question": "Quy định về nồng độ cồn khi lái xe ô tô?",
            "role": "employee",
            "use_rag": True,
        },
    )

    assert res.status_code == 503
    data = res.json()
    assert "error_code" in data
    assert "message" in data
    assert data["error_code"] == "LLM_NOT_CONFIGURED"
    assert "Chưa cấu hình OPENAI_API_KEY" in data["message"]


def test_ask_case_3_llm_error(client, monkeypatch):
    """Ca 3 mở rộng: Lỗi khi gọi mô hình LLM trả về HTTP 503 JSON {error_code, message}."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-mock-key")

    def mock_generate_fail(question, chunks, role):
        raise RuntimeError("OpenAI rate limit exceeded or connection timeout")

    monkeypatch.setattr("backend.main.generate_answer", mock_generate_fail)

    res = client.post(
        "/ask",
        json={
            "question": "Quy định về nồng độ cồn khi lái xe ô tô?",
            "role": "employee",
            "use_rag": True,
        },
    )

    assert res.status_code == 503
    data = res.json()
    assert "error_code" in data
    assert "message" in data
    assert data["error_code"] == "LLM_ERROR"
    assert "OpenAI rate limit exceeded" in data["message"]


def test_ask_case_4_allow_general_knowledge_true(client, monkeypatch):
    """Ca 4: ALLOW_GENERAL_KNOWLEDGE=true và không có chunk.
    Cho phép trả lời từ hiểu biết chung, thêm warning và source_type='none'."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-mock-key")
    monkeypatch.setenv("ALLOW_GENERAL_KNOWLEDGE", "true")

    # Giả lập không có chunk
    monkeypatch.setattr("backend.main.retrieve", lambda q, top_k=3: [])

    def mock_generate(question, chunks, role):
        assert len(chunks) == 0
        return "Theo hiểu biết chung, Trái Đất quay quanh Mặt Trời.", "mock-model"

    monkeypatch.setattr("backend.main.generate_answer", mock_generate)

    res = client.post(
        "/ask",
        json={
            "question": "Trái đất có quay quanh mặt trời không?",
            "role": "employee",
            "use_rag": True,
        },
    )

    assert res.status_code == 200
    data = res.json()
    assert data["answer"] == "Theo hiểu biết chung, Trái Đất quay quanh Mặt Trời."
    assert data["source_type"] == "none"
    assert data["citations"] == []
    assert data["retrieval"]["n_chunks"] == 0
    assert "Thông tin tham khảo chung, không trích từ tài liệu" in data["warnings"]


def test_rag_min_score_threshold_filtering(monkeypatch):
    """Kiểm tra ngưỡng RAG_MIN_SCORE: chunk dưới ngưỡng bị loại bỏ."""
    monkeypatch.setenv("RAG_MIN_SCORE", "0.99")
    # Với ngưỡng cực cao 0.99, không chunk nào đạt -> trả về rỗng
    chunks = rag_module.retrieve("luật giao thông", top_k=5)
    assert chunks == []

    # Với ngưỡng thấp 0.01, có chunk đạt yêu cầu
    monkeypatch.setenv("RAG_MIN_SCORE", "0.01")
    chunks = rag_module.retrieve("luật giao thông", top_k=5)
    assert len(chunks) > 0
    for c in chunks:
        assert c["score"] >= 0.01
        assert "title" in c
        assert "source" in c
        assert "text" in c


def test_llm_prompt_principles(monkeypatch):
    """Kiểm tra nguyên tắc trong backend/llm.py:
    1. Khi có chunks: chỉ dùng ngữ cảnh được cung cấp, không bịa nguồn.
    2. Khi không có chunks và ALLOW_GENERAL_KNOWLEDGE=false: chỉ dùng ngữ cảnh, không bịa nguồn.
    3. Khi không có chunks và ALLOW_GENERAL_KNOWLEDGE=true: cho phép trả lời từ hiểu biết chung."""
    from unittest.mock import MagicMock, patch

    monkeypatch.setenv("OPENAI_API_KEY", "sk-mock-key")

    with patch("backend.llm.OpenAI") as mock_openai:
        mock_client = MagicMock()
        mock_openai.return_value = mock_client
        mock_client.chat.completions.create.return_value.choices = [
            MagicMock(message=MagicMock(content="Mô phỏng câu trả lời."))
        ]

        # Case A: Có chunks
        chunks = [{"source": "test.md#chunk-1", "text": "Đoạn văn bản trích dẫn mẫu"}]
        llm_module.generate_answer("câu hỏi", chunks, "employee")
        call_system_content = mock_client.chat.completions.create.call_args[1]["messages"][0]["content"]
        assert "Chỉ sử dụng ngữ cảnh tài liệu được cung cấp" in call_system_content
        assert "không bịa nguồn hoặc dữ kiện" in call_system_content
        assert "Đoạn văn bản trích dẫn mẫu" in call_system_content

        # Case B: Không có chunks, ALLOW_GENERAL_KNOWLEDGE=false
        monkeypatch.setenv("ALLOW_GENERAL_KNOWLEDGE", "false")
        llm_module.generate_answer("câu hỏi", [], "employee")
        call_system_content = mock_client.chat.completions.create.call_args[1]["messages"][0]["content"]
        assert "Chỉ sử dụng ngữ cảnh tài liệu được cung cấp" in call_system_content
        assert "Không tìm thấy đoạn tài liệu phù hợp" in call_system_content

        # Case C: Không có chunks, ALLOW_GENERAL_KNOWLEDGE=true
        monkeypatch.setenv("ALLOW_GENERAL_KNOWLEDGE", "true")
        llm_module.generate_answer("câu hỏi", [], "employee")
        call_system_content = mock_client.chat.completions.create.call_args[1]["messages"][0]["content"]
        assert "Bạn được phép trả lời dựa trên hiểu biết chung" in call_system_content
        assert "Thông tin chỉ mang tính tham khảo chung, không trích từ tài liệu" in call_system_content


def test_ask_pii_masking_and_warnings(client, monkeypatch):
    """Kiểm tra PII được che và cảnh báo xuất hiện trong warnings."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-mock-key")

    def mock_generate(question, chunks, role):
        assert "[EMAIL_REDACTED]" in question
        return "Đã nhận câu hỏi sau khi che PII.", "mock-model"

    monkeypatch.setattr("backend.main.generate_answer", mock_generate)

    res = client.post(
        "/ask",
        json={
            "question": "Liên hệ tôi qua email user@example.com về quy định.",
            "role": "employee",
            "use_rag": False,
        },
    )

    assert res.status_code == 200
    data = res.json()
    assert any("[EMAIL_REDACTED]" in w for w in data["warnings"])

