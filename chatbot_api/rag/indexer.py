"""
Kéo toàn bộ sản phẩm từ Django export endpoint, embed và nạp vào Chroma.

Mỗi document trong Chroma:
  id       = str(san_pham["id"])
  document = "{ten} • {tom_tat} • {hang}"   (text dùng để embed)
  metadata = {loai, ten, hang, gia (số), thong_so}
  embedding = vector từ bge-m3
"""
import httpx
import logging
import config
from rag.embedder import embed_batch, EmbedError
from rag.store import reset_collection

logger = logging.getLogger(__name__)

BATCH_SIZE = 50   # số sản phẩm embed mỗi lần gọi Ollama


async def fetch_products() -> list[dict]:
    """Gọi Django export endpoint, trả list dict sản phẩm."""
    headers = {"Authorization": f"Token {config.DJANGO_EXPORT_TOKEN}"}
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(config.DJANGO_EXPORT_URL, headers=headers)
    except Exception as e:
        raise RuntimeError(f"Không lấy được dữ liệu từ Django: {e}") from e
    if r.status_code != 200:
        raise RuntimeError(f"Django export lỗi {r.status_code}: {r.text[:200]}")
    return r.json()


def _make_text(p: dict) -> str:
    parts = [p.get("ten", "")]
    if p.get("tom_tat"):
        parts.append(p["tom_tat"])
    if p.get("hang"):
        parts.append(p["hang"])
    return " • ".join(filter(None, parts))


async def reindex() -> int:
    """Tải lại toàn bộ sản phẩm vào Chroma. Trả số document đã nạp."""
    logger.info("Bắt đầu reindex...")
    products = await fetch_products()
    if not products:
        logger.warning("Django trả danh sách rỗng, hủy reindex.")
        return 0

    collection = reset_collection()

    total = 0
    for i in range(0, len(products), BATCH_SIZE):
        batch = products[i : i + BATCH_SIZE]
        texts = [_make_text(p) for p in batch]
        try:
            vectors = await embed_batch(texts)
        except EmbedError as e:
            logger.error("Embed batch %d lỗi: %s", i // BATCH_SIZE, e)
            raise

        ids        = [str(p["id"]) for p in batch]
        metadatas  = [
            {
                "loai":     (p.get("loai") or "").upper(),
                "ten":      p.get("ten", ""),
                "hang":     p.get("hang", ""),
                "gia":      float(p.get("gia_hien_tai") or p.get("gia") or 0),
                "thong_so": p.get("thong_so") or p.get("tom_tat") or "",
                "anh_dai_dien": p.get("anh_dai_dien") or "",
            }
            for p in batch
        ]
        collection.add(
            ids=ids,
            embeddings=vectors,
            documents=texts,
            metadatas=metadatas,
        )
        total += len(batch)
        logger.info("  Đã nạp %d / %d sản phẩm", total, len(products))

    logger.info("Reindex hoàn tất: %d documents.", total)
    return total