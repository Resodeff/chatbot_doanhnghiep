import re
import json
import logging
import logging.handlers
import os
from collections import defaultdict

_rag_logger = logging.getLogger("rag.debug")
if not _rag_logger.handlers:
    _log_path = os.path.join(os.path.dirname(__file__), "rag_debug.log")
    _fh = logging.FileHandler(_log_path, encoding="utf-8")
    _fh.setLevel(logging.DEBUG)
    _fh.setFormatter(logging.Formatter("%(asctime)s\n%(message)s\n"))
    _rag_logger.addHandler(_fh)
    _rag_logger.setLevel(logging.DEBUG)
    _rag_logger.propagate = False

LOAI_ORDER = ["GPU", "CPU", "MAIN", "RAM", "SSD", "HDD", "PSU", "COOLER", "CASE"]


def _fmt_line(p: dict, index: int | None = None) -> str:
    gia = f"{int(p['gia']):,}".replace(",", ".") + "đ"
    prefix = f"[{index}] " if index is not None else "- "
    line = f"{prefix}{p['ten']} | giá {gia}"
    if p.get("thong_so"):
        line += f" | {p['thong_so']}"
    if p.get("anh"):
        line += f" | ảnh: {p['anh']}"
    return line


def format_products(products: list[dict], limit: int, numbered: bool = False) -> str:
    if not products:
        return "(trống - không tìm thấy sản phẩm phù hợp)"

    grouped: dict[str, list[dict]] = defaultdict(list)
    for p in products:
        loai = (p.get("loai") or "KHÁC").upper()
        grouped[loai].append(p)

    order = LOAI_ORDER + sorted(k for k in grouped if k not in LOAI_ORDER)

    sections: list[str] = []
    for loai in order:
        if loai not in grouped:
            continue
        items = grouped[loai][:limit]
        header = f"[{loai} — {len(items)} sản phẩm]"
        lines = [
            _fmt_line(p, index=(i if numbered else None))
            for i, p in enumerate(items, 1)
        ]
        sections.append(header + "\n" + "\n".join(lines))

    return "\n\n".join(sections)


def format_products_debug(products: list[dict], limit: int = 10) -> str:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for p in products:
        loai = (p.get("loai") or "KHÁC").upper()
        grouped[loai].append(p)

    all_loai = LOAI_ORDER + sorted(k for k in grouped if k not in LOAI_ORDER)
    lines: list[str] = []
    total = 0

    for loai in all_loai:
        items = grouped.get(loai, [])[:limit]
        count = len(items)
        total += count
        flag = "⚠️  THIẾU" if count == 0 else f"{count} sản phẩm"
        lines.append(f"\n  ┌─ [{loai}] {flag}")
        for i, p in enumerate(items, 1):
            gia = f"{int(p['gia']):,}".replace(",", ".") + "đ"
            ts  = p.get("thong_so", "")
            ts_short = (ts[:60] + "…") if ts and len(ts) > 60 else ts
            prefix = "  └─" if i == len(items) else "  ├─"
            lines.append(f"  {prefix} {i:>2}. {p['ten'][:60]}")
            lines.append(f"         giá: {gia}" + (f" | {ts_short}" if ts_short else ""))

    sep = "─" * 56
    lines.append(f"\n  {sep}")
    lines.append(f"  Tổng retrieve: {len(products)} sản phẩm → hiển thị {total} (max {limit}/loại)")
    return "\n".join(lines)


def is_multi_type_build(products: list[dict]) -> bool:
    distinct_types = {(p.get("loai") or "").upper() for p in products}
    return len(distinct_types) >= 5


def build_pick_messages(message: str, products: list[dict]) -> list[dict]:
    product_block = format_products(products, limit=4, numbered=True)
    sys_msg = (
        "Bạn là kỹ thuật viên PC. Chọn 1 số thứ tự (1 đến 4) cho mỗi loại linh kiện trong DANH SÁCH SẢN PHẨM "
        "sao cho tương thích tuyệt đối (đúng socket CPU và Mainboard, đúng chuẩn RAM DDR4/DDR5, PSU đủ công suất gánh GPU) và tổng tiền vừa ngân sách.\n"
        "Chỉ trả về JSON:\n"
        '{"CPU": 1, "MAIN": 1, "RAM": 1, "GPU": 1, "SSD": 1, "PSU": 1, "COOLER": 1, "CASE": 1}'
    )
    user_msg = f"DANH SÁCH SẢN PHẨM:\n{product_block}\n\nYÊU CẦU CỦA KHÁCH: {message}"
    return [
        {"role": "system", "content": sys_msg},
        {"role": "user", "content": user_msg},
    ]


