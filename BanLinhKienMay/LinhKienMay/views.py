from email import message
import json
import logging
import re
import urllib.error
import urllib.request

from django.conf import settings
from django.core.paginator import Paginator
from django.db.models import Q, Func, F, FloatField
from django.db.models.expressions import ExpressionWrapper
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST, require_GET
from .models import LinhKien

SELECT = ("cpu", "main", "ram", "ssd", "hdd", "gpu", "psu", "cooler", "case")


def home(request):
    loai = request.GET.get("loai", "")
    q = request.GET.get("q", "").strip()
    sort = request.GET.get("sort", "gia")

    qs = LinhKien.objects.select_related(*SELECT)
    if loai in dict(LinhKien.LOAI):
        qs = qs.filter(loai=loai)
    if q:
        qs = qs.filter(Q(ten__icontains=q) | Q(hang__icontains=q))
    qs = qs.order_by("-gia_hien_tai" if sort == "-gia" else "gia_hien_tai")

    page = Paginator(qs, 24).get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)
    return render(request, "LinhKienMay/home.html", {
        "page": page, "loai_list": LinhKien.LOAI, "loai": loai, "q": q,
        "sort": sort, "qs_str": params.urlencode(),
    })


KEYWORDS = {
    "CPU":    ["cpu", "vi xử lý", "intel", "ryzen", "i5", "i7", "i9"],
    "MAIN":   ["mainboard", "main", "bo mạch"],
    "RAM":    ["ram", "bộ nhớ"],
    "SSD":    ["ssd", "nvme", "m.2"],
    "HDD":    ["hdd", "ổ cứng cơ", "ổ cơ"],
    "GPU":    ["gpu", "vga", "card đồ họa", "card màn hình", "rtx", "gtx", "radeon"],
    "PSU":    ["nguồn", "psu"],
    "COOLER": ["tản nhiệt", "tản", "cooler", "aio", "quạt"],
    "CASE":   ["case", "vỏ"],
}

FULL_BUILD_KEYWORDS = ["full bộ", "full bo", "cả bộ", "nguyên bộ", "toàn bộ", "build pc", "build máy"]

# Tỷ lệ phân bổ ngân sách chuẩn cho PC Gaming
GAMING_BUILD_RATIOS = {
    "GPU":    0.38,
    "CPU":    0.20,
    "MAIN":   0.11,
    "RAM":    0.08,
    "SSD":    0.08,
    "PSU":    0.07,
    "CASE":   0.04,
    "COOLER": 0.04,
}

RENDER_BUILD_RATIOS = {
    "GPU":    0.35, 
    "CPU":  0.22, 
    "MAIN": 0.11,
    "RAM":    0.12, 
    "SSD": 0.08,  
    "PSU":  0.06,
    "COOLER": 0.03,
    "CASE": 0.03,
}

OFFICE_BUILD_RATIOS = {
    "GPU":    0.00, 
    "CPU":  0.30, 
    "MAIN": 0.22,
    "RAM":    0.16, 
    "SSD": 0.14,  
    "PSU":  0.08,
    "COOLER": 0.03, 
    "CASE": 0.07,
}

log = logging.getLogger(__name__)


def detect_loai(msg):
    """Chọn loại có từ khóa khớp dài nhất."""
    best, best_len = None, 0
    for code, kws in KEYWORDS.items():
        for k in kws:
            if k in msg and len(k) > best_len:
                best, best_len = code, len(k)
    return best


def is_full_build(msg_lower):
    return any(k in msg_lower for k in FULL_BUILD_KEYWORDS)


def extract_budget(msg_lower):
    """Trích xuất ngân sách từ câu hỏi. VD: '50 triệu' -> 50_000_000."""
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(triệu|tr|m)\b", msg_lower)
    if m:
        return float(m.group(1).replace(",", ".")) * 1_000_000
    return None


