from app.rag.indexer import retrieve_context as _retrieve

async def retrieve_context(query: str, top_k: int = 5) -> str:
    try:
        return await _retrieve(query, top_k=top_k)
    except Exception:
        return ""