def _detect_socket(p: dict) -> str | None:
    text = f"{p.get('ten', '')} {p.get('thong_so', '')}".lower()
    for sk in ("am5", "am4", "lga1851", "lga 1851", "lga1700", "lga 1700", "lga1200", "lga 1200"):
        if sk in text:
            return sk.replace(" ", "")
    if re.search(r"ryzen\s*[579]\s*[789]\d{3}", text):
        return "am5"
    if re.search(r"ryzen\s*[3579]\s*[345]\d{3}", text):
        return "am4"
    if re.search(r"i[3579]-1[234]\d{3}", text):
        return "lga1700"
    if re.search(r"ultra\s*[579]", text):
        return "lga1851"
    return None


def _detect_ddr(p: dict) -> str | None:
    text = f"{p.get('ten', '')} {p.get('thong_so', '')}".lower()
    if "ddr5" in text:
        return "ddr5"
    if "ddr4" in text:
        return "ddr4"
    return None


def resolve_picked_products(raw_json: str, products: list[dict]) -> list[dict]:
    by_loai: dict[str, list[dict]] = defaultdict(list)
    for p in products:
        by_loai[(p.get("loai") or "").upper()].append(p)

    data: dict = {}
    cleaned = clean_reply(raw_json)
    m = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if m:
        try:
            data = json.loads(m.group(0))
        except Exception:
            data = {}

    def _pick(loai: str) -> dict | None:
        cands = by_loai.get(loai, [])[:4]
        if not cands:
            return None
        try:
            idx = int(data.get(loai, 1)) - 1
        except Exception:
            idx = 0
        return cands[idx] if 0 <= idx < len(cands) else cands[0]

    chosen_map: dict[str, dict] = {}
    for loai in ["GPU", "CPU", "MAIN", "RAM", "SSD", "PSU", "COOLER", "CASE"]:
        item = _pick(loai)
        if item:
            chosen_map[loai] = item

    cpu = chosen_map.get("CPU")
    if cpu and by_loai.get("MAIN"):
        cpu_sk = _detect_socket(cpu)
        main = chosen_map.get("MAIN")
        main_sk = _detect_socket(main) if main else None
        if cpu_sk and main_sk and cpu_sk != main_sk:
            for cand in by_loai["MAIN"][:4]:
                if _detect_socket(cand) == cpu_sk:
                    chosen_map["MAIN"] = cand
                    break

    main = chosen_map.get("MAIN")
    if main and by_loai.get("RAM"):
        main_ddr = _detect_ddr(main)
        ram = chosen_map.get("RAM")
        ram_ddr = _detect_ddr(ram) if ram else None
        if main_ddr and ram_ddr and main_ddr != ram_ddr:
            for cand in by_loai["RAM"][:4]:
                if _detect_ddr(cand) == main_ddr:
                    chosen_map["RAM"] = cand
                    break

    order = ["GPU", "CPU", "MAIN", "RAM", "SSD", "PSU", "COOLER", "CASE"]
    return [chosen_map[k] for k in order if k in chosen_map]


def build_present_build_messages(
    system_prompt: str,
    message: str,
    selected_products: list[dict],
) -> list[dict]:
    lines = []
    for p in selected_products:
        ts = f" ({p['thong_so']})" if p.get("thong_so") else ""
        lines.append(f"- {p['loai']}: {p['ten']}{ts}")

    verified_block = "\n".join(lines)

    user_msg = (
        f"KHÁCH HỎI: {message}\n\n"
        f"BỘ MÁY ĐÃ CHỐT CHO KHÁCH:\n{verified_block}\n\n"
        "NHIỆM VỤ: Đóng vai nhân viên tư vấn của shop (xưng mình/em - bạn), trả về JSON nhận xét ngắn gọn để ghép vào bảng cấu hình:\n"
        "- mo_dau: 2 câu ngắn chào khách theo đúng nhu cầu và ngân sách khách nêu, kết thúc bằng 'Mình đề xuất bộ máy sau:' (KHÔNG ghi số tiền tổng hay tên linh kiện ở đây).\n"
        "- GPU, CPU, MAIN, RAM, SSD, PSU, COOLER, CASE: mỗi trường là 1 cụm nhận xét ngắn 6-12 từ về hiệu năng hoặc độ tương thích với món khác trong bộ (ví dụ: 'lựa chọn phổ biến, hiệu năng ổn định' hoặc 'hỗ trợ đúng socket CPU và RAM DDR5').\n"
        "- ket_thuc: 1 câu hỏi ngắn xem khách có muốn điều chỉnh linh kiện nào không (KHÔNG tự bịa số tiền khác)."
    )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_msg},
    ]