def search_full_build(budget):
    """
    Với mỗi danh mục linh kiện, lấy 2 sản phẩm có giá gần target nhất.
    3 tầng fallback đảm bảo luôn có đủ 8 danh mục trong kết quả.
    """
    items = []
    for code, ratio in GAMING_BUILD_RATIOS.items():
        qs = LinhKien.objects.filter(loai=code)
        if budget:
            target = budget * ratio

            # Tầng 1: lọc chặt [65%, 115%] target
            candidates = list(qs.filter(
                gia_hien_tai__gte=target * 0.65,
                gia_hien_tai__lte=target * 1.15,
            ).order_by("gia_hien_tai")[:10])

            # Tầng 2: nới rộng [30%, 150%] nếu tầng 1 rỗng
            if not candidates:
                candidates = list(qs.filter(
                    gia_hien_tai__gte=target * 0.30,
                    gia_hien_tai__lte=target * 1.50,
                ).order_by("gia_hien_tai")[:10])

            # Tầng 3: lấy sản phẩm gần nhất trong toàn bộ danh mục (không lọc giá)
            if not candidates:
                candidates = list(qs.order_by("gia_hien_tai")[:5])

            candidates.sort(key=lambda p: abs(float(p.gia_hien_tai) - target))
            picked = candidates[:2]
        else:
            # Không có ngân sách: lấy sản phẩm tầm trung
            all_items = list(qs.order_by("gia_hien_tai"))
            mid = len(all_items) // 2
            picked = all_items[max(0, mid - 1): mid + 1]

        log.debug("full_build | %s | picked=%d", code, len(picked))
        items += picked
    return items  # tối đa 16 sản phẩm (2 mỗi loại × 8 loại)


def search_products(msg_lower, limit=6):
    """Điều phối tìm kiếm: full build -> search_full_build(), còn lại -> query thông thường."""
    if is_full_build(msg_lower):
        budget = extract_budget(msg_lower)
        return search_full_build(budget)

    # Truy vấn thông thường theo loại + ngân sách
    loai = detect_loai(msg_lower)
    qs = LinhKien.objects.select_related(*SELECT)
    if loai:
        qs = qs.filter(loai=loai)
    elif "ổ cứng" in msg_lower:
        qs = qs.filter(loai__in=["SSD", "HDD"])
        loai = "STORAGE"

    budget = extract_budget(msg_lower)
    if budget:
        qs = qs.filter(gia_hien_tai__lte=budget)

    if not loai and not budget:
        return []  # chưa đủ thông tin: để chatbot hỏi lại

    items = list(qs.order_by("-gia_hien_tai" if budget else "gia_hien_tai")[:200])
    if not budget and len(items) > limit:
        step = len(items) / limit
        items = [items[int(i * step)] for i in range(limit)]
    return items[:limit]


def to_payload(items, request=None):
    """Chuyển queryset thành list dict gửi lên chatbot API."""
    result = []
    for p in items:
        anh_url = ""
        if p.anh_dai_dien:
            anh_url = (
                request.build_absolute_uri(p.anh_dai_dien)
                if request else p.anh_dai_dien
            )
        result.append({
            "loai":     p.loai,
            "ten":      p.ten[:120],
            "gia":      float(p.gia_hien_tai),
            "thong_so": p.tom_tat,
            "anh":      anh_url,
        })
    return result


def rule_reply(items):
    """Dự phòng khi chatbot AI (FastAPI/Ollama) không chạy."""
    if not items:
        return (
            "Bạn cần tư vấn linh kiện nào (CPU, mainboard, RAM, SSD, HDD, GPU, "
            "nguồn, tản nhiệt, case) và ngân sách bao nhiêu? "
            "Ví dụ: \u201ccard đồ họa dưới 10 triệu\u201d."
        )
    lines = []
    for p in items[:3]:
        gia = f"{int(p.gia_hien_tai):,}".replace(",", ".")
        t = p.tom_tat
        lines.append(f"• {p.ten[:70]} — {gia}đ" + (f"\n   {t}" if t else ""))
    return "Mình gợi ý cho bạn:\n" + "\n".join(lines)


