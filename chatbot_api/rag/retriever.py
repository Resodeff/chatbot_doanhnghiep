"""
Truy xuất sản phẩm liên quan theo câu hỏi của khách.

Chiến lược lai:
  1. Tách loại (CPU / GPU / RAM / SSD / ...) và khoảng ngân sách bằng luật/regex.
  2. Lọc metadata Chroma theo loại + ngân sách.
  3. Xếp hạng bằng vector similarity + MMR để đa dạng kết quả.
  4. Nếu không tìm thấy gì → trả danh sách rỗng.
"""
import re
import math
import logging
from rag.embedder import embed
from rag.store import get_collection
import config

logger = logging.getLogger(__name__)

# ─── Từ điển loại linh kiện ──────────────────────────────────────────────────
LOAI_MAP: dict[str, str] = {
    # GPU
    "gpu": "GPU", "card": "GPU", "vga": "GPU", "đồ họa": "GPU",
    "do hoa": "GPU", "rtx": "GPU", "gtx": "GPU", "radeon": "GPU",
    "rx ": "GPU",
    # CPU
    "cpu": "CPU", "vi xử lý": "CPU", "vi xu ly": "CPU",
    "bộ xử lý": "CPU", "bo xu ly": "CPU", "chip": "CPU",
    "core i": "CPU", "ryzen": "CPU", "intel": "CPU", "amd": "CPU",
    # RAM
    "ram": "RAM", "bộ nhớ": "RAM", "bo nho": "RAM",
    # SSD / HDD
    "ssd": "SSD", "nvme": "SSD", "m.2": "SSD",
    "hdd": "HDD", "ổ cứng": "HDD", "o cung": "HDD",
    "ổ đĩa": "HDD", "o dia": "HDD",
    # Mainboard
    "mainboard": "MB", "main": "MB", "bo mạch": "MB",
    "bo mach": "MB", "motherboard": "MB",
    # PSU
    "psu": "PSU", "nguồn": "PSU", "nguon": "PSU",
    "power supply": "PSU",
    # Case
    "case": "CASE", "vỏ máy": "CASE", "vo may": "CASE",
    "thùng máy": "CASE", "thung may": "CASE",
    # Tản nhiệt
    "tản nhiệt": "TN", "tan nhiet": "TN", "cooler": "TN", "aio": "TN",
    # Màn hình
    "màn hình": "MH", "man hinh": "MH", "monitor": "MH",
}

# ─── Helpers số học ──────────────────────────────────────────────────────────
_TRIEU = 1_000_000
_NGAN  = 1_000

def _parse_so(text: str) -> float | None:
    """
    Chuyển chuỗi dạng '10 triệu', '500k', '1.5 triệu', '1500000' → float.
    Trả None nếu không nhận ra.
    """
    text = text.strip().lower()
    text = re.sub(r"[,_]", "", text)
    # 'x triệu' hoặc 'x tr'
    m = re.match(r"(\d+(?:\.\d+)?)\s*(?:triệu|trieu|tr\b)", text)
    if m:
        return float(m.group(1)) * _TRIEU
    # 'xk' hoặc 'x nghìn'
    m = re.match(r"(\d+(?:\.\d+)?)\s*(?:k\b|nghìn|nghin|nghìn đồng)", text)
    if m:
        return float(m.group(1)) * _NGAN
    # số thuần
    m = re.match(r"(\d+(?:\.\d+)?)$", text)
    if m:
        return float(m.group(1))
    return None


# ─── Tách điều kiện từ câu hỏi ──────────────────────────────────────────────

def extract_loai(text: str) -> str | None:
    lower = text.lower()
    for kw, loai in LOAI_MAP.items():
        if kw in lower:
            return loai
    return None


def extract_budget(text: str) -> tuple[float | None, float | None]:
    """
    Trả (min_gia, max_gia). None nghĩa là không giới hạn.
    Hiểu được: 'dưới 10 triệu', 'trên 5 triệu', '5-7 triệu', 'khoảng 8 triệu',
                'tầm 10tr', 'từ 5 đến 8 triệu', '15 triệu'.
    """
    text_l = text.lower()

    # 'từ X đến Y' hoặc 'X - Y triệu'
    m = re.search(
        r"(?:từ|tu)\s*([\d.,]+\s*(?:triệu|trieu|tr|k|nghìn|nghin)?)\s*(?:đến|den|tới|toi|-)\s*([\d.,]+\s*(?:triệu|trieu|tr|k|nghìn|nghin)?)",
        text_l,
    )
    if m:
        lo = _parse_so(m.group(1))
        hi = _parse_so(m.group(2))
        return lo, hi

    # 'X - Y' không có từ 'từ'
    m = re.search(
        r"([\d.,]+\s*(?:triệu|trieu|tr))\s*[-–]\s*([\d.,]+\s*(?:triệu|trieu|tr))",
        text_l,
    )
    if m:
        lo = _parse_so(m.group(1))
        hi = _parse_so(m.group(2))
        return lo, hi

    # 'dưới / không quá / tối đa / tầm / khoảng / dưới X'
    m = re.search(
        r"(?:dưới|duoi|không quá|khong qua|tối đa|toi da|max)\s*([\d.,]+\s*(?:triệu|trieu|tr|k|nghìn|nghin|đồng|dong)?)",
        text_l,
    )
    if m:
        return None, _parse_so(m.group(1))

    # 'trên / tối thiểu / từ X'
    m = re.search(
        r"(?:trên|tren|tối thiểu|toi thieu|từ|tu|ít nhất|it nhat)\s*([\d.,]+\s*(?:triệu|trieu|tr|k|nghìn|nghin|đồng|dong)?)",
        text_l,
    )
    if m:
        return _parse_so(m.group(1)), None

    # 'tầm / khoảng / ngân sách X' → ± 20%
    m = re.search(
        r"(?:tầm|tam|khoảng|khoang|ngân sách|ngan sach|budget)\s*([\d.,]+\s*(?:triệu|trieu|tr|k|nghìn|nghin)?)",
        text_l,
    )
    if m:
        center = _parse_so(m.group(1))
        if center:
            return center * 0.8, center * 1.2

    return None, None


