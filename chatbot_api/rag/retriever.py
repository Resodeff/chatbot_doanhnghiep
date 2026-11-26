import re
import math
import logging
from rag.embedder import embed
from rag.store import get_collection
import config

logger = logging.getLogger(__name__)

LOAI_MAP: dict[str, str] = {
    "gpu": "GPU", "card": "GPU", "vga": "GPU", "đồ họa": "GPU",
    "do hoa": "GPU", "rtx": "GPU", "gtx": "GPU", "radeon": "GPU",
    "rx ": "GPU",
    "cpu": "CPU", "vi xử lý": "CPU", "vi xu ly": "CPU",
    "bộ xử lý": "CPU", "bo xu ly": "CPU", "chip": "CPU",
    "core i": "CPU", "ryzen": "CPU", "intel": "CPU", "amd": "CPU",
    "ram": "RAM", "bộ nhớ": "RAM", "bo nho": "RAM",
    "ssd": "SSD", "nvme": "SSD", "m.2": "SSD",
    "hdd": "HDD", "ổ cứng": "HDD", "o cung": "HDD",
    "ổ đĩa": "HDD", "o dia": "HDD",
    "mainboard": "MAIN", "main": "MAIN", "bo mạch": "MAIN",
    "bo mach": "MAIN", "motherboard": "MAIN",
    "psu": "PSU", "nguồn": "PSU", "nguon": "PSU",
    "power supply": "PSU",
    "case": "CASE", "vỏ máy": "CASE", "vo may": "CASE",
    "thùng máy": "CASE", "thung may": "CASE",
    "tản nhiệt": "COOLER", "tan nhiet": "COOLER", "cooler": "COOLER",
    "aio": "COOLER", "quạt": "COOLER",
}

FULL_BUILD_KEYWORDS = [
    "full bộ", "full bo", "cả bộ", "ca bo", "nguyên bộ",
    "nguyen bo", "toàn bộ", "toan bo", "build pc", "build máy",
    "lắp máy", "lap may", "máy tính", "may tinh",
    "một bộ", "mot bo", "bộ máy", "bo may",
    "build một", "xây dựng", "tư vấn build", "tu van build",
    "cấu hình", "cau hinh",
]

FULL_BUILD_LOAI = ["CPU", "MAIN", "RAM", "GPU", "SSD", "PSU", "COOLER", "CASE"]

_DESKTOP_EXCLUDE: dict[str, list[str]] = {
    "RAM":    ["laptop", "so-dimm", "sodimm"],
    "SSD":    ["usb", "di động", "di dong", "portable", "gắn ngoài"],
    "COOLER": ["quạt ", "quat ", "fan "],
}

BUDGET_PROFILES: dict[str, dict[str, float]] = {
    "gaming": {
        "GPU":    0.40, "CPU":  0.20, "MAIN": 0.11,
        "RAM":    0.08, "SSD": 0.07,  "PSU":  0.07,
        "COOLER": 0.035,"CASE": 0.035,
    },
    "render": {
        "GPU":    0.34, "CPU":  0.25, "MAIN": 0.12,
        "RAM":    0.12, "SSD": 0.07,  "PSU":  0.05,
        "COOLER": 0.025,"CASE": 0.025,
    },
    "office": {
        "GPU":    0.00, "CPU":  0.32, "MAIN": 0.22,
        "RAM":    0.16, "SSD": 0.13,  "PSU":  0.09,
        "COOLER": 0.02, "CASE": 0.06,
    },
}

_PROFILE_KEYWORDS: dict[str, list[str]] = {
    "gaming": [
        "gaming", "game", "chơi game", "choi game", "fps",
        "chiến game", "chien game", "esport", "stream",
        "chơi", "choi",
    ],
    "render": [
        "render", "đồ họa", "do hoa", "ai", "local ai", "machine learning",
        "deep learning", "blender", "premiere", "after effect",
        "3d", "workstation", "đồ hoạ",
    ],
    "office": [
        "văn phòng", "van phong", "office", "làm việc", "lam viec",
        "học", "hoc", "không gpu", "khong gpu", "igpu",
        "tản zin", "tan zin", "không card", "khong card",
    ],
}


def detect_build_profile(text: str) -> str:
    lower = text.lower()
    for profile, keywords in _PROFILE_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            return profile
    return "gaming"


_TRIEU = 1_000_000
_NGAN  = 1_000