def call_chatbot_api(message, session_id="default"):
    """Gửi message + session_id sang FastAPI. History do FastAPI tự quản lý."""
    url = settings.CHATBOT_API_URL.rstrip("/") + "/chat"
    body = json.dumps({"message": message, "session_id": session_id}).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=settings.CHATBOT_TIMEOUT) as r:
        return json.loads(r.read())


def inject_images(reply: str, items) -> str:
    """
    Chỉ ghép ảnh của sản phẩm nào thực sự được nhắc tên trong reply.
    Tránh gắn nhầm ảnh sản phẩm không liên quan (VD: GT 730 khi hỏi RTX 3060).
    """
    if not items:
        return reply

    reply_lower = reply.lower()
    lines = []
    seen = set()

    for p in items:
        if not p.anh_dai_dien or p.ten in seen:
            continue
        # Khớp tên rút gọn: lấy 3 từ đầu để tránh miss do tên dài
        name_lower = p.ten.lower()
        name_short = " ".join(name_lower.split()[:3])
        if name_lower in reply_lower or name_short in reply_lower:
            lines.append(f"![{p.ten}]({p.anh_dai_dien})")
            seen.add(p.ten)

    if lines:
        reply = reply.rstrip() + "\n\n" + "\n".join(lines)
    return reply

def inject_images_from_products(reply: str, products) -> str:
    """Chỉ ghép ảnh của sản phẩm được nhắc tên trong reply."""
    reply_lower = reply.lower()
    lines, seen = [], set()
    for p in products or []:
        pid = str(p.get("product_id", ""))
        anh, ten = p.get("anh", ""), p.get("ten", "")
        if not anh or pid in seen:
            continue
        name_lower = ten.lower()
        name_short = " ".join(name_lower.split()[:3])
        if name_lower in reply_lower or name_short in reply_lower:
            seen.add(pid)
            lines.append(f"![{ten}]({anh})")
    if lines:
        reply = reply.rstrip() + "\n\n" + "\n".join(lines)
    return reply

@require_POST
def chat_api(request):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"reply": "Tin nhắn không hợp lệ."}, status=400)

    message = str(data.get("message", "")).strip()[:1000]
    if not message:
        return JsonResponse({"reply": "Bạn hãy nhập câu hỏi nhé."}, status=400)

    history = [
        {"role": h["role"], "content": str(h["content"])[:1000]}
        for h in (data.get("history") or [])[-12:]
        if isinstance(h, dict)
        and h.get("role") in ("user", "assistant")
        and h.get("content")
    ]

    # session_id: dùng Django session key để phân biệt từng khách
    session_id = request.session.session_key or "default"
    if not request.session.session_key:
        request.session.create()
        session_id = request.session.session_key

    # RAG và history do FastAPI quản lý — ảnh lấy từ products trong response
    try:
        resp = call_chatbot_api(message, session_id)
        reply = inject_images_from_products(resp["reply"], resp.get("products", []))
    except (urllib.error.URLError, TimeoutError, KeyError, ValueError) as e:
        log.warning("Chatbot API lỗi, dùng câu trả lời dự phòng: %s", e)
        items = search_products(message.lower())  # chỉ dùng cho câu trả lời dự phòng
        reply = rule_reply(items)

    return JsonResponse({"reply": reply})


@require_GET
def export_linhkien(request):
    expected = f"Token {settings.EXPORT_TOKEN}"
    if request.headers.get("Authorization", "") != expected:
        return JsonResponse({"error": "unauthorized"}, status=401)

    qs = LinhKien.objects.select_related(*SELECT).order_by("id")
    data = [
        {
            "id":           lk.id,
            "loai":         lk.loai,
            "ten":          lk.ten,
            "hang":         lk.hang,
            "gia_hien_tai": float(lk.gia_hien_tai),
            "tom_tat":      lk.tom_tat,
            "anh_dai_dien": request.build_absolute_uri(lk.anh_dai_dien) if lk.anh_dai_dien else "",
        }
        for lk in qs
    ]
    return JsonResponse(data, safe=False)