import json
import logging
import re
import urllib.error
import urllib.request

from django.conf import settings
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

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
    "CPU": ["cpu", "vi xử lý", "intel", "ryzen", "i5", "i7", "i9"],
    "MAIN": ["mainboard", "main", "bo mạch"],
    "RAM": ["ram", "bộ nhớ"],
    "SSD": ["ssd", "nvme", "m.2"],
    "HDD": ["hdd", "ổ cứng cơ", "ổ cơ"],
    "GPU": ["gpu", "vga", "card đồ họa", "card màn hình", "rtx", "gtx", "radeon"],
    "PSU": ["nguồn", "psu"],
    "COOLER": ["tản nhiệt", "tản", "cooler", "aio", "quạt"],
    "CASE": ["case", "vỏ"],
}


def detect_loai(msg):
    """Chọn loại có từ khóa khớp dài nhất (vd 'mainboard intel' -> MAIN, không phải CPU)."""
    best, best_len = None, 0
    for code, kws in KEYWORDS.items():
        for k in kws:
            if k in msg and len(k) > best_len:
                best, best_len = code, len(k)
    return best


log = logging.getLogger(__name__)


def search_products(msg_lower, limit=6):
    """Tìm sản phẩm liên quan trong DB theo loại + ngân sách trong câu hỏi (đưa cho chatbot làm ngữ cảnh)."""
    loai = detect_loai(msg_lower)
    qs = LinhKien.objects.select_related(*SELECT)
    if loai:
        qs = qs.filter(loai=loai)
    elif "ổ cứng" in msg_lower:
        loai = "STORAGE"
        qs = qs.filter(loai__in=["SSD", "HDD"])

    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(triệu|tr|m)\b", msg_lower)
    if m:
        qs = qs.filter(gia_hien_tai__lte=float(m.group(1).replace(",", ".")) * 1_000_000)

    if not loai and not m:
        return []                                  # chưa đủ thông tin: để chatbot hỏi lại

    items = list(qs.order_by("-gia_hien_tai" if m else "gia_hien_tai")[:200])
    if not m and len(items) > limit:               # không có ngân sách: lấy rải đều từ rẻ -> đắt
        step = len(items) / limit
        items = [items[int(i * step)] for i in range(limit)]
    return items[:limit]


def to_payload(items):
    return [{"ten": p.ten[:120], "gia": float(p.gia_hien_tai), "thong_so": p.tom_tat} for p in items]


def rule_reply(items):
    """Dự phòng khi chatbot AI (FastAPI/Ollama) không chạy."""
    if not items:
        return ("Bạn cần tư vấn linh kiện nào (CPU, mainboard, RAM, SSD, HDD, GPU, nguồn, tản nhiệt, case) "
                "và ngân sách bao nhiêu? Ví dụ: “card đồ họa dưới 10 triệu”.")
    lines = []
    for p in items[:3]:
        gia = f"{int(p.gia_hien_tai):,}".replace(",", ".")
        t = p.tom_tat
        lines.append(f"• {p.ten[:70]} — {gia}đ" + (f"\n   {t}" if t else ""))
    return "Mình gợi ý cho bạn:\n" + "\n".join(lines)


def call_chatbot_api(message, history, products):
    url = settings.CHATBOT_API_URL.rstrip("/") + "/chat"
    body = json.dumps({"message": message, "history": history, "products": products}).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=settings.CHATBOT_TIMEOUT) as r:
        return json.loads(r.read())["reply"]


@require_POST
def chat_api(request):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"reply": "Tin nhắn không hợp lệ."}, status=400)
    message = str(data.get("message", "")).strip()[:1000]
    if not message:
        return JsonResponse({"reply": "Bạn hãy nhập câu hỏi nhé."}, status=400)
    history = [{"role": h["role"], "content": str(h["content"])[:1000]}
               for h in (data.get("history") or [])[-12:]
               if isinstance(h, dict) and h.get("role") in ("user", "assistant") and h.get("content")]

    items = search_products(message.lower())
    try:
        reply = call_chatbot_api(message, history, to_payload(items))
    except (urllib.error.URLError, TimeoutError, KeyError, ValueError) as e:
        log.warning("Chatbot API lỗi, dùng câu trả lời dự phòng: %s", e)
        reply = rule_reply(items)
    return JsonResponse({"reply": reply})