def _build_where(loai: str | None, min_gia: float | None, max_gia: float | None) -> dict | None:
    conditions = []
    if loai:
        conditions.append({"loai": {"$eq": loai}})
    if min_gia is not None:
        conditions.append({"gia": {"$gte": min_gia}})
    if max_gia is not None:
        conditions.append({"gia": {"$lte": max_gia}})

    if not conditions:
        return None
    if len(conditions) == 1:
        return conditions[0]
    return {"$and": conditions}


# ─── MMR (Maximal Marginal Relevance) ───────────────────────────────────────

def _cosine_sim(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na  = math.sqrt(sum(x * x for x in a))
    nb  = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb + 1e-9)


def _mmr(
    query_vec: list[float],
    candidates: list[dict],   # [{id, embedding, metadata, document}]
    k: int,
    lambda_: float = 0.5,
) -> list[dict]:
    """
    Chọn k document bằng MMR để vừa liên quan vừa đa dạng.
    lambda_=1 → chỉ theo sim(query), lambda_=0 → chỉ đa dạng.
    """
    if not candidates:
        return []
    selected: list[dict] = []
    remaining = list(candidates)

    while len(selected) < k and remaining:
        best, best_score = None, -1e9
        for cand in remaining:
            rel = _cosine_sim(query_vec, cand["embedding"])
            red = max(
                (_cosine_sim(cand["embedding"], s["embedding"]) for s in selected),
                default=0.0,
            )
            score = lambda_ * rel - (1 - lambda_) * red
            if score > best_score:
                best_score = score
                best = cand
        selected.append(best)
        remaining.remove(best)

    return selected


# ─── API công khai ───────────────────────────────────────────────────────────

async def retrieve(
    message: str,
    history: list[dict] | None = None,
    top_k: int | None = None,
    fetch_k: int | None = None,
) -> list[dict]:
    """
    Trả list dict sản phẩm (ten, gia, thong_so) phù hợp với câu hỏi.
    Trả [] nếu không tìm thấy gì trong Chroma.
    """
    top_k   = top_k   or config.RAG_TOP_K
    fetch_k = fetch_k or config.RAG_FETCH_K

    # 1. Tách điều kiện
    loai = extract_loai(message)

    # Nếu câu hỏi không nói rõ loại, thử lấy từ lịch sử
    if loai is None and history:
        for turn in reversed(history):
            loai = extract_loai(turn.get("content", ""))
            if loai:
                break

    min_gia, max_gia = extract_budget(message)

    logger.info("RAG query | loai=%s min_gia=%s max_gia=%s | '%s'",
                loai, min_gia, max_gia, message[:80])

    # 2. Embed câu hỏi
    query_vec = await embed(message)

    # 3. Truy vấn Chroma
    collection = get_collection()
    n_docs = collection.count()
    if n_docs == 0:
        logger.warning("Chroma collection rỗng. Hãy gọi /reindex trước.")
        return []

    where = _build_where(loai, min_gia, max_gia)
    actual_fetch = min(fetch_k, n_docs)

    try:
        result = collection.query(
            query_embeddings=[query_vec],
            n_results=actual_fetch,
            where=where,
            include=["embeddings", "metadatas", "documents"],
        )
    except Exception as e:
        # Chroma có thể raise nếu where lọc ra 0 kết quả trên một số phiên bản
        logger.warning("Chroma query lỗi (có thể không có sản phẩm phù hợp): %s", e)
        return []

    ids        = result["ids"][0]
    embeddings = result["embeddings"][0]
    metadatas  = result["metadatas"][0]

    if not ids:
        return []

    candidates = [
        {"id": id_, "embedding": emb, "metadata": meta}
        for id_, emb, meta in zip(ids, embeddings, metadatas)
    ]

    # 4. MMR
    chosen = _mmr(query_vec, candidates, k=top_k)

    # 5. Chuyển sang định dạng Product cho build_messages()
    products = [
        {
            "ten":      c["metadata"]["ten"],
            "gia":      c["metadata"]["gia"],
            "thong_so": c["metadata"]["thong_so"],
            "anh_dai_dien": c["metadata"].get("anh_dai_dien", ""),
        }
        for c in chosen
    ]
    logger.info("RAG trả %d sản phẩm.", len(products))
    return products