"""RAG Retrieval Module for Enterprise Legal Research Assistant.
Supports:
- Baseline TF-IDF
- BM25 (Okapi)
- Dense Embedding Semantic Search (FastEmbed multilingual / OpenAI)
- Hybrid Search (BM25 + Dense Embedding with Reciprocal Rank Fusion)
- Calibrated score thresholding & Insufficient Context detection
- Standardized chunk schema & traceable legal citations
"""
import hashlib
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from rank_bm25 import BM25Okapi

try:
    from fastembed import TextEmbedding
    FASTEMBED_AVAILABLE = True
except ImportError:
    FASTEMBED_AVAILABLE = False

logger = logging.getLogger(__name__)

DOCS_DIR = Path(__file__).resolve().parent.parent / "knowledge_base"
CACHE_DIR = Path(__file__).resolve().parent / ".cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
CACHE_FILE = CACHE_DIR / "embeddings_cache.json"

# Calibrated default thresholds for each retrieval method
CALIBRATED_THRESHOLDS = {
    "tfidf": 0.15,
    "bm25": 5.0,
    "embedding": 0.45,
    "hybrid": 0.028,
}


class RetrievalResult(list):
    """List subclass holding retrieved chunks, with metadata on retrieval quality and status."""

    def __init__(
        self,
        chunks: List[Dict[str, Any]],
        status: str = "relevant",
        query: str = "",
        top_score: Optional[float] = None,
        threshold: float = 0.15,
        method: str = "tfidf",
        latency_ms: float = 0.0,
        candidates_count: int = 0,
    ):
        super().__init__(chunks)
        self.status = status  # 'relevant' | 'insufficient_context' | 'empty_query'
        self.is_insufficient = status != "relevant"
        self.query = query
        self.top_score = top_score
        self.threshold = threshold
        self.method = method
        self.latency_ms = latency_ms
        self.candidates_count = candidates_count


def get_active_method() -> str:
    """Get active retrieval method from environment variable or default to tfidf (baseline)."""
    method = os.getenv("RAG_METHOD", "tfidf").strip().lower()
    if method not in ("tfidf", "bm25", "embedding", "hybrid"):
        return "tfidf"
    return method


def get_min_score(method: Optional[str] = None) -> float:
    """Get similarity threshold, honoring RAG_MIN_SCORE for tfidf or method-specific env, else calibrated default."""
    chosen_method = (method or get_active_method()).lower()
    
    # Check method-specific environment variable first (e.g. RAG_MIN_SCORE_HYBRID)
    method_env = os.getenv(f"RAG_MIN_SCORE_{chosen_method.upper()}")
    if method_env is not None:
        try:
            return float(method_env)
        except (ValueError, TypeError):
            pass

    env_score = os.getenv("RAG_MIN_SCORE")
    if env_score is not None:
        try:
            val = float(env_score)
            # If method is tfidf, honor RAG_MIN_SCORE directly
            if chosen_method == "tfidf":
                return val
            # If user explicitly set RAG_MIN_SCORE to something other than the 0.15 tfidf default, honor it
            if abs(val - 0.15) > 1e-4:
                return val
        except (ValueError, TypeError):
            pass

    return CALIBRATED_THRESHOLDS.get(chosen_method, 0.15)