def _parse_so(text: str, default_trieu: bool = False) -> float | None:
    text = text.strip().lower()
    text = re.sub(r"[,_]", "", text)
    m = re.match(r"(\d+(?:\.\d+)?)\s*(?:triệu|trieu|tr\b|củ|cu\b)", text)
    if m:
        return float(m.group(1)) * _TRIEU
    m = re.match(r"(\d+(?:\.\d+)?)\s*(?:k\b|nghìn|nghin|nghìn đồng)", text)
    if m:
        return float(m.group(1)) * _NGAN
    m = re.match(r"(\d+(?:\.\d+)?)$", text)
    if m:
        val = float(m.group(1))
        if default_trieu and 1 <= val <= 500:
            return val * _TRIEU
        return val
    return None


def extract_loai(text: str) -> str | None:
    lower = text.lower()
    for kw, loai in LOAI_MAP.items():
        if kw in lower:
            return loai
    return None


def is_full_build(text: str) -> bool:
    lower = text.lower()
    return any(kw in lower for kw in FULL_BUILD_KEYWORDS)


def extract_budget(text: str) -> tuple[float | None, float | None]:
    text_l = text.lower()
    unit_pat = r"(?:triệu|trieu|tr|củ|cu|k|nghìn|nghin|đồng|dong)"

    m = re.search(
        rf"(?:từ|tu)\s*([\d.,]+\s*{unit_pat}?)\s*(?:đến|den|tới|toi|-|–)\s*([\d.,]+\s*{unit_pat}?)",
        text_l,
    )
    if m:
        return _parse_so(m.group(1), default_trieu=True), _parse_so(m.group(2), default_trieu=True)

    m = re.search(
        rf"([\d.,]+\s*{unit_pat})\s*[-–]\s*([\d.,]+\s*{unit_pat})",
        text_l,
    )
    if m:
        return _parse_so(m.group(1), default_trieu=True), _parse_so(m.group(2), default_trieu=True)

    m = re.search(
        rf"(?:dưới|duoi|không quá|khong qua|tối đa|toi da|max)\s*([\d.,]+\s*{unit_pat}?)",
        text_l,
    )
    if m:
        return None, _parse_so(m.group(1), default_trieu=True)

    m = re.search(
        rf"([\d.,]+\s*{unit_pat}?)\s*(?:đổ lại|do lai|trở xuống|tro xuong|quay đầu|quay dau)",
        text_l,
    )
    if m:
        return None, _parse_so(m.group(1), default_trieu=True)

    m = re.search(
        rf"(?:trên|tren|tối thiểu|toi thieu|ít nhất|it nhat)\s*([\d.,]+\s*{unit_pat}?)",
        text_l,
    )
    if m:
        return _parse_so(m.group(1), default_trieu=True), None

    m = re.search(
        rf"(?:tầm|tam|khoảng|khoang|ngân sách|ngan sach|budget)(?:\s+giá|\s+gia)?\s*([\d.,]+\s*{unit_pat}?)",
        text_l,
    )
    if m:
        center = _parse_so(m.group(1), default_trieu=True)
        if center:
            return center * 0.8, center

    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:triệu|trieu|tr\b|củ|cu\b)", text_l)
    if m:
        return None, _parse_so(m.group(1), default_trieu=True)

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


def _filter_desktop_candidates(loai: str, candidates: list[dict]) -> list[dict]:
    bad_kws = _DESKTOP_EXCLUDE.get(loai)
    if not bad_kws or not candidates:
        return candidates
    filtered = [
        c for c in candidates
        if not any(
            kw in (c["metadata"].get("ten", "") + " " + c["metadata"].get("thong_so", "")).lower()
            for kw in bad_kws
        )
    ]
    return filtered or candidates


def _cosine_sim(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na  = math.sqrt(sum(x * x for x in a))
    nb  = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb + 1e-9)


def _mmr(
    query_vec: list[float],
    candidates: list[dict],
    k: int,
    lambda_: float = 0.5,
) -> list[dict]:
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


def _query_chroma(collection, query_vec, where, fetch_k) -> list[dict]:
    n_docs = collection.count()
    if n_docs == 0:
        return []
    actual_fetch = min(fetch_k, n_docs)
    try:
        result = collection.query(
            query_embeddings=[query_vec],
            n_results=actual_fetch,
            where=where,
            include=["embeddings", "metadatas", "documents"],
        )
    except Exception as e:
        logger.warning("Chroma query lỗi: %s", e)
        return []
    ids        = result["ids"][0]
    embeddings = result["embeddings"][0]
    metadatas  = result["metadatas"][0]
    if not ids:
        return []
    return [
        {"id": id_, "embedding": emb, "metadata": meta}
        for id_, emb, meta in zip(ids, embeddings, metadatas)
    ]


