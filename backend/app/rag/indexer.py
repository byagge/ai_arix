"""Local RAG: file-based TF-IDF + optional Qdrant/Gemini embeddings."""
from __future__ import annotations

import json
import math
import re
import uuid
from collections import Counter
from pathlib import Path

from app.config import DATA_DIR, get_settings

settings = get_settings()
LOCAL_INDEX = DATA_DIR / "rag_index.json"
UPLOAD_DIR = Path("uploads/knowledge")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-zA-Zа-яА-ЯёЁ0-9$]+", text.lower())


def _load_index() -> list[dict]:
    if LOCAL_INDEX.exists():
        return json.loads(LOCAL_INDEX.read_text(encoding="utf-8"))
    return []


def _save_index(chunks: list[dict]) -> None:
    LOCAL_INDEX.write_text(json.dumps(chunks, ensure_ascii=False, indent=2), encoding="utf-8")


def extract_text_from_file(file_path: Path, file_type: str, filename: str = "") -> str:
    ft = (file_type or "").lower().lstrip(".")
    name = filename or file_path.name

    if ft == "pdf":
        from pypdf import PdfReader

        reader = PdfReader(str(file_path))
        return "\n".join(page.extract_text() or "" for page in reader.pages)

    if ft in ("docx", "doc"):
        from docx import Document

        doc = Document(str(file_path))
        return "\n".join(p.text for p in doc.paragraphs)

    if ft in ("png", "jpg", "jpeg", "webp", "gif", "bmp", "heic", "tiff"):
        return (
            f"[Изображение: {name}]\n"
            f"Тип: {ft}. Файл сохранён в базе знаний."
        )

    if ft in ("txt", "md", "csv", "json", "log", "xml", "html", "htm", "py", "js", "ts", "tsx", "jsx"):
        return file_path.read_text(encoding="utf-8", errors="ignore")

    size = file_path.stat().st_size if file_path.exists() else 0
    try:
        text = file_path.read_text(encoding="utf-8", errors="ignore")
        if text.strip():
            return text
    except Exception:
        pass
    return f"[Файл: {name}]\nТип: {ft or 'unknown'} · размер: {size} байт"


def chunk_text(text: str, chunk_size: int = 800, overlap: int = 100) -> list[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end].strip())
        start = end - overlap
    return [c for c in chunks if len(c) > 10]


def save_upload(filename: str, content: bytes) -> tuple[str, str]:
    ext = Path(filename).suffix.lower().lstrip(".")
    safe_name = f"{uuid.uuid4().hex}_{filename}"
    path = UPLOAD_DIR / safe_name
    path.write_bytes(content)
    return str(path), ext


def _tfidf_score(query: str, doc: str) -> float:
    q = Counter(_tokenize(query))
    d = Counter(_tokenize(doc))
    if not q or not d:
        return 0.0
    score = 0.0
    for term, qf in q.items():
        if term in d:
            score += qf * (1 + math.log(1 + d[term]))
    return score


async def index_document(doc_id: int, filename: str, file_path: str, file_type: str) -> int:
    text = extract_text_from_file(Path(file_path), file_type, filename)
    chunks = chunk_text(text)
    if not chunks and text.strip():
        chunks = [text.strip()]
    index = [c for c in _load_index() if c.get("doc_id") != doc_id]
    for i, chunk in enumerate(chunks):
        index.append(
            {
                "id": str(uuid.uuid4()),
                "doc_id": doc_id,
                "filename": filename,
                "chunk_index": i,
                "text": chunk,
            }
        )
    _save_index(index)

    if not settings.use_local_rag and settings.google_api_key:
        try:
            await _index_qdrant(doc_id, filename, chunks)
        except Exception:
            pass
    return len(chunks)


async def _index_qdrant(doc_id: int, filename: str, chunks: list[str]) -> None:
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, PointStruct, VectorParams
    import google.generativeai as genai

    genai.configure(api_key=settings.google_api_key)
    client = QdrantClient(url=settings.qdrant_url)
    names = [c.name for c in client.get_collections().collections]
    if settings.qdrant_collection not in names:
        client.create_collection(
            collection_name=settings.qdrant_collection,
            vectors_config=VectorParams(size=768, distance=Distance.COSINE),
        )
    points = []
    for i, chunk in enumerate(chunks):
        emb = genai.embed_content(
            model=settings.gemini_embedding_model,
            content=chunk,
            task_type="retrieval_document",
        )["embedding"]
        points.append(
            PointStruct(
                id=str(uuid.uuid4()),
                vector=emb,
                payload={"doc_id": doc_id, "filename": filename, "chunk_index": i, "text": chunk},
            )
        )
    if points:
        client.upsert(collection_name=settings.qdrant_collection, points=points)


async def delete_document_vectors(doc_id: int) -> None:
    index = [c for c in _load_index() if c.get("doc_id") != doc_id]
    _save_index(index)


async def retrieve_context(query: str, top_k: int = 5) -> str:
    index = _load_index()
    # Seed with sample price list if empty
    if not index:
        sample = Path(__file__).resolve().parents[1] / "sample_data" / "price_list.txt"
        if not sample.exists():
            sample = Path(__file__).resolve().parents[2] / "sample_data" / "price_list.txt"
        if sample.exists():
            await index_document(0, "price_list.txt", str(sample), "txt")
            index = _load_index()

    scored = sorted(
        (( _tfidf_score(query, c["text"]), c) for c in index),
        key=lambda x: x[0],
        reverse=True,
    )
    top = [c for s, c in scored[:top_k] if s > 0]
    if not top and index:
        top = index[:top_k]
    return "\n\n".join(f"[{c['filename']}] {c['text']}" for c in top)