def extract_metadata_for_chunk(doc_name: str, chunk_index: int, chunk_text: str, default_title: str) -> Dict[str, Any]:
    """Standardize metadata extraction according to legal research requirements (Session 2 & Session 3)."""
    article = None
    legal_status = "reference"
    effective_from = None
    effective_to = None
    citation = ""

    if doc_name == "01_paper_summary.md":
        legal_status = "academic_paper"
        effective_from = None
        effective_to = None
        article = default_title if default_title != "Tóm tắt bài báo — nguồn nền tảng demo" else None
        citation = f"[Salesforce Research (Haki et al., 2025)] ({doc_name}#chunk-{chunk_index})"

    elif doc_name == "02_demo_security_notes.md":
        legal_status = "internal_note"
        effective_from = None
        effective_to = None
        article = "Ghi chú bảo mật demo"
        citation = f"[Demo Security Guidelines] ({doc_name}#chunk-{chunk_index})"

    elif doc_name == "03_domain.md":
        legal_status = "effective"
        effective_to = None
        if chunk_index == 2:
            article = "Điều 5"
            effective_from = "2020-01-15"
            citation = f"[Nghị định 100/2019/NĐ-CP - Điều 5] ({doc_name}#chunk-{chunk_index})"
        elif chunk_index == 3:
            article = "Thủ tục đăng ký doanh nghiệp"
            effective_from = "2021-01-01"
            citation = f"[Luật Doanh nghiệp 2020 & Nghị định 01/2021/NĐ-CP] ({doc_name}#chunk-{chunk_index})"
        elif chunk_index == 4:
            article = "Hợp đồng thuê mặt bằng kinh doanh"
            effective_from = "2017-01-01"
            citation = f"[Bộ luật Dân sự 2015 & Luật Kinh doanh BĐS] ({doc_name}#chunk-{chunk_index})"
        elif chunk_index == 5:
            article = "Chế độ bảo hiểm xã hội bắt buộc"
            effective_from = "2016-01-01"
            citation = f"[Luật Bảo hiểm xã hội 2014] ({doc_name}#chunk-{chunk_index})"
        elif chunk_index == 6:
            article = "Giải quyết tranh chấp hợp đồng lao động"
            effective_from = "2021-01-01"
            citation = f"[Bộ luật Lao động 2019] ({doc_name}#chunk-{chunk_index})"
        else:
            article = None
            effective_from = "2020-01-01"
            citation = f"[Quy định pháp luật tham chiếu] ({doc_name}#chunk-{chunk_index})"

    elif doc_name == "04_luat_giao_thong.md":
        legal_status = "draft"  # Explicitly marked as draft!
        effective_from = None
        effective_to = None
        m = re.search(r"###\s+(Điều\s+\d+[^.\n]*)", chunk_text)
        if m:
            article = m.group(1).strip()
        else:
            article = default_title if default_title.startswith("Điều") else None
        
        art_label = f" - {article}" if article else ""
        citation = f"[Dự thảo Luật GTĐB (09/07/2018){art_label}] ({doc_name}#chunk-{chunk_index})"

    return {
        "article": article,
        "legal_status": legal_status,
        "effective_from": effective_from,
        "effective_to": effective_to,
        "citation": citation,
    }


