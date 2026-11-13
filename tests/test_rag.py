"""Unit and integration test suite for RAG retrieval system (Session 2).
Tests:
- TF-IDF baseline retrieval
- BM25 Okapi lexical retrieval
- Dense Embedding semantic retrieval and caching
- Hybrid retrieval with Reciprocal Rank Fusion
- Standardized chunk schema & metadata integrity
- Traceable citations (no generic citations)
- Threshold filtering & Insufficient Context rejection
- Out-of-domain and adversarial query handling
"""
import os
import pytest
from pathlib import Path
from backend.rag import (
    retrieve,
    retrieve_tfidf,
    retrieve_bm25,
    retrieve_embedding,
    retrieve_hybrid,
    load_documents,
    count_kb_chunks,
    get_min_score,
    get_active_method,
    CALIBRATED_THRESHOLDS,
    CACHE_FILE,
)


def test_kb_loading_and_chunk_count():
    """Verify KB loading and chunk count."""
    docs = load_documents()
    assert len(docs) > 0
    assert count_kb_chunks() == len(docs)
    assert len(docs) >= 200  # Detailed split of documents and draft law


def test_standardized_chunk_schema():
    """Verify all chunks adhere to standardized metadata structure (Session 2 & 3)."""
    docs = load_documents()
    required_keys = [
        "chunk_id",
        "document_id",
        "content",
        "text",
        "title",
        "source",
        "article",
        "effective_from",
        "effective_to",
        "legal_status",
        "citation",
    ]
    for doc in docs:
        for k in required_keys:
            assert k in doc, f"Missing key '{k}' in doc {doc.get('chunk_id')}"
        assert doc["content"] == doc["text"]
        assert doc["chunk_id"] == doc["source"]
        assert doc["legal_status"] in ("effective", "draft", "academic_paper", "internal_note", "reference")


def test_legal_status_and_citation_traceability():
    """Verify draft documents have draft status and citations are non-generic and traceable."""
    docs = load_documents()
    
    # Check 04_luat_giao_thong.md is explicitly marked as draft
    draft_chunks = [d for d in docs if d["document_id"] == "04_luat_giao_thong.md"]
    assert len(draft_chunks) > 0
    for d in draft_chunks:
        assert d["legal_status"] == "draft"
        assert "Dự thảo Luật GTĐB" in d["citation"]
        assert "Hệ thống quy chuẩn pháp luật Việt Nam" not in d["citation"]

    # Check 03_domain.md has effective status
    effective_chunks = [d for d in docs if d["document_id"] == "03_domain.md" and d["chunk_id"] != "03_domain.md#chunk-1"]
    assert len(effective_chunks) > 0
    for d in effective_chunks:
        assert d["legal_status"] == "effective"
        assert d["citation"] != ""
        assert "Hệ thống quy chuẩn pháp luật Việt Nam" not in d["citation"]

    # Check specific article citation for alcohol regulation
    chunk_alcohol = next(d for d in docs if d["chunk_id"] == "03_domain.md#chunk-2")
    assert chunk_alcohol["article"] == "Điều 5"
    assert "Nghị định 100/2019/NĐ-CP - Điều 5" in chunk_alcohol["citation"]
    assert chunk_alcohol["effective_from"] == "2020-01-15"


def test_baseline_tfidf_retrieval():
    """Test TF-IDF baseline returns correct scores and metadata."""
    query = "Mức xử phạt nồng độ cồn đối với người điều khiển xe ô tô"
    results = retrieve_tfidf(query, top_k=3, threshold=0.10)
    assert len(results) > 0
    assert results.status == "relevant"
    assert results.method == "tfidf"
    assert results.latency_ms > 0
    top = results[0]
    assert top["retrieval_method"] == "tfidf"
    assert top["chunk_id"] == "03_domain.md#chunk-2"
    assert top["score"] >= 0.10


def test_bm25_retrieval():
    """Test BM25 Okapi lexical retrieval."""
    query = "Hồ sơ đăng ký thành lập doanh nghiệp theo Luật Doanh nghiệp"
    results = retrieve_bm25(query, top_k=3, threshold=4.0)
    assert len(results) > 0
    assert results.status == "relevant"
    assert results.method == "bm25"
    top = results[0]
    assert top["retrieval_method"] == "bm25"
    assert top["chunk_id"] == "03_domain.md#chunk-3"
    assert top["score"] >= 4.0


def test_embedding_semantic_retrieval_and_caching():
    """Test dense embedding semantic search and disk cache reuse."""
    query = "Lái xe hơi sau khi uống bia rượu thì bị tước bằng lái xe bao lâu?"
    results = retrieve_embedding(query, top_k=3, threshold=0.35)
    assert len(results) > 0
    assert results.status == "relevant"
    assert results.method == "embedding"
    assert any(c["chunk_id"] == "03_domain.md#chunk-2" for c in results[:3])
    assert results[0]["score"] >= 0.35

    # Check cache file exists on disk
    assert CACHE_FILE.exists()


def test_hybrid_retrieval():
    """Test Hybrid retrieval combining BM25 and Semantic Embeddings with RRF."""
    query = "Tỷ lệ đóng bảo hiểm xã hội bắt buộc hàng tháng của người sử dụng lao động"
    results = retrieve_hybrid(query, top_k=3, threshold=0.02)
    assert len(results) > 0
    assert results.status == "relevant"
    assert results.method == "hybrid"
    assert results[0]["chunk_id"] == "03_domain.md#chunk-5"
    assert results[0]["score"] >= 0.02


def test_insufficient_context_on_out_of_domain():
    """Verify out-of-domain query triggers insufficient_context and returns NO chunks."""
    query = "Cách nấu phở bò Hà Nội thơm ngon chuẩn vị truyền thống"
    for method in ["tfidf", "embedding", "hybrid"]:
        results = retrieve(query, top_k=3, method=method)
        # Low similarity chunks must NEVER be returned as evidence!
        assert len(results) == 0
        assert results.status == "insufficient_context"
        assert results.is_insufficient is True


def test_empty_and_whitespace_query_handling():
    """Test handling of empty or whitespace queries."""
    for empty_q in ["", "   ", "\n\t"]:
        res = retrieve(empty_q)
        assert len(res) == 0
        assert res.status == "empty_query"
        assert res.is_insufficient is True


def test_threshold_calibration_and_rejection():
    """Verify threshold filtering strictly excludes low-confidence chunks."""
    # When threshold is set extremely high, all chunks are rejected
    res = retrieve("luật giao thông đường bộ", top_k=5, threshold=0.99, method="tfidf")
    assert len(res) == 0
    assert res.status == "insufficient_context"

    # With calibrated threshold, relevant chunks pass
    res_calibrated = retrieve("luật giao thông đường bộ", top_k=3, threshold=0.15, method="tfidf")
    assert len(res_calibrated) > 0
    for c in res_calibrated:
        assert c["score"] >= 0.15


def test_env_var_method_switching(monkeypatch):
    """Test switching retrieval methods via environment variable RAG_METHOD."""
    monkeypatch.setenv("RAG_METHOD", "bm25")
    res_bm25 = retrieve("bảo hiểm xã hội bắt buộc", top_k=2)
    assert res_bm25.method == "bm25"
    assert res_bm25[0]["retrieval_method"] == "bm25"

    monkeypatch.setenv("RAG_METHOD", "embedding")
    res_emb = retrieve("bảo hiểm xã hội bắt buộc", top_k=2)
    assert res_emb.method == "embedding"
    assert res_emb[0]["retrieval_method"] == "embedding"
