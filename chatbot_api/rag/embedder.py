"""Gọi Ollama /api/embed để lấy vector cho một đoạn text."""
import httpx
import config

class EmbedError(Exception):
    pass

async def embed(text: str) -> list[float]:
    """Trả về vector embedding cho `text` dùng model nomic."""
    payload = {"model": config.EMBED_MODEL, "input": text}
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(f"{config.OLLAMA_URL}/api/embed", json=payload)
    except httpx.ConnectError:
        raise EmbedError("Không kết nối được Ollama khi embed.")
    except httpx.TimeoutException:
        raise EmbedError("Ollama embed timeout.")
    if r.status_code != 200:
        raise EmbedError(f"Ollama embed lỗi {r.status_code}: {r.text[:200]}")
    data = r.json()
    # Ollama /api/embed trả {"embeddings": [[...]]} (list of list)
    embeddings = data.get("embeddings") or data.get("embedding")
    if not embeddings:
        raise EmbedError(f"Ollama không trả embedding: {data}")
    # Nếu là list of list thì lấy phần tử đầu
    if isinstance(embeddings[0], list):
        return embeddings[0]
    return embeddings

async def embed_batch(texts: list[str]) -> list[list[float]]:
    """Embed nhiều text cùng lúc (một request)."""
    payload = {"model": config.EMBED_MODEL, "input": texts}
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post(f"{config.OLLAMA_URL}/api/embed", json=payload)
    except httpx.ConnectError:
        raise EmbedError("Không kết nối được Ollama khi embed batch.")
    except httpx.TimeoutException:
        raise EmbedError("Ollama embed batch timeout.")
    if r.status_code != 200:
        raise EmbedError(f"Ollama embed batch lỗi {r.status_code}: {r.text[:200]}")
    data = r.json()
    embeddings = data.get("embeddings")
    if not embeddings:
        raise EmbedError(f"Ollama không trả embeddings batch: {data}")
    return embeddings