def load_documents() -> List[Dict[str, Any]]:
    """Load and chunk documents with standardized metadata."""
    docs = []
    if not DOCS_DIR.exists():
        return docs

    for path in sorted(DOCS_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        doc_title = path.stem.replace("_", " ").title()
        for line in text.splitlines():
            line_s = line.strip()
            if line_s.startswith("# "):
                doc_title = line_s.lstrip("# ").strip()
                break

        current_article = None
        for i, chunk in enumerate([x.strip() for x in text.split("\n\n") if x.strip()], start=1):
            chunk_lines = [l.strip() for l in chunk.splitlines() if l.strip()]
            chunk_title = doc_title
            if chunk_lines and chunk_lines[0].startswith("#"):
                clean_heading = chunk_lines[0].lstrip("#").strip()
                chunk_title = clean_heading
                if clean_heading.startswith("Điều "):
                    current_article = clean_heading

            meta = extract_metadata_for_chunk(path.name, i, chunk, chunk_title)
            if not meta["article"] and current_article and path.name == "04_luat_giao_thong.md":
                meta["article"] = current_article
                meta["citation"] = f"[Dự thảo Luật GTĐB (09/07/2018) - {current_article}] ({path.name}#chunk-{i})"

            chunk_id = f"{path.name}#chunk-{i}"
            docs.append({
                "chunk_id": chunk_id,
                "document_id": path.name,
                "title": chunk_title,
                "source": chunk_id,
                "text": chunk,
                "content": chunk,
                "article": meta["article"],
                "effective_from": meta["effective_from"],
                "effective_to": meta["effective_to"],
                "legal_status": meta["legal_status"],
                "citation": meta["citation"],
            })
    return docs


def count_kb_chunks() -> int:
    return len(load_documents())


def simple_vi_tokenize(text: str) -> List[str]:
    """Tokenize Vietnamese text for BM25 with unigrams and bigrams."""
    text_clean = re.sub(r"[^\w\s]", " ", text.lower())
    words = [w for w in text_clean.split() if w]
    tokens = list(words)
    for i in range(len(words) - 1):
        tokens.append(f"{words[i]}_{words[i+1]}")
    return tokens


# ---------------------------------------------------------------------------
# Embedding Engine with local FastEmbed and disk caching
# ---------------------------------------------------------------------------
class DenseEmbeddingEngine:
    def __init__(self, model_name: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"):
        self.model_name = model_name
        self.model = None
        self._doc_embeddings = None

    def _init_model(self):
        if self.model is None and FASTEMBED_AVAILABLE:
            try:
                self.model = TextEmbedding(model_name=self.model_name)
            except Exception as e:
                logger.warning(f"Could not load FastEmbed model {self.model_name}: {e}")

    def get_doc_embeddings(self, docs: List[Dict[str, Any]]) -> Optional[np.ndarray]:
        if not docs:
            return None

        current_hashes = [hashlib.sha256(d["content"].encode("utf-8")).hexdigest() for d in docs]
        
        # Try loading from cache
        if CACHE_FILE.exists():
            try:
                with open(CACHE_FILE, "r", encoding="utf-8") as f:
                    cache = json.load(f)
                if (
                    cache.get("model") == self.model_name
                    and cache.get("hashes") == current_hashes
                    and "embeddings" in cache
                ):
                    self._doc_embeddings = np.array(cache["embeddings"], dtype=np.float32)
                    return self._doc_embeddings
            except Exception as e:
                logger.warning(f"Error loading embedding cache: {e}")

        self._init_model()
        if self.model is None:
            return None

        texts = [f"{d.get('article') or ''} {d['title']} {d['content']}".strip() for d in docs]
        try:
            embeddings = list(self.model.embed(texts))
            self._doc_embeddings = np.array(embeddings, dtype=np.float32)
            # Write to cache
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump({
                    "model": self.model_name,
                    "hashes": current_hashes,
                    "embeddings": self._doc_embeddings.tolist(),
                }, f)
            return self._doc_embeddings
        except Exception as e:
            logger.warning(f"Failed to generate dense embeddings: {e}")
            return None

    def embed_query(self, query: str) -> Optional[np.ndarray]:
        self._init_model()
        if self.model is None:
            return None
        try:
            q_emb = list(self.model.embed([query]))[0]
            return np.array(q_emb, dtype=np.float32)
        except Exception as e:
            logger.warning(f"Failed to embed query: {e}")
            return None


# Global singleton engine for high efficiency
_embedding_engine = DenseEmbeddingEngine()


# ---------------------------------------------------------------------------
# Individual Retriever Functions
# ---------------------------------------------------------------------------
def retrieve_tfidf(query: str, top_k: int = 3, threshold: Optional[float] = None) -> RetrievalResult:
    t0 = time.perf_counter()
    thresh = threshold if threshold is not None else get_min_score("tfidf")
    if not query or not query.strip():
        return RetrievalResult([], status="empty_query", query=query, threshold=thresh, method="tfidf")

    docs = load_documents()
    if not docs:
        return RetrievalResult([], status="insufficient_context", query=query, threshold=thresh, method="tfidf")

    corpus = [d["content"] for d in docs]
    vectorizer = TfidfVectorizer(ngram_range=(1, 2), stop_words=None)
    matrix = vectorizer.fit_transform(corpus + [query])
    scores = cosine_similarity(matrix[-1], matrix[:-1]).flatten()
    ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)

    max_score = float(ranked[0][1]) if ranked else 0.0
    passed = []
    for idx, score in ranked[:top_k]:
        if score >= thresh:
            passed.append({
                **docs[idx],
                "score": float(score),
                "retrieval_method": "tfidf",
            })

    latency_ms = (time.perf_counter() - t0) * 1000
    status = "relevant" if passed else "insufficient_context"
    return RetrievalResult(
        passed,
        status=status,
        query=query,
        top_score=max_score if max_score > 0 else None,
        threshold=thresh,
        method="tfidf",
        latency_ms=round(latency_ms, 2),
        candidates_count=len(docs),
    )


def retrieve_bm25(query: str, top_k: int = 3, threshold: Optional[float] = None) -> RetrievalResult:
    t0 = time.perf_counter()
    thresh = threshold if threshold is not None else get_min_score("bm25")
    if not query or not query.strip():
        return RetrievalResult([], status="empty_query", query=query, threshold=thresh, method="bm25")

    docs = load_documents()
    if not docs:
        return RetrievalResult([], status="insufficient_context", query=query, threshold=thresh, method="bm25")

    tokens = simple_vi_tokenize(query)
    if not tokens:
        return RetrievalResult([], status="insufficient_context", query=query, threshold=thresh, method="bm25")

    tokenized_corpus = [
        simple_vi_tokenize(f"{d.get('article') or ''} {d['title']} {d['content']}")
        for d in docs
    ]
    bm25 = BM25Okapi(tokenized_corpus)
    scores = bm25.get_scores(tokens)
    ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)

    max_score = float(ranked[0][1]) if ranked else 0.0
    passed = []
    for idx, score in ranked[:top_k]:
        if score >= thresh:
            passed.append({
                **docs[idx],
                "score": float(score),
                "retrieval_method": "bm25",
            })

    latency_ms = (time.perf_counter() - t0) * 1000
    status = "relevant" if passed else "insufficient_context"
    return RetrievalResult(
        passed,
        status=status,
        query=query,
        top_score=max_score if max_score > 0 else None,
        threshold=thresh,
        method="bm25",
        latency_ms=round(latency_ms, 2),
        candidates_count=len(docs),
    )


