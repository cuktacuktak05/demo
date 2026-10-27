"""Small local RAG retriever using TF-IDF for a zero-service demo."""
from pathlib import Path
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

DOCS_DIR = Path(__file__).resolve().parent.parent / "knowledge_base"

def load_documents():
    docs = []
    for path in sorted(DOCS_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        # Split files into paragraphs/chunks.
        for i, chunk in enumerate([x.strip() for x in text.split("\n\n") if x.strip()], start=1):
            docs.append({"source": f"{path.name}#chunk-{i}", "text": chunk})
    return docs

def retrieve(query: str, top_k: int = 3):
    docs = load_documents()
    if not docs:
        return []
    corpus = [d["text"] for d in docs]
    vectorizer = TfidfVectorizer(ngram_range=(1, 2), stop_words=None)
    matrix = vectorizer.fit_transform(corpus + [query])
    scores = cosine_similarity(matrix[-1], matrix[:-1]).flatten()
    ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
    return [
        {**docs[i], "score": float(score)}
        for i, score in ranked[:top_k]
        if score > 0
    ]