def _to_product(c: dict) -> dict:
    return {
        "product_id": c["metadata"].get("product_id", c["id"]),
        "loai":       c["metadata"].get("loai", "KHÁC"),
        "ten":        c["metadata"]["ten"],
        "gia":        c["metadata"]["gia"],
        "thong_so":   c["metadata"]["thong_so"],
        "anh":        c["metadata"].get("anh_dai_dien", ""),
    }


def _dedup_products(products: list[dict]) -> list[dict]:
    seen: set[str] = set()
    result: list[dict] = []
    for p in products:
        pid = p.get("product_id") or p.get("ten", "")
        if pid not in seen:
            seen.add(pid)
            result.append(p)
    return result


async def retrieve(
    message: str,
    history: list[dict] | None = None,
    top_k: int | None = None,
    fetch_k: int | None = None,
) -> list[dict]:
    top_k   = top_k   or config.RAG_TOP_K
    fetch_k = fetch_k or config.RAG_FETCH_K

    collection = get_collection()
    if collection.count() == 0:
        logger.warning("Chroma collection rỗng. Hãy gọi /reindex trước.")
        return []

    context_parts: list[str] = []
    if history:
        for turn in (history or [])[-4:]:
            c = turn.get("content", "").strip()
            if c:
                context_parts.append(c)
    context_parts.append(message)
    query_text = " ".join(context_parts)

    query_vec = await embed(query_text)

    user_texts: list[str] = []
    if history:
        for turn in history[-4:]:
            if turn.get("role") == "user":
                c = turn.get("content", "").strip()
                if c:
                    user_texts.append(c)
    user_texts.append(message)

    min_gia, max_gia = None, None
    for text in reversed(user_texts):
        lo, hi = extract_budget(text)
        if lo is not None or hi is not None:
            min_gia, max_gia = lo, hi
            break

    if is_full_build(message):
        full_context = " ".join(context_parts)
        profile = detect_build_profile(full_context)
        budget_ratio = BUDGET_PROFILES[profile]

        logger.info("RAG full build | profile=%s | max_gia=%s", profile, max_gia)

        FULL_BUILD_K     = 4
        FULL_BUILD_FETCH = 40

        products = []
        for loai in FULL_BUILD_LOAI:
            ratio = budget_ratio.get(loai, 0.0)

            if ratio == 0.0:
                logger.info("  Loại %s: bỏ qua (profile=%s)", loai, profile)
                continue

            loai_min = (max_gia * ratio * 0.70) if max_gia is not None else None
            loai_max = (max_gia * ratio * 1.05) if max_gia is not None else None

            where = _build_where(loai, loai_min, loai_max)
            candidates = _query_chroma(collection, query_vec, where, fetch_k=FULL_BUILD_FETCH)

            if len(candidates) < 2 and loai_max is not None:
                where_max_only = _build_where(loai, None, loai_max)
                candidates = _query_chroma(collection, query_vec, where_max_only, fetch_k=FULL_BUILD_FETCH)

            if not candidates and loai_max is not None:
                where_no_budget = _build_where(loai, None, None)
                candidates = _query_chroma(collection, query_vec, where_no_budget, fetch_k=FULL_BUILD_FETCH)

            candidates = _filter_desktop_candidates(loai, candidates)

            chosen = _mmr(query_vec, candidates, k=FULL_BUILD_K, lambda_=0.75)
            products.extend(_to_product(c) for c in chosen)
            logger.info("  Loại %s: %d sản phẩm | ratio=%.0f%% | range=[%s - %s]",
                        loai, len(chosen), ratio * 100,
                        f"{loai_min:.0f}" if loai_min else "None",
                        f"{loai_max:.0f}" if loai_max else "None")

        products = _dedup_products(products)
        logger.info("RAG full build trả %d sản phẩm (profile=%s).", len(products), profile)
        return products

    loai = extract_loai(message)
    if loai is None:
        for text in reversed(context_parts[:-1]):
            loai = extract_loai(text)
            if loai:
                break

    logger.info("RAG query | loai=%s min_gia=%s max_gia=%s | query='%s'",
                loai, min_gia, max_gia, query_text[:120])

    where = _build_where(loai, min_gia, max_gia)
    candidates = _query_chroma(collection, query_vec, where, fetch_k)
    chosen = _mmr(query_vec, candidates, k=top_k)

    products = _dedup_products([_to_product(c) for c in chosen])
    logger.info("RAG trả %d sản phẩm.", len(products))
    return products