def retrieve_embedding(query: str, top_k: int = 3, threshold: Optional[float] = None) -> RetrievalResult:
    t0 = time.perf_counter()
    thresh = threshold if threshold is not None else get_min_score("embedding")
    if not query or not query.strip():
        return RetrievalResult([], status="empty_query", query=query, threshold=thresh, method="embedding")

    docs = load_documents()
    if not docs:
        return RetrievalResult([], status="insufficient_context", query=query, threshold=thresh, method="embedding")

    doc_embeddings = _embedding_engine.get_doc_embeddings(docs)
    q_emb = _embedding_engine.embed_query(query)

    if doc_embeddings is None or q_emb is None:
        logger.warning("Dense embeddings unavailable; falling back to TF-IDF.")
        return retrieve_tfidf(query, top_k=top_k, threshold=get_min_score("tfidf"))

    norms = np.linalg.norm(doc_embeddings, axis=1, keepdims=True)
    norms[norms == 0] = 1e-10
    normed_docs = doc_embeddings / norms

    q_norm = np.linalg.norm(q_emb)
    if q_norm == 0:
        return RetrievalResult([], status="insufficient_context", query=query, threshold=thresh, method="embedding")
    normed_q = q_emb / q_norm

    scores = np.dot(normed_docs, normed_q).flatten()
    ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)

    max_score = float(ranked[0][1]) if ranked else 0.0
    passed = []
    for idx, score in ranked[:top_k]:
        if score >= thresh:
            passed.append({
                **docs[idx],
                "score": float(score),
                "retrieval_method": "embedding",
            })

    latency_ms = (time.perf_counter() - t0) * 1000
    status = "relevant" if passed else "insufficient_context"
    return RetrievalResult(
        passed,
        status=status,
        query=query,
        top_score=max_score if max_score > 0 else None,
        threshold=thresh,
        method="embedding",
        latency_ms=round(latency_ms, 2),
        candidates_count=len(docs),
    )


