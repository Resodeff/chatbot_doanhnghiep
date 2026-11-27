"""Kiểm tra tương thích của một bộ linh kiện (service độc lập).

Nhận danh sách sản phẩm (dict dạng như retrieve() trả về: loai/ten/thong_so),
trả về danh sách cảnh báo (rỗng = tương thích).
Chỉ kiểm tra những gì dữ liệu cho phép: socket CPU-Main, chuẩn RAM,
cỡ mainboard vs case, và quy tắc iGPU (không có card rời thì CPU phải có iGPU).
Không kiểm tra công suất PSU (cần TDP mà DB chưa có).
"""

import re

from prompting import _detect_ddr, _detect_socket, _has_igpu

# Thứ tự cỡ mainboard, từ nhỏ tới lớn. Case hỗ trợ tới cỡ X thì
# chứa được mọi mainboard có cỡ <= X.
_SIZE_ORDER = {"MINI-ITX": 0, "MICRO-ATX": 1, "ATX": 2, "E-ATX": 3}


def _short(p: dict | None) -> str:
    ten = (p or {}).get("ten", "")
    return ten if len(ten) <= 60 else ten[:60] + "…"


def _text(p: dict | None) -> str:
    if not p:
        return ""
    return f"{p.get('ten', '')} {p.get('thong_so', '')}"


def _detect_form_factor(text: str) -> str | None:
    """Nhận dạng cỡ mainboard từ tên/thông số. Trả None nếu không xác định được."""
    t = (text or "").lower()
    if re.search(r"mini[-\s]?itx|\bitx\b", t):
        return "MINI-ITX"
    if re.search(r"micro[-\s]?atx|\bm[-\s]?atx\b", t):
        return "MICRO-ATX"
    if re.search(r"\be[-\s]?atx\b", t):
        return "E-ATX"
    if re.search(r"\batx\b", t):
        return "ATX"
    return None


def _detect_supported_sizes(text: str) -> set[str]:
    """Các cỡ mainboard mà case hỗ trợ (đọc từ tên/thông số)."""
    t = (text or "").lower()
    out: set[str] = set()
    if re.search(r"mini[-\s]?itx|\bitx\b", t):
        out.add("MINI-ITX")
    if re.search(r"micro[-\s]?atx|\bm[-\s]?atx\b", t):
        out.add("MICRO-ATX")
    if re.search(r"\be[-\s]?atx\b", t):
        out.add("E-ATX")
    if re.search(r"\batx\b", t):
        out.add("ATX")
    return out


def check_compatibility(products: list[dict]) -> list[str]:
    """Kiểm tra một bộ linh kiện, trả về danh sách cảnh báo (rỗng = tương thích)."""
    warnings: list[str] = []
    by_loai: dict[str, dict] = {}
    for p in products:
        by_loai.setdefault((p.get("loai") or "").upper(), p)

    cpu = by_loai.get("CPU")
    main = by_loai.get("MAIN")
    ram = by_loai.get("RAM")
    gpu = by_loai.get("GPU")
    case = by_loai.get("CASE")

    # 1. Socket CPU vs Mainboard
    if cpu and main:
        cpu_sk = _detect_socket(cpu)
        main_sk = _detect_socket(main)
        if cpu_sk and main_sk and cpu_sk != main_sk:
            warnings.append(
                f"CPU {_short(cpu)} (socket {cpu_sk}) không khớp mainboard {_short(main)} (socket {main_sk})."
            )

    # 2. Chuẩn RAM Mainboard vs RAM
    if main and ram:
        main_ddr = _detect_ddr(main)
        ram_ddr = _detect_ddr(ram)
        if main_ddr and ram_ddr and main_ddr != ram_ddr:
            warnings.append(
                f"Mainboard {_short(main)} ({main_ddr}) không khớp RAM {_short(ram)} ({ram_ddr})."
            )

    # 3. Cỡ mainboard vs case
    if main and case:
        main_ff = _detect_form_factor(_text(main))
        supported = _detect_supported_sizes(_text(case))
        if main_ff and supported:
            biggest = max(supported, key=lambda s: _SIZE_ORDER[s])
            if _SIZE_ORDER[main_ff] > _SIZE_ORDER[biggest]:
                warnings.append(
                    f"Mainboard {_short(main)} (cỡ {main_ff}) không vừa case {_short(case)} (chỉ hỗ trợ tới {biggest})."
                )

    # 4. Không có card rời thì CPU phải có iGPU
    if not gpu and cpu and not _has_igpu(cpu):
        warnings.append(
            f"CPU {_short(cpu)} không có đồ họa tích hợp mà bộ máy không có card rời — máy sẽ không xuất hình được."
        )

    return warnings