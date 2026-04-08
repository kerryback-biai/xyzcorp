"""RAG pipeline: ingest corporate documents and search them with TF-IDF + cosine similarity."""
import re
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

DOCUMENTS_DIR = Path(__file__).parent.parent.parent / "documents"

CHUNK_SIZE = 800       # characters per chunk (~200 tokens)
CHUNK_OVERLAP = 200    # overlap between chunks

# In-memory store, built at startup
_chunks: list[dict] = []
_vectorizer: TfidfVectorizer | None = None
_tfidf_matrix = None


def _chunk_text(text: str, source: str) -> list[dict]:
    """Split text into overlapping chunks with metadata."""
    text = re.sub(r"\n{3,}", "\n\n", text.strip())
    chunks = []
    start = 0
    while start < len(text):
        end = start + CHUNK_SIZE
        chunk = text[start:end]
        if chunk.strip():
            chunks.append({
                "text": chunk.strip(),
                "source": source,
                "start": start,
            })
        start += CHUNK_SIZE - CHUNK_OVERLAP
    return chunks


def _read_file(path: Path) -> str | None:
    """Read a document file, returning its text content."""
    suffix = path.suffix.lower()
    if suffix in (".txt", ".md"):
        return path.read_text(encoding="utf-8")
    if suffix == ".pdf":
        try:
            import pymupdf
            doc = pymupdf.open(str(path))
            return "\n\n".join(page.get_text() for page in doc)
        except ImportError:
            return None
    return None


def ingest_documents():
    """Ingest all documents from the documents/ directory into the in-memory store."""
    global _chunks, _vectorizer, _tfidf_matrix

    if not DOCUMENTS_DIR.exists():
        print("RAG: no documents/ directory found, skipping")
        return

    files = [
        f for f in DOCUMENTS_DIR.rglob("*")
        if f.is_file() and f.suffix.lower() in (".txt", ".md", ".pdf")
    ]

    _chunks = []
    for filepath in files:
        text = _read_file(filepath)
        if not text:
            continue
        rel_path = str(filepath.relative_to(DOCUMENTS_DIR))
        _chunks.extend(_chunk_text(text, rel_path))

    if not _chunks:
        print("RAG: no document chunks to index")
        return

    _vectorizer = TfidfVectorizer(stop_words="english", max_features=5000)
    _tfidf_matrix = _vectorizer.fit_transform([c["text"] for c in _chunks])

    print(f"RAG: indexed {len(_chunks)} chunks from {len(files)} documents")


def search_documents(query: str, n_results: int = 5) -> list[dict]:
    """Search the corporate document store. Returns a list of matching chunks."""
    if not _chunks or _vectorizer is None or _tfidf_matrix is None:
        return [{"message": "No documents have been ingested yet."}]

    query_vec = _vectorizer.transform([query])
    scores = cosine_similarity(query_vec, _tfidf_matrix).flatten()

    # Get top N results with non-zero scores
    top_indices = scores.argsort()[::-1][:n_results]

    matches = []
    for idx in top_indices:
        score = float(scores[idx])
        if score > 0:
            matches.append({
                "text": _chunks[idx]["text"],
                "source": _chunks[idx]["source"],
                "relevance": round(score, 3),
            })

    if not matches:
        return [{"message": "No relevant documents found for this query."}]

    return matches