def retrieve_hybrid(
    query: str,
    top_k: int = 3,
    threshold: Optional[float] = None,
    rrf_k: int = 60,
) -> RetrievalResult:
    """Hybrid Retrieval combining BM25 and Dense Embedding with Reciprocal Rank Fusion (RRF)."""
    t0 = time.perf_counter()
    thresh = threshold if threshold is not None else get_min_score("hybrid")
    if not query or not query.strip():
        return RetrievalResult([], status="empty_query", query=query, threshold=thresh, method="hybrid")

    docs = load_documents()
    if not docs:
        return RetrievalResult([], status="insufficient_context", query=query, threshold=thresh, method="hybrid")

    # 1. BM25 ranks
    tokens = simple_vi_tokenize(query)
    if tokens:
        tokenized_corpus = [
            simple_vi_tokenize(f"{d.get('article') or ''} {d['title']} {d['content']}")
            for d in docs
        ]
        bm25 = BM25Okapi(tokenized_corpus)
        bm25_scores = bm25.get_scores(tokens)
    else:
        bm25_scores = np.zeros(len(docs))
    bm25_ranked = [idx for idx, _ in sorted(enumerate(bm25_scores), key=lambda x: x[1], reverse=True)]

    # 2. Dense Embedding ranks
    doc_embeddings = _embedding_engine.get_doc_embeddings(docs)
    q_emb = _embedding_engine.embed_query(query)
    if doc_embeddings is not None and q_emb is not None:
        norms = np.linalg.norm(doc_embeddings, axis=1, keepdims=True)
        norms[norms == 0] = 1e-10
        normed_docs = doc_embeddings / norms
        q_norm = np.linalg.norm(q_emb)
        if q_norm > 0:
            emb_scores = np.dot(normed_docs, q_emb / q_norm).flatten()
        else:
            emb_scores = np.zeros(len(docs))
    else:
        emb_scores = np.zeros(len(docs))
    emb_ranked = [idx for idx, _ in sorted(enumerate(emb_scores), key=lambda x: x[1], reverse=True)]

    # Check semantic gating for out-of-domain rejection
    max_dense = float(np.max(emb_scores)) if len(emb_scores) > 0 else 0.0
    max_bm25 = float(np.max(bm25_scores)) if len(bm25_scores) > 0 else 0.0

    if max_dense < 0.42 and max_bm25 < 4.0:
        latency_ms = (time.perf_counter() - t0) * 1000
        return RetrievalResult(
            [],
            status="insufficient_context",
            query=query,
            top_score=max_dense,
            threshold=thresh,
            method="hybrid",
            latency_ms=round(latency_ms, 2),
            candidates_count=len(docs),
        )

    # 3. Reciprocal Rank Fusion
    candidate_indices = set(bm25_ranked[:20]) | set(emb_ranked[:20])
    bm25_rank_map = {idx: rank for rank, idx in enumerate(bm25_ranked, 1)}
    emb_rank_map = {idx: rank for rank, idx in enumerate(emb_ranked, 1)}

    hybrid_scores = []
    for idx in candidate_indices:
        r_bm25 = bm25_rank_map.get(idx, 1000)
        r_emb = emb_rank_map.get(idx, 1000)
        score_rrf = (1.0 / (rrf_k + r_bm25)) + (1.0 / (rrf_k + r_emb))
        
        # Penalize low dense confidence
        if emb_scores[idx] < 0.25 and bm25_scores[idx] < 4.0:
            score_rrf *= 0.3

        hybrid_scores.append((idx, score_rrf))

    ranked = sorted(hybrid_scores, key=lambda x: x[1], reverse=True)
    max_score = float(ranked[0][1]) if ranked else 0.0

    passed = []
    for idx, score in ranked[:top_k]:
        if score >= thresh:
            passed.append({
                **docs[idx],
                "score": float(score),
                "retrieval_method": "hybrid",
            })

    latency_ms = (time.perf_counter() - t0) * 1000
    status = "relevant" if passed else "insufficient_context"
    return RetrievalResult(
        passed,
        status=status,
        query=query,
        top_score=max_score if max_score > 0 else None,
        threshold=thresh,
        method="hybrid",
        latency_ms=round(latency_ms, 2),
        candidates_count=len(docs),
    )


# ---------------------------------------------------------------------------
# Unified Main Retrieval Entry Point
# ---------------------------------------------------------------------------
def retrieve(
    query: str,
    top_k: int = 3,
    threshold: Optional[float] = None,
    method: Optional[str] = None,
) -> RetrievalResult:
    """Unified retrieval interface.
    
    Dispatches to the configured retrieval method ('tfidf', 'bm25', 'embedding', 'hybrid').
    Applies calibrated similarity threshold filtering.
    Returns RetrievalResult list subclass: empty with status='insufficient_context' if no chunk meets threshold.
    """
    chosen_method = (method or get_active_method()).lower()

    if chosen_method == "tfidf":
        return retrieve_tfidf(query, top_k=top_k, threshold=threshold)
    elif chosen_method == "bm25":
        return retrieve_bm25(query, top_k=top_k, threshold=threshold)
    elif chosen_method == "embedding":
        return retrieve_embedding(query, top_k=top_k, threshold=threshold)
    elif chosen_method == "hybrid":
        return retrieve_hybrid(query, top_k=top_k, threshold=threshold)
    else:
        logger.warning(f"Unknown retrieval method '{chosen_method}', falling back to hybrid.")
        return retrieve_hybrid(query, top_k=top_k, threshold=threshold)
