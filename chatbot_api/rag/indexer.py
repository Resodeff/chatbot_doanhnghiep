"""
Kéo toàn bộ sản phẩm từ Django export endpoint, embed và nạp vào Chroma.

Chiến lược chunking:
  - Mỗi sản phẩm → 1 "document text" đầy đủ (tên + loại + hãng + thông số + giá).
  - Text đó được chunk bằng RecursiveCharacterTextSplitter (chunk_size=500,
    overlap=100) để embedding capture được cả tên ngắn lẫn thông số dài.
  - Mỗi chunk được lưu riêng trong Chroma với id = "{product_id}_{chunk_idx}",
    nhưng metadata vẫn giữ nguyên product_id gốc để retriever có thể
    dedup (nhiều chunk cùng sản phẩm → chỉ trả 1 lần).

Mỗi document trong Chroma:
  id       = "{product_id}_{chunk_idx}"
  document = chunk text
  metadata = {product_id, loai, ten, hang, gia, thong_so, anh_dai_dien}
  embedding = vector từ nomic-embed-text
"""
import httpx
import logging
import config
from rag.embedder import embed_batch, EmbedError
from rag.store import reset_collection

logger = logging.getLogger(__name__)

BATCH_SIZE = 50       # số chunk embed mỗi lần gọi Ollama
CHUNK_SIZE = 500      # ký tự mỗi chunk
CHUNK_OVERLAP = 100   # overlap giữa các chunk liền kề


def _split_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """
    Tự implement RecursiveCharacterTextSplitter đơn giản — không cần langchain,
    tránh thêm dependency. Ưu tiên tách tại dấu '\n', rồi '. ', rồi ' ', rồi ký tự.
    """
    if len(text) <= chunk_size:
        return [text]

    separators = ["\n", ". ", " ", ""]
    chunks: list[str] = []

    def _split(s: str, seps: list[str]) -> list[str]:
        if not seps or len(s) <= chunk_size:
            return [s] if s.strip() else []
        sep = seps[0]
        rest_seps = seps[1:]
        parts = s.split(sep) if sep else list(s)
        result: list[str] = []
        current = ""
        for part in parts:
            piece = (current + sep + part) if current else part
            if len(piece) <= chunk_size:
                current = piece
            else:
                if current:
                    result.append(current)
                if len(part) > chunk_size:
                    result.extend(_split(part, rest_seps))
                    current = ""
                else:
                    current = part
        if current:
            result.append(current)
        return result

    raw_chunks = _split(text, separators)

    # Áp overlap: mỗi chunk mang theo đuôi chunk trước
    result: list[str] = []
    for i, chunk in enumerate(raw_chunks):
        if i == 0 or overlap == 0:
            result.append(chunk)
        else:
            tail = raw_chunks[i - 1][-overlap:]
            result.append(tail + " " + chunk)

    return [c.strip() for c in result if c.strip()]


def _make_full_text(p: dict) -> str:
    """
    Tạo document text ĐẦY ĐỦ cho 1 sản phẩm — càng nhiều thông tin càng tốt
    để embedding capture được nhiều góc truy vấn (tên model, thông số, hãng...).
    """
    lines: list[str] = []

    ten = p.get("ten", "").strip()
    if ten:
        lines.append(f"Tên sản phẩm: {ten}")

    loai = (p.get("loai") or "").strip().upper()
    if loai:
        lines.append(f"Loại: {loai}")

    hang = (p.get("hang") or "").strip()
    if hang:
        lines.append(f"Hãng: {hang}")

    gia = float(p.get("gia_hien_tai") or p.get("gia") or 0)
    if gia:
        gia_str = f"{int(gia):,}".replace(",", ".") + "đ"
        lines.append(f"Giá: {gia_str}")

    thong_so = (p.get("thong_so") or p.get("tom_tat") or "").strip()
    if thong_so:
        lines.append(f"Thông số: {thong_so}")

    mo_ta = (p.get("mo_ta") or "").strip()
    if mo_ta:
        lines.append(f"Mô tả: {mo_ta}")

    return "\n".join(lines)


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


async def reindex() -> tuple[int, int]:
    """Tải lại toàn bộ sản phẩm vào Chroma. Trả (số chunk, số sản phẩm) đã nạp."""
    logger.info("Bắt đầu reindex...")
    products = await fetch_products()
    if not products:
        logger.warning("Django trả danh sách rỗng, hủy reindex.")
        return 0,0

    collection = reset_collection()

    # ── Debug: kiểm tra fields Django trả về ─────────────────────────────────
    if products:
        sample = products[0]
        logger.info("Sample product fields: %s", list(sample.keys()))
        logger.info("Sample product data: loai=%r | ten=%r | gia=%r",
                    sample.get("loai"), sample.get("ten"),
                    sample.get("gia_hien_tai") or sample.get("gia"))

    # ── Chuẩn bị tất cả chunk trước ──────────────────────────────────────────
    all_ids:       list[str]  = []
    all_texts:     list[str]  = []
    all_metadatas: list[dict] = []

    for p in products:
        full_text = _make_full_text(p)
        chunks    = _split_text(full_text)
        pid       = str(p["id"])
        meta_base = {
            "product_id":   pid,
            "loai":         (p.get("loai") or "").upper(),
            "ten":          p.get("ten", ""),
            "hang":         p.get("hang", ""),
            "gia":          float(p.get("gia_hien_tai") or p.get("gia") or 0),
            "thong_so":     p.get("thong_so") or p.get("tom_tat") or "",
            "anh_dai_dien": p.get("anh_dai_dien") or "",
        }
        for idx, chunk in enumerate(chunks):
            all_ids.append(f"{pid}_{idx}")
            all_texts.append(chunk)
            all_metadatas.append({**meta_base, "chunk_idx": idx})

    # Thống kê số sản phẩm theo loại để kiểm tra dữ liệu
    from collections import Counter
    loai_count = Counter(m["loai"] for m in all_metadatas if m.get("chunk_idx", 0) == 0)
    logger.info("Tổng %d sản phẩm → %d chunks.", len(products), len(all_ids))
    logger.info("Phân bố theo loại: %s",
                " | ".join(f"{k}={v}" for k, v in sorted(loai_count.items())))

    # ── Embed và nạp từng batch ───────────────────────────────────────────────
    total = 0
    for i in range(0, len(all_ids), BATCH_SIZE):
        batch_ids   = all_ids[i : i + BATCH_SIZE]
        batch_texts = all_texts[i : i + BATCH_SIZE]
        batch_metas = all_metadatas[i : i + BATCH_SIZE]

        try:
            vectors = await embed_batch(batch_texts)
        except EmbedError as e:
            logger.error("Embed batch %d lỗi: %s", i // BATCH_SIZE, e)
            raise

        collection.add(
            ids=batch_ids,
            embeddings=vectors,
            documents=batch_texts,
            metadatas=batch_metas,
        )
        total += len(batch_ids)
        logger.info("  Đã nạp %d / %d chunks", total, len(all_ids))

    logger.info("Reindex hoàn tất: %d chunks từ %d sản phẩm.", total, len(products))
    return total, len(products)