def render_present_build(raw_notes_json: str, selected_products: list[dict]) -> str:
    label_map = {
        "GPU": "GPU",
        "CPU": "CPU",
        "MAIN": "Mainboard",
        "RAM": "RAM",
        "SSD": "SSD",
        "PSU": "Nguồn",
        "COOLER": "Tản nhiệt",
        "CASE": "Vỏ máy",
    }
    default_notes = {
        "GPU": "hiệu năng đồ họa mạnh mẽ, chiến mượt các tựa game",
        "CPU": "xử lý đa nhiệm nhanh, tối ưu hiệu năng chơi game",
        "MAIN": "tương thích chuẩn socket với CPU và hỗ trợ nâng cấp tốt",
        "RAM": "dung lượng và tốc độ đáp ứng mượt mà nhu cầu game",
        "SSD": "tốc độ đọc ghi cao, tải game và khởi động nhanh",
        "PSU": "công suất ổn định, cấp nguồn an toàn cho cả hệ thống",
        "COOLER": "giữ nhiệt độ CPU luôn mát mẻ khi tải nặng",
        "CASE": "thiết kế thoáng khí, lắp đặt gọn gàng các linh kiện",
    }

    notes: dict = {}
    cleaned = clean_reply(raw_notes_json)
    m = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if m:
        try:
            notes = json.loads(m.group(0))
        except Exception:
            notes = {}

    mo_dau = str(notes.get("mo_dau", "")).strip()
    if not mo_dau or any(w in mo_dau.lower() for w in ("chưa bao gồm", "dư ra", "kiểm tra bộ máy")):
        mo_dau = "Chào bạn, dựa trên nhu cầu và ngân sách của bạn, mình sẽ ưu tiên cấu hình cân bằng và hiệu năng tối ưu nhất. Mình đề xuất bộ máy sau:"

    lines = [mo_dau + "\n"]
    tong_tien = 0

    for p in selected_products:
        loai = (p.get("loai") or "").upper()
        label = label_map.get(loai, loai)
        gia = int(p["gia"])
        tong_tien += gia
        gia_str = f"{gia:,}".replace(",", ".") + "đ"
        note = str(notes.get(loai, "")).strip().rstrip(".")
        if not note or len(note) > 120:
            note = default_notes.get(loai, "tương thích đồng bộ với cấu hình")
        lines.append(f"- **{label}:** {p['ten']} ({gia_str}) – {note}")

    tong_str = f"{tong_tien:,}".replace(",", ".") + "đ"
    lines.append(f"\n**Tổng chi phí:** **{tong_str}**")

    ket_thuc = str(notes.get("ket_thuc", "")).strip()
    if not ket_thuc or any(w in ket_thuc.lower() for w in ("chưa bao gồm", "dư ra", "lên bảng báo giá")):
        ket_thuc = "Bạn có muốn điều chỉnh thêm linh kiện nào để phù hợp hơn với nhu cầu của mình không?"
    lines.append(f"\n{ket_thuc}")

    return "\n".join(lines)


def build_messages(system_prompt, message, history, products, max_turns, max_products,
                   debug: bool = True):
    product_block = format_products(products, max_products, numbered=False)

    if debug:
        _rag_logger.debug(
            "━" * 60 + "\n"
            "CÂU HỎI: %s\n"
            "%s\n"
            + "━" * 60,
            message,
            format_products_debug(products, max_products),
        )

    msgs = [{"role": "system", "content": system_prompt}]
    for h in history[-max_turns * 2:]:
        if h.get("role") in ("user", "assistant") and h.get("content"):
            msgs.append({"role": h["role"], "content": h["content"][:1000]})

    user = (
        "DANH SÁCH SẢN PHẨM (dữ liệu thật của cửa hàng):\n"
        f"{product_block}\n\n"
        f"CÂU HỎI CỦA KHÁCH: {message}"
    )
    msgs.append({"role": "user", "content": user})
    return msgs


def clean_reply(text: str) -> str:
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    return text.strip()