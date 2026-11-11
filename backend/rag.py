"""Small local RAG retriever using TF-IDF for a zero-service demo."""
import os
from pathlib import Path
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

DOCS_DIR = Path(__file__).resolve().parent.parent / "knowledge_base"


def get_min_score() -> float:
    try:
        return float(os.getenv("RAG_MIN_SCORE", "0.15"))
    except (ValueError, TypeError):
        return 0.15


def load_documents():
    docs = []
    if not DOCS_DIR.exists():
        return docs

    for path in sorted(DOCS_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        
        # Extract default file title from first '# ' heading if available
        doc_title = path.stem.replace("_", " ").title()
        for line in text.splitlines():
            line_s = line.strip()
            if line_s.startswith("# "):
                doc_title = line_s.lstrip("# ").strip()
                break

        # Split files into paragraphs/chunks.
        for i, chunk in enumerate([x.strip() for x in text.split("\n\n") if x.strip()], start=1):
            chunk_lines = [l.strip() for l in chunk.splitlines() if l.strip()]
            chunk_title = doc_title
            if chunk_lines and chunk_lines[0].startswith("#"):
                chunk_title = chunk_lines[0].lstrip("#").strip()

            docs.append({
                "title": chunk_title,
                "source": f"{path.name}#chunk-{i}",
                "text": chunk,
            })
    return docs


def count_kb_chunks() -> int:
    return len(load_documents())


def retrieve(query: str, top_k: int = 6) -> list[dict]:
    if not query or not query.strip():
        return []

    docs = load_documents()
    if not docs:
        return []

    corpus = [d["text"] for d in docs]
    vectorizer = TfidfVectorizer(ngram_range=(1, 2), stop_words=None)
    matrix = vectorizer.fit_transform(corpus + [query])
    scores = cosine_similarity(matrix[-1], matrix[:-1]).flatten()
    ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
    min_score = get_min_score()

    return [
        {**docs[i], "score": float(score)}
        for i, score in ranked[:top_k]
        if score >= min_score
    ]
